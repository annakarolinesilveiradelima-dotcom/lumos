from __future__ import annotations

import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, quote_plus
from zoneinfo import ZoneInfo

import requests

import config


TIMEOUT = 25
BR_TZ = ZoneInfo("America/Sao_Paulo")

TITLE_ID = getattr(config, "TITLE_ID", "hp")
OUTPUT_DATA = os.environ.get("OUTPUT_DATA", getattr(config, "OUTPUT_DATA", "../data.json"))
HISTORY_DIR = os.environ.get("HISTORY_DIR", getattr(config, "HISTORY_DIR", "../history"))

TEASER_DATE = datetime(2026, 3, 25, 0, 0, 0, tzinfo=BR_TZ)

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

NEWS_QUERIES = [
    "Harry Potter HBO Brasil",
    "Harry Potter Max Brasil",
    "Harry Potter HBO Max Brasil",
    "serie Harry Potter HBO Brasil",
    "nova serie Harry Potter HBO Brasil",
    "Harry Potter HBO elenco Brasil",
    "Paapa Essiedu Harry Potter Brasil",
    "John Lithgow Harry Potter Brasil",
    "Dominic McLaughlin Harry Potter Brasil",
    "Arabella Stanton Harry Potter Brasil"
]

YOUTUBE_QUERIES = [
    "Harry Potter HBO Brasil",
    "Harry Potter HBO Max Brasil",
    "Harry Potter série HBO Brasil",
    "Harry Potter série Max Brasil",
    "Harry Potter HBO Omelete",
    "Harry Potter HBO elenco Brasil",
    "Harry Potter Max Brasil elenco",
    "Harry Potter HBO Brasil Omelete"
]

BR_CHANNELS = [
    "omelete",
    "omeleteve",
    "jovem nerd",
    "ei nerd",
    "pipocando",
    "legião dos heróis",
    "legiao dos herois",
    "observatório do cinema",
    "observatorio do cinema",
    "canal peewee",
    "entre migas",
    "super oito",
    "nerdland",
    "cinematologia",
    "refúgio cult",
    "refugio cult",
    "heróis e mais",
    "herois e mais",
    "nerd rabugento",
    "canaltech",
    "tecmundo",
    "adorocinema",
    "cinepop",
    "coisa de nerd"
]

BLOCKED_YOUTUBE_SIGNALS = [
    "portugal",
    "india",
    "pakistan",
    "pakistani",
    "hindi",
    "ki new update",
    "subscribe this channel",
    "viral",
    "fyp",
    "breakup",
    "sad",
    "slang",
    "shorts",
    "youtubeshorts",
    "hogwarts nearly",
    "movies never told",
    "cursed child subscribe",
    "draco owns me",
    "flash_viral",
    "rave kishorre",
    "harrypotter_portugal"
]

WIKI_PAGES = [
    {
        "project": "pt.wikipedia.org",
        "article": "Harry_Potter",
        "label": "Harry Potter PT"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter",
        "label": "Harry Potter"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter_(TV_series)",
        "label": "Harry Potter TV series"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter_(film_series)",
        "label": "Harry Potter film series"
    },
    {
        "project": "en.wikipedia.org",
        "article": "John_Lithgow",
        "label": "John Lithgow"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Paapa_Essiedu",
        "label": "Paapa Essiedu"
    }
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


def _yyyymmdd00(dt):
    return dt.strftime("%Y%m%d00")


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


def _wiki_page_url(project, article):
    safe_article = quote(article, safe="")
    return f"https://{project}/wiki/{safe_article}"


def _wiki_api_url(project, article, start, end):
    article_encoded = quote(article, safe="")
    start_str = _yyyymmdd00(start)
    end_str = _yyyymmdd00(end)

    return (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{project}/all-access/user/{article_encoded}/daily/{start_str}/{end_str}"
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


def _history_path(snapshot_date):
    return os.path.join(HISTORY_DIR, f"day-{snapshot_date:%Y-%m-%d}.json")


def collect_google_news_week(start, end):
    results = []

    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)

    for query in NEWS_QUERIES:
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
                    "scope": "Google News RSS BR"
                })

            time.sleep(0.3)

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

    for query in YOUTUBE_QUERIES:
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

                title_lower = title.lower()
                description_lower = description.lower()
                channel_lower = channel.lower()

                allowed_channel = any(
                    br_channel in channel_lower
                    for br_channel in BR_CHANNELS
                )

                is_blocked = any(
                    blocked in title_lower
                    or blocked in description_lower
                    or blocked in channel_lower
                    for blocked in BLOCKED_YOUTUBE_SIGNALS
                )

                # Filtro BR radical: só entra canal brasileiro aprovado.
                if not allowed_channel:
                    continue

                if is_blocked:
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
                    "scope": "Video/Creator - YouTube BR"
                })

        except Exception as exc:
            print(f"[youtube] falha query='{query}': {exc}")

    results = _dedupe_coverage(results)

    print(f"[youtube] {len(results)} videos BR coletados na semana")

    return results


def _wiki_score_from_views(total_views):
    if total_views <= 0:
        return 0

    score = round(math.log10(total_views + 1) * 18)

    return max(1, min(100, score))


def collect_wikipedia_pageviews_week(start, end):
    headers = {
        "User-Agent": "lumos-fandom-intelligence/1.0 (github-actions; contact: anna)"
    }

    page_results = []
    total_views = 0

    for page in WIKI_PAGES:
        project = page["project"]
        article = page["article"]
        label = page["label"]
        url = _wiki_api_url(project, article, start, end)

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=TIMEOUT
            )

            print(
                f"[wiki] project='{project}' article='{article}' "
                f"{start.date()} to {end.date()} status={response.status_code}"
            )

            if response.status_code != 200:
                print("[wiki] resposta:", response.text[:300])
                continue

            data = response.json()
            items = data.get("items", [])

            views = sum(
                int(item.get("views", 0) or 0)
                for item in items
            )

            if views <= 0:
                continue

            total_views += views

            page_results.append({
                "project": project,
                "article": article,
                "label": label,
                "views": views,
                "url": _wiki_page_url(project, article)
            })

            time.sleep(0.3)

        except Exception as exc:
            print(f"[wiki] falha project='{project}' article='{article}': {exc}")

    page_results = sorted(
        page_results,
        key=lambda item: item["views"],
        reverse=True
    )

    top_page = page_results[0] if page_results else None
    score = _wiki_score_from_views(total_views)

    coverage = []

    if top_page and total_views > 0:
        coverage.append({
            "o": "Wikipedia Pageviews",
            "u": top_page["url"],
            "title": f"Interesse enciclopedico por '{top_page['label']}'",
            "cat": "neu",
            "time": _range_label(start, end),
            "scope": f"Wikipedia Pageviews - {total_views:,} views na semana".replace(",", ".")
        })

    print(
        f"[wiki] total_views={total_views} score={score} "
        f"top='{top_page['label'] if top_page else ''}'"
    )

    return {
        "score": score,
        "total_views": total_views,
        "top_page": top_page["label"] if top_page else "",
        "pages": page_results,
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

    if source.startswith("Wikipedia"):
        return "Wikipedia"

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
            "growth": "Baseado em fonte real coletada via Google News RSS, YouTube BR ou Wikipedia Pageviews",
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
                "d": f"Nao foram encontradas materias, videos BR ou sinais para a janela {week_label}.",
                "rec": "Manter monitoramento e validar novas fontes historicas."
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
            "d": "A janela teve fonte real ou sinal historico coletado, mas sem sinais criticos fortes.",
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
            "d": "Quando existe cobertura, video BR ou pageview, ha oportunidade de explicar como a serie pode aprofundar pontos nao explorados nos filmes."
        },
        {
            "ico": "film",
            "t": "Organizar narrativa de comparacao",
            "d": "Usar videos, conteudos editoriais e sinais historicos para posicionar a serie como nova leitura para streaming."
        }
    ]


def _empty_snapshot(snapshot_date, week_label):
    return {
        "label": week_label,
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
                "sub": "sem cobertura ou sinal real"
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
                "name": "Imprensa/YouTube BR/Wikipedia",
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
            "wiki_score": 0,
            "wiki_views": 0,
            "wiki_top_page": "",
            "backfill": True
        }
    }


def _snapshot_from_coverage(snapshot_date, week_label, coverage, wiki):
    coverage = _dedupe_coverage(coverage)[:12]

    pos, neu, neg, sentiment_index = _build_sentiment(coverage)
    net = pos - neg
    count = len(coverage)

    wiki_score = int((wiki or {}).get("score", 0) or 0)
    wiki_views = int((wiki or {}).get("total_views", 0) or 0)
    wiki_top_page = (wiki or {}).get("top_page", "")

    buzz_from_coverage = 20 + count * 8 + round(max(0, net) / 2) if count else 0
    buzz = min(100, max(buzz_from_coverage, wiki_score))

    youtube_count = sum(
        1 for item in coverage
        if str(item.get("o", "")).startswith("YouTube")
    )

    wiki_count = sum(
        1 for item in coverage
        if str(item.get("o", "")).startswith("Wikipedia")
    )

    press_count = count - youtube_count - wiki_count

    creators = []

    for item in coverage:
        outlet = str(item.get("o", ""))

        if outlet.startswith("YouTube"):
            creators.append({
                "h": outlet.replace("YouTube - ", ""),
                "pf": "YouTube",
                "type": "Video BR sobre Harry Potter HBO",
                "senti": _senti_from_cat(item.get("cat", "neu")),
                "reach": "nao coletado",
                "rel": 70,
                "risk": "low",
                "c": "#E7A94B",
                "u": item.get("u", "#")
            })

    return {
        "label": week_label,
        "updated": _stamp(),
        "kpi": {
            "mentions": {
                "v": f"{count} item" + ("" if count == 1 else "s"),
                "d": 0,
                "sub": f"{press_count} noticias - {youtube_count} videos YouTube BR - {wiki_count} sinais Wikipedia - {week_label}"
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
                "sub": f"buzz com Wikipedia {wiki_score}/100"
            }
        },
        "senti": {
            "pos": pos,
            "neu": neu,
            "neg": neg,
            "tone": "Backfill semanal baseado em Google News RSS, YouTube BR e Wikipedia Pageviews"
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
                "name": "YouTube BR",
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
                "name": "Wikipedia",
                "vol": max(wiki_score, 1),
                "senti": "neu",
                "ang": 160,
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
            "desc": f"Semana preenchida por fontes reais e sinais historicos. Janela: {week_label}.",
            "facts": [
                ["Janela", week_label],
                ["Marco", "25/03/2026"],
                ["Itens reais/sinais", str(count)],
                ["Wikipedia", f"{wiki_top_page or 'sem sinal'} - {wiki_views:,} views".replace(",", ".")]
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
            "wiki_score": wiki_score,
            "wiki_views": wiki_views,
            "wiki_top_page": wiki_top_page,
            "backfill": True,
            "sentiment_index": sentiment_index
        }
    }


def _collect_sources_for_range(start, end, youtube_key):
    coverage = []

    google_news_coverage = collect_google_news_week(start, end)
    coverage.extend(google_news_coverage)

    youtube_coverage = collect_youtube_week(start, end, youtube_key)
    coverage.extend(youtube_coverage)

    wiki = collect_wikipedia_pageviews_week(start, end)

    if wiki.get("coverage"):
        coverage.extend(wiki.get("coverage", []))

    return _dedupe_coverage(coverage), wiki


def _save_snapshot(snapshot_date, snapshot):
    os.makedirs(HISTORY_DIR, exist_ok=True)

    path = _history_path(snapshot_date)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)

    print(f"[backfill] snapshot salvo: {path}")


def _build_current_day(youtube_key):
    now = _now_br()
    start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=BR_TZ)
    end = now
    label = _label(now)

    coverage, wiki = _collect_sources_for_range(start, end, youtube_key)

    if coverage:
        snapshot = _snapshot_from_coverage(end, label, coverage, wiki)
        snapshot["label"] = label
        return snapshot

    return _empty_snapshot(end, label)


def _load_week_snapshots_from_history():
    weeks = {}

    if not os.path.exists(HISTORY_DIR):
        print(f"[backfill] HISTORY_DIR nao existe: {HISTORY_DIR}")
        return weeks

    files = []

    for name in os.listdir(HISTORY_DIR):
        if not name.startswith("day-") or not name.endswith(".json"):
            continue

        date_text = name.replace("day-", "").replace(".json", "")

        try:
            dt = datetime.fromisoformat(date_text).replace(tzinfo=BR_TZ)
        except Exception:
            continue

        files.append((dt, os.path.join(HISTORY_DIR, name)))

    files = sorted(files, key=lambda item: item[0], reverse=True)

    for index, (_, path) in enumerate(files):
        try:
            with open(path, encoding="utf-8") as file:
                snapshot = json.load(file)

            key = "w0" if index == 0 else f"w-{index}"
            weeks[key] = snapshot

        except Exception as exc:
            print(f"[backfill] nao consegui ler semana {path}: {exc}")

    print(f"[backfill] semanas carregadas do history: {len(weeks)}")

    return weeks


def regenerate_feed(current_day):
    if not current_day:
        current_day = _empty_snapshot(_now_br(), _label(_now_br()))

    weeks = _load_week_snapshots_from_history()

    feed = {
        "generated_at": _stamp(),
        "source": "backend automático",
        "tracking_start": "2026-03-25",
        "tracking_label": "Desde o lançamento do teaser",
        "titles": {
            TITLE_ID: {
                "label": "Harry Potter (HBO)",
                "topTitle": "Harry Potter — Série HBO Max",
                "topSub": "Daily Intelligence · mercado brasileiro",
                "days": {
                    "d0": current_day
                },
                "weeks": weeks
            }
        }
    }

    with open(OUTPUT_DATA, "w", encoding="utf-8") as file:
        json.dump(feed, file, ensure_ascii=False, indent=2)

    print("[backfill] data.json regenerado diretamente com days + weeks do history.")


def main():
    youtube_key = os.environ.get("YOUTUBE_API_KEY", "").strip()

    if youtube_key:
        print(f"[backfill] YouTube key detectada com {len(youtube_key)} caracteres")
    else:
        print("[backfill] YOUTUBE_API_KEY nao configurada. YouTube sera ignorado.")

    print("[backfill] inicio")
    print("[backfill] fonte principal: Google News RSS BR + YouTube BR + Wikipedia Pageviews")
    print("[backfill] marco: teaser em 25/03/2026")
    print(f"[backfill] hoje: {_now_br():%Y-%m-%d %H:%M}")

    now = _now_br()

    start = TEASER_DATE
    week_index = 1

    while start <= now:
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        if end > now:
            end = now

        week_label = _range_label(start, end)

        print(f"[backfill] Semana {week_index}: {week_label}")

        try:
            coverage, wiki = _collect_sources_for_range(start, end, youtube_key)

            print(f"[backfill] {len(coverage)} itens reais/sinais na semana {week_label}")

            if coverage:
                snapshot = _snapshot_from_coverage(end, week_label, coverage, wiki)
                _save_snapshot(end, snapshot)
            else:
                snapshot = _empty_snapshot(end, week_label)
                _save_snapshot(end, snapshot)

        except Exception as exc:
            print(f"[backfill] erro na semana {week_label}: {exc}")

            snapshot = _empty_snapshot(end, week_label)
            _save_snapshot(end, snapshot)

        time.sleep(1)

        start = start + timedelta(days=7)
        week_index += 1

    current_day = _build_current_day(youtube_key)
    regenerate_feed(current_day)

    print("[backfill] concluido")


if __name__ == "__main__":
    main()
