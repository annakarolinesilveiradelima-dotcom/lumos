"""
Lumos build_data.py

Monta o data.json no contrato do Lumos.

Comportamento:
- Diário = execução atual.
- Semanal = semanas desde o teaser de 25/03/2026.
- w0 = semana atual desde o teaser.
- w-1, w-2... = semanas anteriores.
- As semanas são montadas pela DATA REAL DA MATÉRIA, não pela data em que o backfill rodou.
- Sem dado real em uma semana, deixa vazio/honesto.
"""

from __future__ import annotations

import glob
import html
import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

BR_TZ = ZoneInfo("America/Sao_Paulo")
TEASER_DATE = datetime(2026, 3, 25, tzinfo=BR_TZ)


def _now_br():
    return datetime.now(BR_TZ)


def _label(dt):
    return f"{dt.day} {PT_MONTHS[dt.month - 1]} {dt.year}"


def _stamp(dt):
    return f"{_label(dt)}, {dt:%H:%M}"


def _range_label(start, end):
    if start.month == end.month:
        return f"{start.day}–{end.day} {PT_MONTHS[end.month - 1]} {end.year}"

    return (
        f"{start.day} {PT_MONTHS[start.month - 1]}–"
        f"{end.day} {PT_MONTHS[end.month - 1]} {end.year}"
    )


def _clean_url(raw_url):
    """
    Garante que o campo de URL fique como URL pura.
    Se por acidente vier HTML tipo ......</a>, extrai só o href.
    """
    if not raw_url:
        return ""

    value = html.unescape(str(raw_url)).strip()

    href_match = re.search(r'href=[^"\']+["\']', value)
    if href_match:
        value = href_match.group(1)

    value = value.replace("&quot;", "")
    value = value.replace('"', "")
    value = value.replace("'", "")
    value = value.strip()

    # Remove vírgula final que às vezes aparece se o valor foi copiado/renderizado errado
    value = value.rstrip(",")

    return value


def _parse_date_from_label(label):
    """
    Tenta extrair data no formato '8 jul 2026' de labels salvos no histórico.
    """
    if not label:
        return None

    parts = str(label).split()

    if len(parts) < 3:
        return None

    try:
        day = int(parts[0])
        month = PT_MONTHS.index(parts[1].lower()) + 1
        year = int(parts[2])

        return datetime(year, month, day, tzinfo=BR_TZ)
    except Exception:
        return None


def _parse_article_date(time_value):
    """
    Interpreta datas de matérias no formato:
    - '8 jul, 14:30'
    - '15 jun, 22:00'
    - '4 jul, 18:28'

    Como o campo não traz ano, usa o ano atual do tracking: 2026.
    """
    if not time_value:
        return None

    try:
        clean = str(time_value).replace(",", "")
        parts = clean.split()

        if len(parts) < 3:
            return None

        day = int(parts[0])
        month = PT_MONTHS.index(parts[1].lower()) + 1
        hour_min = parts[2]

        hour, minute = hour_min.split(":")

        return datetime(
            2026,
            month,
            day,
            int(hour),
            int(minute),
            tzinfo=BR_TZ
        )
    except Exception:
        return None


def _load_history_days():
    files = sorted(glob.glob(os.path.join(config.HISTORY_DIR, "day-*.json")))
    days = []

    for file_name in files:
        try:
            with open(file_name, encoding="utf-8") as file:
                day = json.load(file)

            days.append(day)
        except Exception:
            continue

    return days


def _latest_prev_day():
    days = _load_history_days()

    if not days:
        return None

    return days[-1]


def _delta(curr, prev):
    try:
        if prev is None:
            return 0

        return round(curr - prev)
    except Exception:
        return 0


def _human(n, unit="menções"):
    if unit == "matérias":
        return f"{n} matéria" + ("" if n == 1 else "s")

    if n >= 1000:
        return f"{n / 1000:.1f} mil".replace(".", ",")

    return str(n)


def _platforms_news_only(news_count, analysis):
    p = int(analysis.get("pos", 0))
    g = int(analysis.get("neu", 100))
    n = int(analysis.get("neg", 0))

    if p >= 55:
        senti = "pos"
    elif n >= 35:
        senti = "neg"
    else:
        senti = "neu"

    return [
        {
            "name": "Imprensa",
            "vol": max(news_count, 1),
            "senti": senti,
            "ang": -90,
            "s": {
                "p": p,
                "n": n,
                "g": g
            }
        }
    ]


def _platforms_from_social(social):
    angles = {
        "TikTok": -90,
        "X/Twitter": -38,
        "Instagram": 16,
        "YouTube": 70,
        "Reddit": 128,
        "Threads": 182,
        "Tumblr": 232
    }

    out = []

    for name, s in social.items():
        mentions = max(int(s.get("mentions", 0) or 0), 0)

        if mentions <= 0:
            continue

        pos = round(int(s.get("pos", 0) or 0) / max(mentions, 1) * 100)
        neg = round(int(s.get("neg", 0) or 0) / max(mentions, 1) * 100)
        neu = max(0, 100 - pos - neg)

        if pos >= 55:
            senti = "pos"
        elif neg >= 35:
            senti = "neg"
        elif abs(pos - neg) < 12:
            senti = "div"
        else:
            senti = "neu"

        out.append({
            "name": name,
            "vol": mentions,
            "senti": senti,
            "ang": angles.get(name, 0),
            "s": {
                "p": pos,
                "n": neg,
                "g": neu
            }
        })

    return out


def _series(prev, key, today):
    old = (prev or {}).get(key, [])
    series = (old[1:] if len(old) >= 7 else old) + [today]

    while len(series) < 7:
        series.insert(0, today)

    return series[-7:]


def _buzz_score(base_count, sentiment_index):
    return min(
        100,
        20 + min(40, base_count * 4) + round(max(0, sentiment_index) / 2)
    )


def _cat_to_senti(cat):
    if cat in ("pos", "nos"):
        return "pos"

    if cat == "neg":
        return "neg"

    if cat == "esp":
        return "div"

    return "neu"


def _dedupe_coverage(items):
    seen = set()
    out = []

    for item in items:
        url = _clean_url(item.get("u", ""))
        title = str(item.get("title", "")).strip()

        if not url or not title:
            continue

        if "news.google.com" in url:
            continue

        clean_item = dict(item)
        clean_item["u"] = url
        clean_item["title"] = title

        key = url.split("?")[0].lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(clean_item)

    return out


def _coverage_from_all_days(days):
    """
    Pega todas as matérias reais encontradas no histórico e no dia atual.
    Depois as semanas vão ser montadas pela data real da matéria.
    """
    coverage = []

    for day in days:
        for item in day.get("coverage", []) or []:
            clean_item = dict(item)
            clean_item["u"] = _clean_url(clean_item.get("u", ""))
            coverage.append(clean_item)

    return _dedupe_coverage(coverage)


def _narratives_from_coverage(coverage):
    narratives = []

    for item in coverage[:6]:
        narratives.append({
            "t": item.get("title", "Cobertura real coletada"),
            "vol": 1,
            "senti": _cat_to_senti(item.get("cat", "neu")),
            "pf": "Imprensa",
            "trend": "flat",
            "growth": "Baseado em cobertura real da semana; social listening não conectado",
            "q": "",
            "pct": 50,
            "src": [
                {
                    "o": item.get("o", "Imprensa"),
                    "u": _clean_url(item.get("u", "#"))
                }
            ]
        })

    return narratives


def _risks_from_coverage(coverage, label):
    if not coverage:
        return [
            {
                "t": "Semana sem cobertura real",
                "sev": "low",
                "d": f"Não foram encontradas matérias reais para a janela {label}.",
                "rec": "Manter monitoramento e validar se a API possui histórico disponível para essa semana."
            }
        ]

    titles = " ".join(item.get("title", "") for item in coverage).lower()

    risks = []

    if "reboot" in titles or "filmes" in titles or "nostalg" in titles:
        risks.append({
            "t": "Comparação com os filmes originais",
            "sev": "mid",
            "d": "A cobertura pode reacender comparação com a saga original e expectativa de fidelidade aos livros.",
            "rec": "Reforçar que a série é uma nova adaptação com espaço para aprofundamento narrativo."
        })

    if "elenco" in titles or "ator" in titles or "atriz" in titles:
        risks.append({
            "t": "Sensibilidade em torno de elenco",
            "sev": "mid",
            "d": "Matérias sobre escalação podem gerar discussão sobre aderência ao imaginário dos fãs.",
            "rec": "Acompanhar comentários e preparar mensagens sobre intenção criativa e construção de personagens."
        })

    if not risks:
        risks.append({
            "t": "Risco baixo na cobertura editorial",
            "sev": "low",
            "d": "A semana teve cobertura real, mas sem sinais críticos fortes na camada de notícias.",
            "rec": "Manter monitoramento e registrar mudanças de tom nas próximas coletas."
        })

    return risks[:3]


def _opps_from_coverage(coverage, label):
    if not coverage:
        return [
            {
                "ico": "mail",
                "t": "Monitorar próxima coleta",
                "d": f"A janela {label} ainda não tem matérias reais na fonte conectada. Próximo passo: manter backfill/monitoramento."
            }
        ]

    opps = [
        {
            "ico": "book",
            "t": "Explorar fidelidade aos livros",
            "d": "Quando a cobertura cita adaptação, personagens ou elenco, existe oportunidade de explicar como a série pode aprofundar pontos não explorados nos filmes."
        },
        {
            "ico": "film",
            "t": "Organizar narrativa de comparação",
            "d": "Usar conteúdos editoriais para posicionar a série como uma nova leitura para streaming, não como substituição direta dos filmes."
        }
    ]

    return opps[:4]


def build_day(collected, analysis):
    now = _now_br()
    prev = _latest_prev_day()

    social = collected.get("social", {}) or {}
    news = collected.get("news", []) or []

    social_mentions = sum(int(v.get("mentions", 0) or 0) for v in social.values())
    news_count = len(news)

    has_social = social_mentions > 0

    if has_social:
        base_count = social_mentions
        unit = "menções"
        mentions_sub = "vs. ontem"
    else:
        base_count = news_count
        unit = "matérias"
        mentions_sub = "cobertura real coletada"

    prev_raw = (prev or {}).get("_raw", {})

    sentiment_index = int(analysis.get("sentiment_index", 50))
    net = (sentiment_index - 50) * 2
    buzz = _buzz_score(base_count, sentiment_index)

    if has_social:
        platforms = _platforms_from_social(social)
    else:
        platforms = _platforms_news_only(news_count, analysis)

    clean_coverage = _dedupe_coverage(analysis.get("coverage", [])[:12])

    day = {
        "label": _label(now),
        "updated": _stamp(now),
        "kpi": {
            "mentions": {
                "v": _human(base_count, unit),
                "d": _delta(base_count, prev_raw.get("base_count")),
                "sub": mentions_sub
            },
            "sentiment": {
                "v": ("+" if net >= 0 else "") + str(net),
                "suf": "/100",
                "d": _delta(net, prev_raw.get("net")),
                "sub": "índice líquido do dia"
            },
            "sov": {
                "v": "—",
                "d": 0,
                "dtype": "pts",
                "sub": "requer base multi-título"
            },
            "buzz": {
                "v": str(buzz),
                "suf": "/100",
                "d": _delta(buzz, prev_raw.get("buzz")),
                "sub": "índice de buzz do dia"
            }
        },
        "senti": {
            "pos": int(analysis.get("pos", 0)),
            "neu": int(analysis.get("neu", 100)),
            "neg": int(analysis.get("neg", 0)),
            "tone": analysis.get("tone", "—")
        },
        "buzz7": _series(
            prev,
            "buzz7",
            round(base_count / 1000, 1) if has_social else base_count
        ),
        "stack": _series(
            prev,
            "stack",
            [
                int(analysis.get("pos", 0)),
                int(analysis.get("neu", 100)),
                int(analysis.get("neg", 0))
            ]
        ),
        "platforms": platforms,
        "narratives": _narratives_from_coverage(clean_coverage),
        "coverage": clean_coverage[:8],
        "creators": [],
        "risks": _risks_from_coverage(clean_coverage, _label(now)),
        "heroOpp": analysis.get("heroOpp") or {
            "title": "Acompanhar cobertura do dia",
            "desc": "A leitura atual usa apenas matérias reais coletadas. Para recomendações sociais e creators, conecte Brandwatch/Meltwater/Stilingue/Sprinklr via export.",
            "facts": [
                ["Fonte", "notícias reais"],
                ["Matérias", str(len(clean_coverage))],
                ["Social", "não conectado"],
                ["Dados fictícios", "não"]
            ]
        },
        "opps": _opps_from_coverage(clean_coverage, _label(now)),
        "ephem": [],
        "_raw": {
            "base_count": base_count,
            "unit": unit,
            "net": net,
            "buzz": buzz,
            "news_count": news_count,
            "social_mentions": social_mentions
        }
    }

    return day


def _empty_week(start, end, label):
    return {
        "label": label,
        "updated": _stamp(_now_br()),
        "kpi": {
            "mentions": {
                "v": "0 matérias",
                "d": 0,
                "sub": "sem cobertura real nesta semana"
            },
            "sentiment": {
                "v": "—",
                "suf": "",
                "d": 0,
                "sub": "sem base suficiente"
            },
            "sov": {
                "v": "—",
                "d": 0,
                "dtype": "pts",
                "sub": "requer base multi-título"
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
                "name": "Imprensa",
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
        "risks": _risks_from_coverage([], label),
        "heroOpp": {
            "title": "Sem oportunidade validada nesta semana",
            "desc": "Não houve cobertura real suficiente nesta janela semanal.",
            "facts": [
                ["Janela", label],
                ["Marco", "teaser 25/03/2026"],
                ["Dados fictícios", "não"],
                ["Status", "sem cobertura real"]
            ]
        },
        "opps": _opps_from_coverage([], label),
        "ephem": []
    }


def _build_week_from_coverage(all_coverage, start, end, label):
    selected = []

    for item in all_coverage:
        article_dt = _parse_article_date(item.get("time"))

        if not article_dt:
            continue

        if start.date() <= article_dt.date() <= end.date():
            selected.append(item)

    selected = _dedupe_coverage(selected)

    if not selected:
        return _empty_week(start, end, label)

    count = len(selected)

    pos_count = sum(1 for item in selected if item.get("cat") in ("pos", "nos"))
    neg_count = sum(1 for item in selected if item.get("cat") == "neg")

    pos = round(pos_count / count * 100) if count else 0
    neg = round(neg_count / count * 100) if count else 0
    neu = max(0, 100 - pos - neg)

    net = pos - neg
    buzz = min(100, 20 + count * 8 + round(max(0, net) / 2))

    narratives = _narratives_from_coverage(selected)
    risks = _risks_from_coverage(selected, label)
    opps = _opps_from_coverage(selected, label)

    return {
        "label": label,
        "updated": _stamp(_now_br()),
        "kpi": {
            "mentions": {
                "v": _human(count, "matérias"),
                "d": 0,
                "sub": "semana desde o teaser"
            },
            "sentiment": {
                "v": ("+" if net >= 0 else "") + str(net),
                "suf": "/100",
                "d": 0,
                "sub": "índice semanal"
            },
            "sov": {
                "v": "—",
                "d": 0,
                "dtype": "pts",
                "sub": "requer base multi-título"
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
            "tone": "Consolidação semanal por data real das matérias"
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
                "vol": max(count, 1),
                "senti": "pos" if pos >= 55 else "neg" if neg >= 35 else "neu",
                "ang": -90,
                "s": {
                    "p": pos,
                    "n": neg,
                    "g": neu
                }
            }
        ],
        "narratives": narratives,
        "coverage": selected[:8],
        "creators": [],
        "risks": risks,
        "heroOpp": {
            "title": "Leitura semanal desde o teaser",
            "desc": f"Semana consolidada por data real de publicação das matérias. Janela: {label}.",
            "facts": [
                ["Janela", label],
                ["Marco", "25/03/2026"],
                ["Matérias", str(count)],
                ["Dados fictícios", "não"]
            ]
        },
        "opps": opps,
        "ephem": []
    }


def _build_weeks(day):
    """
    Cria semanas desde 25/03/2026.

    w0 = semana atual.
    w-1 = semana anterior.

    Agora as matérias são atribuídas à semana pela data real do campo coverage[].time.
    """
    now = _now_br()

    if now < TEASER_DATE:
        total_weeks = 0
    else:
        total_weeks = (now.date() - TEASER_DATE.date()).days // 7

    history_days = _load_history_days()
    history_days.append(day)

    all_coverage = _coverage_from_all_days(history_days)

    weeks = {}

    for index in range(total_weeks, -1, -1):
        start = TEASER_DATE + timedelta(days=index * 7)
        end = start + timedelta(days=6)

        if end > now:
            end = now

        week_distance = total_weeks - index

        if week_distance == 0:
            key = "w0"
        else:
            key = f"w-{week_distance}"

        label = _range_label(start, end)

        weeks[key] = _build_week_from_coverage(all_coverage, start, end, label)

    return weeks


def save_history(day):
    os.makedirs(config.HISTORY_DIR, exist_ok=True)

    now = _now_br()
    path = os.path.join(config.HISTORY_DIR, f"day-{now:%Y-%m-%d}.json")

    with open(path, "w", encoding="utf-8") as file:
        json.dump(day, file, ensure_ascii=False, indent=2)

    print(f"[build] histórico salvo em {path}")


def build_feed(day):
    public_day = {
        key: value
        for key, value in day.items()
        if not key.startswith("_")
    }

    weeks = _build_weeks(day)

    feed = {
        "generated_at": day["updated"],
        "source": "backend automático",
        "tracking_start": "2026-03-25",
        "tracking_label": "Desde o lançamento do teaser",
        "titles": {
            config.TITLE_ID: {
                "label": config.TITLE_LABEL,
                "topTitle": config.TITLE_TOP,
                "topSub": f"Daily Intelligence · {config.MARKET}",
                "days": {
                    "d0": public_day
                },
                "weeks": weeks
            }
        }
    }

    return feed


def write_feed(feed):
    with open(config.OUTPUT_DATA, "w", encoding="utf-8") as file:
        json.dump(feed, file, ensure_ascii=False, indent=2)

    print(f"[build] {config.OUTPUT_DATA} gravado.")
