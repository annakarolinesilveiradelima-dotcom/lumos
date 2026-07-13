from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

import config
import build_data

try:
    import social_reddit
except Exception:
    social_reddit = None


TIMEOUT = 25
BR_TZ = ZoneInfo("America/Sao_Paulo")
TEASER_DATE = datetime(2026, 3, 25, 0, 0, 0, tzinfo=BR_TZ)

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]


def _now_br():
    return datetime.now(BR_TZ)


def _iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _label(dt):
    return f"{dt.day} {PT_MONTHS[dt.month - 1]} {dt.year}"


def _stamp(dt):
    now = _now_br()
    return f"{_label(now)}, {now:%H:%M}"


def _range_label(start, end):
    if start.month == end.month:
        return f"{start.day}-{end.day} {PT_MONTHS[end.month - 1]} {end.year}"

    return (
        f"{start.day} {PT_MONTHS[start.month - 1]}-"
        f"{end.day} {PT_MONTHS[end.month - 1]} {end.year}"
    )


def _parse_dt(value):
    if not value:
        return ""

    try:
        if isinstance(value, str) and value.endswith("Z"):
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(timezone.utc).isoformat()

        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()

    except Exception:
        try:
            return datetime.fromisoformat(str(value)).astimezone(timezone.utc).isoformat()
        except Exception:
            return str(value)


def _format_time(value):
    parsed = _parse_dt(value)

    if not parsed:
        return "sem horario disponivel"

    try:
        dt = datetime.fromisoformat(str(parsed).replace("Z", "+00:00")).astimezone(BR_TZ)
        return f"{dt.day} {PT_MONTHS[dt.month - 1]}, {dt:%H:%M}"
    except Exception:
        return str(value)[:40]


def _clean_title(title):
    return re.sub(r"\s+", " ", (title or "")).strip()


def _cat(text):
    t = (text or "").lower()

    if re.search(r"rumor|especula|supost|vaza|vazou|pode|possivel|teria|leak|leaked", t):
        return "esp"

    if re.search(r"nostalg|filmes|classic|classico|trilha|infancia|reboot|movies|original cast", t):
        return "nos"

    if re.search(r"critic|polem|decep|rejeit|problema|desnecess|medo|hate|worried|terrible|ruined", t):
        return "neg"

    if re.search(r"elogi|acerto|fiel|ansios|empolg|aprova|confirma|revela|estreia|elenco|excited|love|perfect|faithful", t):
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


def _dedupe_coverage(items):
    seen = set()
    out = []

    for item in items:
        url = item.get("u", "")
        title = item.get("title", "")

        if not url or not title:
            continue

        if "news.google.com" in url:
            continue

        key = url.split("?")[0].lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


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


def _narratives_from_coverage(coverage):
    narratives = []

    for item in coverage[:6]:
        outlet = str(item.get("o", "Fonte"))

        if outlet.startswith("Reddit"):
            platform = "Reddit"
        else:
            platform = "Imprensa"

        narratives.append({
            "t": item.get("title", "Cobertura real coletada"),
            "vol": 1,
            "senti": _senti_from_cat(item.get("cat", "neu")),
            "pf": platform,
            "trend": "flat",
            "growth": "Backfill historico desde o teaser; baseado em fonte real coletada",
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


class CombinedResponse:
    def __init__(self, status_code, articles=None, text=""):
        self.status_code = status_code
        self._articles = articles or []
        self.text = text

    def json(self):
        return {
            "articles": self._articles
        }

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.text)


def _gnews_request(api_key, start, end):
    queries = [
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

    all_articles = []
    last_status = 200
    last_error_text = ""

    for query in queries:
        params = {
            "q": query,
            "max": 10,
            "from": _iso_utc(start),
            "to": _iso_utc(end),
            "sortby": "publishedAt",
            "apikey": api_key
        }

        response = requests.get(
            "https://gnews.io/api/v4/search",
            params=params,
            timeout=TIMEOUT
        )

        print(
            f"[backfill] GNews query='{query}' "
            f"{start.date()} to {end.date()} status={response.status_code}"
        )

        if response.status_code == 200:
            data = response.json()
            articles = data.get("articles", [])

            print(f"[backfill] query='{query}' retornou {len(articles)} artigos")

            all_articles.extend(articles)

            if len(all_articles) >= 10:
                break

            time.sleep(1)
            continue

        last_status = response.status_code
        last_error_text = response.text[:800]

        print("[backfill] resposta GNews:", last_error_text)

        if response.status_code in (401, 403, 429):
            if all_articles:
                print("[backfill] limite/erro apos coletar alguns artigos; salvando itens ja encontrados.")
                return CombinedResponse(200, all_articles, last_error_text)

            return CombinedResponse(response.status_code, [], last_error_text)

        time.sleep(1)

    print(
        f"[backfill] total combinado da semana "
        f"{start.date()} to {end.date()}: {len(all_articles)} artigos"
    )

    return CombinedResponse(last_status, all_articles, last_error_text)


def _coverage_from_articles(articles):
    coverage = []

    for article in articles:
        source = article.get("source") or {}
        outlet = source.get("name", "Imprensa")
        url = article.get("url", "")

        if not url:
            continue

        if "news.google.com" in url:
            continue

        title = _clean_title(article.get("title", ""))
        summary = article.get("description", "")

        if not title:
            continue

        cat = _cat(title + " " + summary)

        coverage.append({
            "o": outlet,
            "u": url,
            "title": title,
            "cat": cat,
            "time": _format_time(article.get("publishedAt", "")),
            "scope": "Portal BR"
        })

    return _dedupe_coverage(coverage)


def _risks_from_coverage(coverage, week_label):
    if not coverage:
        return [
            {
                "t": "Semana sem cobertura social/editorial real",
                "sev": "low",
                "d": f"Nao foram encontradas materias ou posts reais para a janela {week_label}.",
                "rec": "Manter monitoramento e ampliar fontes gratuitas como Google Trends e YouTube."
            }
        ]

    titles = " ".join(item.get("title", "") for item in coverage).lower()
    risks = []

    if any(w in titles for w in ["reboot", "filmes", "movies", "nostalg"]):
        risks.append({
            "t": "Comparacao com os filmes originais",
            "sev": "mid",
            "d": "A cobertura/conversa pode reacender comparacao com a saga original e expectativa de fidelidade aos livros.",
            "rec": "Reforcar que a serie e uma nova adaptacao com espaco para aprofundamento narrativo."
        })

    if any(w in titles for w in ["cast", "casting", "elenco", "ator", "atriz"]):
        risks.append({
            "t": "Sensibilidade em torno de elenco",
            "sev": "mid",
            "d": "Materias ou posts sobre escalacao podem gerar discussao sobre aderencia ao imaginario dos fas.",
            "rec": "Acompanhar comentarios e preparar mensagens sobre intencao criativa e construcao de personagens."
        })

    if not risks:
        risks.append({
            "t": "Risco baixo na janela",
            "sev": "low",
            "d": "A semana teve fonte real coletada, mas sem sinais criticos fortes.",
            "rec": "Manter monitoramento e registrar mudancas de tom nas proximas coletas."
        })

    return risks[:3]


def _opps_from_coverage(coverage, week_label):
    if not coverage:
        return [
            {
                "ico": "mail",
                "t": "Monitorar proxima coleta",
                "d": f"A janela {week_label} ainda nao tem fonte real suficiente. Proximo passo: manter backfill/monitoramento."
            }
        ]

    return [
        {
            "ico": "book",
            "t": "Explorar fidelidade aos livros",
            "d": "Quando a cobertura ou conversa cita adaptacao, personagens ou elenco, existe oportunidade de explicar como a serie pode aprofundar pontos nao explorados nos filmes."
        },
        {
            "ico": "film",
            "t": "Organizar narrativa de comparacao",
            "d": "Usar conteudos editoriais e discussoes de fandom para posicionar a serie como uma nova leitura para streaming."
        }
    ]


def _empty_snapshot(snapshot_date, week_label):
    return {
        "label": _label(snapshot_date),
        "updated": _stamp(snapshot_date),
        "kpi": {
            "mentions": {
                "v": "0 materias/posts",
                "d": 0,
                "sub": f"sem cobertura real nesta semana - {week_label}"
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
                "sub": "sem cobertura real"
            }
        },
        "senti": {
            "pos": 0,
            "neu": 100,
            "neg": 0,
            "tone": "Sem cobertura real coletada nesta semana"
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
                "name": "Imprensa/Reddit",
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
                ["Status", "sem cobertura real"]
            ]
        },
        "opps": _opps_from_coverage([], week_label),
        "ephem": [],
        "_raw": {
            "base_count": 0,
            "unit": "materias/posts",
            "net": 0,
            "buzz": 0,
            "news_count": 0,
            "social_mentions": 0,
            "backfill": True
        }
    }


def _snapshot_from_coverage(snapshot_date, week_label, coverage):
    coverage = _dedupe_coverage(coverage)[:12]

    pos, neu, neg, sentiment_index = _build_sentiment(coverage)

    net = pos - neg
    count = len(coverage)
    buzz = min(100, 20 + count * 8 + round(max(0, net) / 2))

    narratives = _narratives_from_coverage(coverage)

    reddit_count = sum(
        1 for item in coverage
        if str(item.get("o", "")).startswith("Reddit")
    )

    press_count = count - reddit_count

    return {
        "label": _label(snapshot_date),
        "updated": _stamp(snapshot_date),
        "kpi": {
            "mentions": {
                "v": f"{count} item" + ("" if count == 1 else "s"),
                "d": 0,
                "sub": f"{press_count} noticias - {reddit_count} posts Reddit - {week_label}"
            },
            "sentiment": {
                "v": ("+" if net >= 0 else "") + str(net),
                "suf": "/100",
                "d": 0,
                "sub": "indice semanal por cobertura"
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
                "sub": "buzz semanal desde o teaser"
            }
        },
        "senti": {
            "pos": pos,
            "neu": neu,
            "neg": neg,
            "tone": "Backfill semanal baseado em noticias e Reddit reais"
        },
        "buzz7": [count, count, count, count, count, count, count],
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
                "name": "Reddit",
                "vol": max(reddit_count, 1),
                "senti": "pos" if pos >= 55 else "neg" if neg >= 35 else "neu",
                "ang": 128,
                "s": {
                    "p": pos,
                    "n": neg,
                    "g": neu
                }
            }
        ],
        "narratives": narratives,
        "coverage": coverage[:8],
        "creators": [],
        "risks": _risks_from_coverage(coverage, week_label),
        "heroOpp": {
            "title": "Leitura semanal desde o teaser",
            "desc": f"Semana preenchida por fontes reais. Janela: {week_label}.",
            "facts": [
                ["Janela", week_label],
                ["Marco", "25/03/2026"],
                ["Itens reais", str(count)],
                ["Dados ficticios", "nao"]
            ]
        },
        "opps": _opps_from_coverage(coverage, week_label),
        "ephem": [],
        "_raw": {
            "base_count": count,
            "unit": "materias/posts",
            "net": net,
            "buzz": buzz,
            "news_count": press_count,
            "social_mentions": reddit_count,
            "backfill": True,
            "sentiment_index": sentiment_index
        }
    }


def _save_snapshot(snapshot_date, snapshot):
    os.makedirs(config.HISTORY_DIR, exist_ok=True)

    path = os.path.join(config.HISTORY_DIR, f"day-{snapshot_date:%Y-%m-%d}.json")

    with open(path, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)

    print(f"[backfill] snapshot salvo: {path}")


def _load_current_day_or_latest_snapshot():
    try:
        with open(config.OUTPUT_DATA, encoding="utf-8") as file:
            feed = json.load(file)

        current_day = feed["titles"][config.TITLE_ID]["days"]["d0"]

        if current_day:
            return current_day

    except Exception as exc:
        print(f"[backfill] nao consegui ler d0 atual do data.json: {exc}")

    if os.path.exists(config.HISTORY_DIR):
        files = sorted(
            file_name
            for file_name in os.listdir(config.HISTORY_DIR)
            if file_name.startswith("day-") and file_name.endswith(".json")
        )

        if files:
            latest = os.path.join(config.HISTORY_DIR, files[-1])

            with open(latest, encoding="utf-8") as file:
                return json.load(file)

    return _empty_snapshot(_now_br(), "sem dados")


def regenerate_feed():
    current_day = _load_current_day_or_latest_snapshot()
    feed = build_data.build_feed(current_day)
    build_data.write_feed(feed)
    print("[backfill] data.json regenerado com weeks desde o teaser.")


def main():
    api_key = os.environ.get("GNEWS_API_KEY", "").strip()

    if not api_key:
        print("[backfill] GNEWS_API_KEY nao configurada. Seguindo sem GNews.")
    else:
        print(f"[backfill] API key detectada com {len(api_key)} caracteres")

    now = _now_br()

    print("[backfill] inicio")
    print("[backfill] marco: teaser em 25/03/2026")
    print(f"[backfill] hoje: {now:%Y-%m-%d %H:%M}")

    if social_reddit is None:
        print("[backfill] social_reddit nao disponivel. Reddit sera ignorado.")
    else:
        print("[backfill] social_reddit disponivel. Reddit sera incluido.")

    start = TEASER_DATE
    week_index = 1
    hit_rate_limit = False

    while start <= now:
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        if end > now:
            end = now

        week_label = _range_label(start, end)

        print(f"[backfill] Semana {week_index}: {week_label}")

        coverage = []
        response = CombinedResponse(200, [])

        if api_key:
            response = _gnews_request(api_key, start, end)

            if response.status_code in (403, 429):
                print("[backfill] limite/plano da GNews atingido. Salvando ate aqui e encerrando sem falhar.")

            if response.status_code == 401:
                print("[backfill] GNews retornou 401. Chave invalida. Encerrando sem falhar.")
                hit_rate_limit = True

        try:
            if response.status_code == 200:
                data = response.json()
                articles = data.get("articles", [])
                coverage.extend(_coverage_from_articles(articles))

            if social_reddit is not None:
                reddit_coverage = social_reddit.collect_reddit_week(start, end)
                coverage.extend(reddit_coverage)

            coverage = _dedupe_coverage(coverage)

            print(f"[backfill] {len(coverage)} itens reais na semana {week_label}")

            if coverage:
                snapshot = _snapshot_from_coverage(end, week_label, coverage)
            else:
                snapshot = _empty_snapshot(end, week_label)

            _save_snapshot(end, snapshot)

        except Exception as exc:
            print(f"[backfill] erro na semana {week_label}: {exc}")
            snapshot = _empty_snapshot(end, week_label)
            _save_snapshot(end, snapshot)

        if response.status_code in (401, 403, 429):
            hit_rate_limit = True
            break

        time.sleep(2)

        start = start + timedelta(days=7)
        week_index += 1

    regenerate_feed()

    if hit_rate_limit:
        print("[backfill] concluido parcialmente por limite/plano da API.")
    else:
        print("[backfill] concluido")


if __name__ == "__main__":
    main()
