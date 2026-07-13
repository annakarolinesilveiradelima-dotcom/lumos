from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests

import build_data
import config


TIMEOUT = 25
BR_TZ = ZoneInfo("America/Sao_Paulo")

TITLE_ID = getattr(config, "TITLE_ID", "hp")
OUTPUT_DATA = getattr(config, "OUTPUT_DATA", "../data.json")
HISTORY_DIR = getattr(config, "HISTORY_DIR", "../history")

TEASER_DATE = datetime(2026, 3, 25, 0, 0, 0, tzinfo=BR_TZ)

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

SEARCH_QUERIES = [
    "Harry Potter HBO",
    "Harry Potter Max",
    "serie Harry Potter HBO",
    "nova serie Harry Potter",
    "Harry Potter HBO series",
    "Harry Potter cast HBO",
    "Dominic McLaughlin Harry Potter",
    "Arabella Stanton Harry Potter",
    "Alastair Stout Harry Potter",
    "Paapa Essiedu Harry Potter",
    "John Lithgow Harry Potter"
]

TRENDS_KEYWORDS = [
    "Harry Potter",
    "Harry Potter HBO",
    "Harry Potter Max",
    "Harry Potter series",
    "HBO Harry Potter",
    "nova serie Harry Potter",
    "John Lithgow Harry Potter",
    "Paapa Essiedu Harry Potter"
]


def _now_br():
    return datetime.now(BR_TZ)


def _label(dt):
    return f"{dt.day} {PT_MONTHS[dt.month - 1]} {dt.year}"


def _stamp():
    now = _now_br()
    return f"{_label(now)}, {now:%H:%M}"


def _range_label(start, end):
    if start.month == end.month:
        return f"{start.day}-{end.day} {PT_MONTHS[end.month - 1]} {end.year}"

    return (
        f"{start.day} {PT_MONTHS[start.month - 1]}-"
        f"{end.day} {PT_MONTHS[end.month - 1]} {end.year}"
    )


def _iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_pubdate(value):
    if not value:
        return None

    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return None


def _format_time_br(dt):
    if not dt:
        return "sem horario disponivel"

    try:
        br = dt.astimezone(BR_TZ)
        return f"{br.day} {PT_MONTHS[br.month - 1]}, {br:%H:%M}"
    except Exception:
        return "sem horario disponivel"


def _clean_title(title):
    title = re.sub(r"\s+", " ", title or "").strip()

    if " - " in title:
        parts = title.rsplit(" - ", 1)
        if len(parts[0]) > 10:
            return parts[0].strip()

    return title


def _cat(text):
    t = (text or "").lower()

    if re.search(r"rumor|especula|supost|vaza|vazou|pode|possivel|teria|leak|leaked", t):
        return "esp"

    if re.search(r"nostalg|filmes|classic|classico|trilha|infancia|reboot|movies|original cast", t):
        return "nos"

    if re.search(r"critic|polem|decep|rejeit|problema|desnecess|medo|hate|worried|terrible|ruined", t):
        return "neg"

    if re.search(r"elogi|acerto|fiel|ansios|empolg|aprova|confirma|revela|estreia|elenco|excited|love|perfect|faithful|reaction|review", t):
        return "pos"

    return "neu"


def _senti_from_cat(cat):
    mapping = {
        "pos": "pos",
        "neg": "neg",
        "esp": "div",
        "nos": "pos",
        "neu": "neu"
    }

    return mapping.get(cat, "neu")


def _source_from_rss_item(item, raw_title):
    source = item.findtext("source")

    if source:
        return source.strip()

    if raw_title and " - " in raw_title:
        return raw_title.rsplit(" - ", 1)[-1].strip()

    return "Google News"


def _google_news_url(query):
    encoded = quote_plus(query)

    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=pt-BR"
        "&gl=BR"
        "&ceid=BR:pt-419"
    )


def _trends_url(query):
    encoded = quote_plus(query)

    return (
        "https://trends.google.com/trends/explore"
        "?date=2026-03-25%202026-07-13"
        "&geo=BR"
        f"&q={encoded}"
    )


def _dedupe_coverage(items):
    seen = set()
    out = []

    for item in items:
        url = item.get("u", "")
        title = item.get("title", "")

        if not url or not title:
            continue

        key = (url.split("?")[0] + "|" + title).lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def _has_real_coverage(snapshot):
    if not snapshot:
        return False

    coverage = snapshot.get("coverage", [])

    return isinstance(coverage, list) and len(coverage) > 0


def _history_path(snapshot_date):
    return os.path.join(HISTORY_DIR, f"day-{snapshot_date:%Y-%m-%d}.json")


def _load_existing_snapshot(snapshot_date):
    path = _history_path(snapshot_date)

    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        print(f"[backfill] nao consegui ler snapshot existente {path}: {exc}")
        return None


def _load_existing_current_day():
    try:
        with open(OUTPUT_DATA, encoding="utf-8") as file:
            feed = json.load(file)

        return feed["titles"][TITLE_ID]["days"]["d0"]
    except Exception as exc:
        print(f"[backfill] nao consegui ler d0 existente: {exc}")
        return None


def collect_google_news_week(start, end):
    results = []

    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)

    for query in SEARCH_QUERIES:
        url = _google_news_url(query)

        try:
            response = requests.get(url, timeout=TIMEOUT)

            print(
                f"[google_news] query='{query}' "
                f"{start.date()} to {end.date()} status={response.status_code}"
            )

            if response.status_code != 200:
                print("[google_news] resposta:", response.text[:300])
                continue

            root = ET.fromstring(response.content)
            channel = root.find("channel")

            if channel is None:
                continue

            items = channel.findall("item")

            print(f"[google_news] query='{query}' retornou {len(items)} itens RSS")

            for item in items:
                raw_title = item.findtext("title") or ""
                title = _clean_title(raw_title)
                link = item.findtext("link") or ""
                description = item.findtext("description") or ""
                pub_date = _parse_pubdate(item.findtext("pubDate"))

                if not title or not link or not pub_date:
                    continue

                if not (start_utc <= pub_date <= end_utc):
                    continue

                source = _source_from_rss_item(item, raw_title)
                cat = _cat(title + " " + description)

                results.append({
                    "o": source,
                    "u": link,
                    "title": title,
                    "cat": cat,
                    "time": _format_time_br(pub_date),
                    "scope": "Google News RSS"
                })

            time.sleep(1)

        except Exception as exc:
            print(f"[google_news] falha query='{query}': {exc}")

    results = _dedupe_coverage(results)

    print(f"[google_news] {len(results)} materias reais coletadas na semana")

    return results


def collect_youtube_week(start, end, api_key):
    if not api_key:
        print("[youtube] YOUTUBE_API_KEY nao configurada. Pulando YouTube.")
        return []

    results = []

    for query in SEARCH_QUERIES:
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": 10,
            "order": "date",
            "publishedAfter": _iso_utc(start),
            "publishedBefore": _iso_utc(end),
            "regionCode": "BR",
            "relevanceLanguage": "pt",
            "key": api_key
        }

        try:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
                timeout=TIMEOUT
            )

            print(
                f"[youtube] query='{query}' "
                f"{start.date()} to {end.date()} status={response.status_code}"
            )

            if response.status_code != 200:
                print("[youtube] resposta:", response.text[:500])
                continue

            data = response.json()
            items = data.get("items", [])

            print(f"[youtube] query='{query}' retornou {len(items)} videos")

            for item in items:
                video_id = (item.get("id") or {}).get("videoId")
                snippet = item.get("snippet") or {}

                if not video_id:
                    continue

                title = (snippet.get("title") or "").strip()
                description = snippet.get("description") or ""
                channel = snippet.get("channelTitle") or "YouTube"
                published = snippet.get("publishedAt") or ""

                if not title:
                    continue

                pub_date = None

                try:
                    pub_date = datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except Exception:
                    pub_date = None

                url = f"https://www.youtube.com/watch?v={video_id}"
                cat = _cat(title + " " + description)

                results.append({
                    "o": f"YouTube - {channel}",
                    "u": url,
                    "title": title,
                    "cat": cat,
                    "time": _format_time_br(pub_date),
                    "scope": "Video/Creator - YouTube"
                })

        except Exception as exc:
            print(f"[youtube] falha query='{query}': {exc}")

    results = _dedupe_coverage(results)

    print(f"[youtube] {len(results)} videos reais coletados na semana")

    return results


def _chunk_keywords(keywords, size=5):
    for i in range(0, len(keywords), size):
        yield keywords[i:i + size]


def collect_google_trends_period(global_start, global_end):
    try:
        from pytrends.request import TrendReq
    except Exception as exc:
        print(f"[trends] pytrends nao instalado/disponivel: {exc}")
        return {}

    timeframe = f"{global_start:%Y-%m-%d} {global_end:%Y-%m-%d}"

    for geo in ["BR", ""]:
        print(f"[trends] coletando periodo completo timeframe='{timeframe}' geo='{geo or 'GLOBAL'}'")

        geo_scores = {}

        try:
            pytrends = TrendReq(
                hl="pt-BR",
                tz=180,
                timeout=(10, 25),
                retries=2,
                backoff_factor=0.3
            )

            for chunk in _chunk_keywords(TRENDS_KEYWORDS, 5):
                try:
                    pytrends.build_payload(
                        chunk,
                        cat=0,
                        timeframe=timeframe,
                        geo=geo,
                        gprop=""
                    )

                    df = pytrends.interest_over_time()

                    if df is None or df.empty:
                        print(f"[trends] dataframe vazio para chunk={chunk}")
                        continue

                    if "isPartial" in df.columns:
                        df = df.drop(columns=["isPartial"])

                    for date_index, row in df.iterrows():
                        try:
                            date_key = date_index.to_pydatetime().date().isoformat()
                        except Exception:
                            date_key = str(date_index)[:10]

                        if date_key not in geo_scores:
                            geo_scores[date_key] = {}

                        for keyword in chunk:
                            if keyword in row:
                                try:
                                    value = int(row[keyword])
                                except Exception:
                                    value = 0

                                geo_scores[date_key][keyword] = value

                    print(f"[trends] chunk={chunk} linhas={len(df)}")

                    time.sleep(2)

                except Exception as exc:
                    print(f"[trends] falha chunk={chunk}: {exc}")

        except Exception as exc:
            print(f"[trends] falha geral geo='{geo}': {exc}")

        max_value = 0

        for date_scores in geo_scores.values():
            if date_scores:
                max_value = max(max_value, max(date_scores.values()))

        print(f"[trends] geo='{geo or 'GLOBAL'}' max_value={max_value}")

        if max_value > 0:
            print(f"[trends] datas coletadas={len(geo_scores)}")
            return geo_scores

    print("[trends] nenhum dado valido coletado")
    return {}


def score_google_trends_week(start, end, trends_period_scores):
    if not trends_period_scores:
        return {
            "score": 0,
            "top_keyword": "",
            "keywords": {},
            "coverage": []
        }

    start_date = start.date()
    end_date = end.date()
    bucket = {}

    for date_key, keyword_scores in trends_period_scores.items():
        try:
            current_date = datetime.fromisoformat(date_key).date()
        except Exception:
            continue

        if not (start_date <= current_date <= end_date):
            continue

        for keyword, value in keyword_scores.items():
            if keyword not in bucket:
                bucket[keyword] = []

            bucket[keyword].append(int(value or 0))

    averages = {}

    for keyword, values in bucket.items():
        values = [int(v or 0) for v in values]
        averages[keyword] = round(sum(values) / len(values)) if values else 0

    if not averages:
        return {
            "score": 0,
            "top_keyword": "",
            "keywords": {},
            "coverage": []
        }

    top_keyword = max(averages, key=averages.get)
    top_score = int(averages.get(top_keyword, 0) or 0)

    coverage = []

    if top_score > 0:
        coverage.append({
            "o": "Google Trends",
            "u": _trends_url(top_keyword),
            "title": f"Interesse de busca por '{top_keyword}' no Brasil",
            "cat": "neu",
            "time": _range_label(start, end),
            "scope": f"Google Trends - interesse {top_score}/100"
        })

    print(f"[trends] semana {start.date()} to {end.date()} score={top_score} top_keyword='{top_keyword}'")

    return {
        "score": top_score,
        "top_keyword": top_keyword,
        "keywords": averages,
        "coverage": coverage
    }


def _build_sentiment(coverage):
    if not coverage:
        return 0, 100, 0, 50

    pos = sum(1 for item in coverage if item.get("cat") in ("pos", "nos"))
    neg = sum(1 for item in coverage if item.get("cat") == "neg")
    total = len(coverage)

    p = round(pos / total * 100)
    n = round(neg / total * 100)
    g = max(0, 100 - p - n)
    index = 50 + round((p - n) / 2)

    return p, g, n, index


def _platform_from_source(source):
    source = str(source or "")

    if source.startswith("YouTube"):
        return "YouTube"

    if source.startswith("Google Trends"):
        return "Google Trends"

    return "Imprensa"


def _narratives_from_coverage(coverage):
    narratives = []

    for item in coverage[:6]:
        platform = _platform_from_source(item.get("o", "Fonte"))

        narratives.append({
            "t": item.get("title", "Cobertura real coletada"),
            "vol": 1,
            "senti": _senti_from_cat(item.get("cat", "neu")),
            "pf": platform,
            "trend": "flat",
            "growth": "Baseado em fonte real coletada via Google News RSS, YouTube ou Google Trends",
            "q": "",
            "pct": 50,
            "src": [
                {
                    "o": item.get("o", "Fonte"),
                    "u": item.get("u", "#")
                }
            ]
        })

    return narratives


def _risks_from_coverage(coverage, week_label):
    if not coverage:
        return [
            {
                "t": "Semana sem cobertura real",
                "sev": "low",
                "d": f"Nao foram encontradas materias, videos ou sinais de busca para a janela {week_label}.",
                "rec": "Manter monitoramento e adicionar fontes historicas complementares como Wikipedia Pageviews."
            }
        ]

    titles = " ".join(item.get("title", "") for item in coverage).lower()
    risks = []

    if any(w in titles for w in ["reboot", "filmes", "movies", "nostalg"]):
        risks.append({
            "t": "Comparacao com os filmes originais",
            "sev": "mid",
            "d": "A conversa pode reacender comparacao com a saga original e expectativa de fidelidade aos livros.",
            "rec": "Reforcar que a serie e uma nova adaptacao com espaco para aprofundamento narrativo."
        })

    if any(w in titles for w in ["cast", "casting", "elenco", "ator", "atriz"]):
        risks.append({
            "t": "Sensibilidade em torno de elenco",
            "sev": "mid",
            "d": "Materias, videos ou buscas sobre escalacao podem gerar discussao sobre aderencia ao imaginario dos fas.",
            "rec": "Acompanhar comentarios e preparar mensagens sobre intencao criativa e construcao de personagens."
        })

    if not risks:
        risks.append({
            "t": "Risco baixo na cobertura",
            "sev": "low",
            "d": "A janela teve fonte real ou sinal de busca coletado, mas sem sinais criticos fortes.",
            "rec": "Manter monitoramento e registrar mudancas de tom nas proximas coletas."
        })

    return risks[:3]


def _opps_from_coverage(coverage, week_label):
    if not coverage:
        return [
            {
                "ico": "mail",
                "t": "Monitorar proxima coleta",
                "d": f"A janela {week_label} ainda nao tem fonte real suficiente."
            }
        ]

    return [
        {
            "ico": "book",
            "t": "Explorar fidelidade aos livros",
            "d": "Quando existe cobertura, video ou interesse de busca, ha oportunidade de explicar como a serie pode aprofundar pontos nao explorados nos filmes."
        },
        {
            "ico": "film",
            "t": "Organizar narrativa de comparacao",
            "d": "Usar videos, conteudos editoriais e sinais de busca para posicionar a serie como nova leitura para streaming."
        }
    ]


def _empty_snapshot(snapshot_date, week_label):
    return {
        "label": _label(snapshot_date),
        "updated": _stamp(),
        "kpi": {
            "mentions": {
                "v": "0 itens",
                "d": 0,
                "sub": f"sem cobertura/sinal real nesta semana - {week_label}"
            },
            "sentiment": {
                "v": "-",
                "suf": "",
                "d": 0,
                "sub": "sem base suficiente"
            },
            "sov": {
                "v": "-",
                "d": 0,
                "dtype": "pts",
                "sub": "requer base multi-titulo"
            },
            "buzz": {
                "v": "0",
                "suf": "/100",
                "d": 0,
                "sub": "sem cobertura ou busca real"
            }
        },
        "senti": {
            "pos": 0,
            "neu": 100,
            "neg": 0,
            "tone": "Sem cobertura ou sinal real coletado nesta janela"
        },
        "buzz7": [0, 0, 0, 0, 0, 0, 0],
        "stack": [
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0]
        ],
        "platforms": [
            {
                "name": "Imprensa/YouTube/Trends",
                "vol": 1,
                "senti": "neu",
                "ang": -90,
                "s": {
                    "p": 0,
                    "n": 0,
                    "g": 100
                }
            }
        ],
        "narratives": [],
        "coverage": [],
        "creators": [],
        "risks": _risks_from_coverage([], week_label),
        "heroOpp": {
            "title": "Sem oportunidade validada nesta semana",
            "desc": "Nao houve cobertura real suficiente nesta janela semanal.",
            "facts": [
                ["Janela", week_label],
                ["Marco", "teaser 25/03/2026"],
                ["Dados ficticios", "nao"],
                ["Status", "sem cobertura/sinal real"]
            ]
        },
        "opps": _opps_from_coverage([], week_label),
        "ephem": [],
        "_raw": {
            "base_count": 0,
            "unit": "itens",
            "net": 0,
            "buzz": 0,
            "news_count": 0,
            "youtube_count": 0,
            "trends_score": 0,
            "trends_keyword": "",
            "backfill": True
        }
    }


def _snapshot_from_coverage(snapshot_date, week_label, coverage, trends):
    coverage = _dedupe_coverage(coverage)[:12]

    pos, neu, neg, sentiment_index = _build_sentiment(coverage)
    net = pos - neg
    count = len(coverage)

    trends_score = int((trends or {}).get("score", 0) or 0)
    trends_keyword = (trends or {}).get("top_keyword", "")

    buzz_from_coverage = 20 + count * 8 + round(max(0, net) / 2) if count else 0
    buzz = min(100, max(buzz_from_coverage, trends_score))

    youtube_count = sum(
        1 for item in coverage
        if str(item.get("o", "")).startswith("YouTube")
    )

    trends_count = sum(
        1 for item in coverage
        if str(item.get("o", "")).startswith("Google Trends")
    )

    press_count = count - youtube_count - trends_count

    creators = []

    for item in coverage:
        outlet = str(item.get("o", ""))

        if outlet.startswith("YouTube"):
            creators.append({
                "h": outlet.replace("YouTube - ", ""),
                "pf": "YouTube",
                "type": "Video sobre Harry Potter HBO",
                "senti": _senti_from_cat(item.get("cat", "neu")),
                "reach": "nao coletado",
                "rel": 60,
                "risk": "low",
                "c": "#E7A94B",
                "u": item.get("u", "#")
            })

    return {
        "label": _label(snapshot_date),
        "updated": _stamp(),
        "kpi": {
            "mentions": {
                "v": f"{count} item" + ("" if count == 1 else "s"),
                "d": 0,
                "sub": f"{press_count} noticias - {youtube_count} videos YouTube - {trends_count} sinais Trends - {week_label}"
            },
            "sentiment": {
                "v": ("+" if net >= 0 else "") + str(net),
                "suf": "/100",
                "d": 0,
                "sub": "indice semanal por cobertura/sinal"
            },
            "sov": {
                "v": "-",
                "d": 0,
                "dtype": "pts",
                "sub": "requer base multi-titulo"
            },
            "buzz": {
                "v": str(buzz),
                "suf": "/100",
                "d": 0,
                "sub": f"buzz semanal com Google Trends {trends_score}/100"
            }
        },
        "senti": {
            "pos": pos,
            "neu": neu,
            "neg": neg,
            "tone": "Backfill semanal baseado em Google News RSS, YouTube e Google Trends"
        },
        "buzz7": [buzz, buzz, buzz, buzz, buzz, buzz, buzz],
        "stack": [
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg]
        ],
        "platforms": [
            {
                "name": "Imprensa",
                "vol": max(press_count, 1),
                "senti": "pos" if pos >= 55 else "neg" if neg >= 35 else "neu",
                "ang": -90,
                "s": {
                    "p": pos,
                    "n": neg,
                    "g": neu
                }
            },
            {
                "name": "YouTube",
                "vol": max(youtube_count, 1),
                "senti": "pos" if pos >= 55 else "neg" if neg >= 35 else "neu",
                "ang": 70,
                "s": {
                    "p": pos,
                    "n": neg,
                    "g": neu
                }
            },
            {
                "name": "Google Trends",
                "vol": max(trends_score, 1),
                "senti": "neu",
                "ang": 128,
                "s": {
                    "p": 0,
                    "n": 0,
                    "g": 100
                }
            }
        ],
        "narratives": _narratives_from_coverage(coverage),
        "coverage": coverage[:8],
        "creators": creators[:8],
        "risks": _risks_from_coverage(coverage, week_label),
        "heroOpp": {
            "title": "Leitura semanal desde o teaser",
            "desc": f"Semana preenchida por fontes reais e sinais de busca. Janela: {week_label}.",
            "facts": [
                ["Janela", week_label],
                ["Marco", "25/03/2026"],
                ["Itens reais", str(count)],
                ["Trends", f"{trends_keyword or 'sem sinal'} · {trends_score}/100"]
            ]
        },
        "opps": _opps_from_coverage(coverage, week_label),
        "ephem": [],
        "_raw": {
            "base_count": count,
            "unit": "itens",
            "net": net,
            "buzz": buzz,
            "news_count": press_count,
            "youtube_count": youtube_count,
            "trends_score": trends_score,
            "trends_keyword": trends_keyword,
            "backfill": True,
            "sentiment_index": sentiment_index
        }
    }


def _collect_sources_for_range(start, end, youtube_key, trends_period_scores):
    coverage = []

    google_news_coverage = collect_google_news_week(start, end)
    coverage.extend(google_news_coverage)

    youtube_coverage = collect_youtube_week(start, end, youtube_key)
    coverage.extend(youtube_coverage)

    trends = score_google_trends_week(start, end, trends_period_scores)

    if not coverage and trends.get("coverage"):
        coverage.extend(trends.get("coverage", []))

    return _dedupe_coverage(coverage), trends


def _save_snapshot(snapshot_date, snapshot):
    os.makedirs(HISTORY_DIR, exist_ok=True)

    path = _history_path(snapshot_date)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)

    print(f"[backfill] snapshot salvo: {path}")


def _build_current_day(youtube_key, trends_period_scores):
    now = _now_br()
    start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=BR_TZ)
    end = now
    label = _label(now)

    coverage, trends = _collect_sources_for_range(start, end, youtube_key, trends_period_scores)

    if coverage:
        snapshot = _snapshot_from_coverage(end, label, coverage, trends)
        snapshot["label"] = label
        return snapshot

    existing = _load_existing_current_day()

    if _has_real_coverage(existing):
        print("[backfill] d0 atual veio vazio. Mantendo d0 anterior com cobertura.")
        return existing

    return _empty_snapshot(end, label)


def regenerate_feed(current_day):
    if not current_day:
        current_day = _load_existing_current_day()

    if not current_day:
        current_day = _empty_snapshot(_now_br(), _label(_now_br()))

    feed = build_data.build_feed(current_day)
    build_data.write_feed(feed)

    print("[backfill] data.json regenerado com Google News RSS + YouTube + Google Trends.")


def main():
    youtube_key = os.environ.get("YOUTUBE_API_KEY", "").strip()

    if youtube_key:
        print(f"[backfill] YouTube key detectada com {len(youtube_key)} caracteres")
    else:
        print("[backfill] YOUTUBE_API_KEY nao configurada. YouTube sera ignorado.")

    print("[backfill] inicio")
    print("[backfill] fonte principal: Google News RSS + YouTube + Google Trends")
    print("[backfill] marco: teaser em 25/03/2026")
    print(f"[backfill] hoje: {_now_br():%Y-%m-%d %H:%M}")

    now = _now_br()
    trends_period_scores = collect_google_trends_period(TEASER_DATE, now)

    start = TEASER_DATE
    week_index = 1

    while start <= now:
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        if end > now:
            end = now

        week_label = _range_label(start, end)

        print(f"[backfill] Semana {week_index}: {week_label}")

        try:
            coverage, trends = _collect_sources_for_range(start, end, youtube_key, trends_period_scores)

            print(f"[backfill] {len(coverage)} itens reais/sinais na semana {week_label}")

            if coverage:
                snapshot = _snapshot_from_coverage(end, week_label, coverage, trends)
                _save_snapshot(end, snapshot)
            else:
                existing = _load_existing_snapshot(end)

                if _has_real_coverage(existing):
                    print("[backfill] semana veio vazia. Mantendo snapshot anterior com cobertura.")
                    _save_snapshot(end, existing)
                else:
                    snapshot = _empty_snapshot(end, week_label)
                    _save_snapshot(end, snapshot)

        except Exception as exc:
            print(f"[backfill] erro na semana {week_label}: {exc}")

            existing = _load_existing_snapshot(end)

            if _has_real_coverage(existing):
                print("[backfill] erro na semana, mas existe snapshot anterior com cobertura. Mantendo.")
                _save_snapshot(end, existing)
            else:
                snapshot = _empty_snapshot(end, week_label)
                _save_snapshot(end, snapshot)

        time.sleep(2)

        start = start + timedelta(days=7)
        week_index += 1

    current_day = _build_current_day(youtube_key, trends_period_scores)
    regenerate_feed(current_day)

    print("[backfill] concluido")


if __name__ == "__main__":
    main()
