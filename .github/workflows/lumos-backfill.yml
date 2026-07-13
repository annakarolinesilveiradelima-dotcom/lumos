from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
import build_data

try:
    import social_google_news
except Exception:
    social_google_news = None

try:
    import social_youtube
except Exception:
    social_youtube = None

try:
    import social_reddit
except Exception:
    social_reddit = None


BR_TZ = ZoneInfo("America/Sao_Paulo")
TEASER_DATE = datetime(2026, 3, 25, 0, 0, 0, tzinfo=BR_TZ)

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
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

        key = (url.split("?")[0] + "|" + title).lower()

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


def _platform_from_outlet(outlet):
    outlet = str(outlet or "")

    if outlet.startswith("Reddit"):
        return "Reddit"

    if outlet.startswith("YouTube"):
        return "YouTube"

    if outlet == "Google News" or "Google News" in outlet:
        return "Imprensa"

    return "Imprensa"


def _narratives_from_coverage(coverage):
    narratives = []

    for item in coverage[:6]:
        platform = _platform_from_outlet(item.get("o", "Fonte"))

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


def _risks_from_coverage(coverage, week_label):
    if not coverage:
        return [
            {
                "t": "Semana sem cobertura social/editorial real",
                "sev": "low",
                "d": f"Nao foram encontradas materias, videos ou posts reais para a janela {week_label}.",
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
            "d": "Materias, videos ou posts sobre escalacao podem gerar discussao sobre aderencia ao imaginario dos fas.",
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
            "d": "Usar videos, conteudos editoriais e discussoes de fandom para posicionar a serie como uma nova leitura para streaming."
        }
    ]


def _empty_snapshot(snapshot_date, week_label):
    return {
        "label": _label(snapshot_date),
        "updated": _stamp(),
        "kpi": {
            "mentions": {
                "v": "0 materias/videos/posts",
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
                "name": "Imprensa/YouTube/Reddit",
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
            "unit": "materias/videos/posts",
            "net": 0,
            "buzz": 0,
            "news_count": 0,
            "youtube_count": 0,
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

    youtube_count = sum(
        1 for item in coverage
        if str(item.get("o", "")).startswith("YouTube")
    )

    press_count = count - reddit_count - youtube_count

    platforms = [
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
    ]

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
                "sub": f"{press_count} noticias - {youtube_count} videos YouTube - {reddit_count} posts Reddit - {week_label}"
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
            "tone": "Backfill semanal baseado em Google News, YouTube e Reddit opcionais"
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
        "platforms": platforms,
        "narratives": narratives,
        "coverage": coverage[:8],
        "creators": creators[:8],
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
            "unit": "materias/videos/posts",
            "net": net,
            "buzz": buzz,
            "news_count": press_count,
            "youtube_count": youtube_count,
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


def _collect_sources_for_range(start, end, youtube_key, enable_reddit):
    coverage = []

    if social_google_news is not None:
        google_news_coverage = social_google_news.collect_google_news_week(start, end)
        coverage.extend(google_news_coverage)
    else:
        print("[backfill] social_google_news nao disponivel.")

    if social_youtube is not None and youtube_key:
        youtube_coverage = social_youtube.collect_youtube_week(start, end, youtube_key)
        coverage.extend(youtube_coverage)
    else:
        print("[backfill] YouTube ignorado nesta execucao.")

    if enable_reddit and social_reddit is not None:
        reddit_coverage = social_reddit.collect_reddit_week(start, end)
        coverage.extend(reddit_coverage)
    else:
        print("[backfill] Reddit ignorado nesta execucao.")

    return _dedupe_coverage(coverage)


def _build_current_day(youtube_key, enable_reddit):
    now = _now_br()
    start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=BR_TZ)
    end = now
    label = _label(now)

    coverage = _collect_sources_for_range(start, end, youtube_key, enable_reddit)

    if coverage:
        snapshot = _snapshot_from_coverage(end, label, coverage)
        snapshot["label"] = label
        return snapshot

    return _empty_snapshot(end, label)


def _load_current_day_fallback():
    try:
        with open(config.OUTPUT_DATA, encoding="utf-8") as file:
            feed = json.load(file)

        current_day = feed["titles"][config.TITLE_ID]["days"]["d0"]

        if current_day and current_day.get("coverage"):
            return current_day

    except Exception as exc:
        print(f"[backfill] nao consegui ler d0 atual do data.json: {exc}")

    return None


def regenerate_feed(current_day):
    if not current_day:
        current_day = _load_current_day_fallback()

    if not current_day:
        current_day = _empty_snapshot(_now_br(), _label(_now_br()))

    feed = build_data.build_feed(current_day)
    build_data.write_feed(feed)

    print("[backfill] data.json regenerado com Google News RSS.")


def main():
    youtube_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    enable_reddit = os.environ.get("ENABLE_REDDIT", "").lower() in ("1", "true", "yes")

    if youtube_key:
        print(f"[backfill] YouTube key detectada com {len(youtube_key)} caracteres")
    else:
        print("[backfill] YOUTUBE_API_KEY nao configurada. YouTube sera ignorado.")

    print("[backfill] inicio")
    print("[backfill] fonte principal: Google News RSS")
    print("[backfill] marco: teaser em 25/03/2026")
    print(f"[backfill] hoje: {_now_br():%Y-%m-%d %H:%M}")

    start = TEASER_DATE
    now = _now_br()
    week_index = 1

    while start <= now:
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        if end > now:
            end = now

        week_label = _range_label(start, end)

        print(f"[backfill] Semana {week_index}: {week_label}")

        try:
            coverage = _collect_sources_for_range(start, end, youtube_key, enable_reddit)

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

        time.sleep(2)

        start = start + timedelta(days=7)
        week_index += 1

    current_day = _build_current_day(youtube_key, enable_reddit)
    regenerate_feed(current_day)

    print("[backfill] concluido")


if __name__ == "__main__":
    main()
