"""
Lumos build_data.py

Monta o data.json no contrato do Lumos.

Novo comportamento:
- Diário = execução atual.
- Semanal = semanas desde o teaser de 25/03/2026.
- w0 = semana atual desde o teaser.
- w-1, w-2... = semanas anteriores.
- Sem dado real em uma semana, deixa vazio/honesto.
"""

from __future__ import annotations

import glob
import json
import os
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


def _parse_date_from_label(label):
    """
    Tenta extrair data no formato '8 jul 2026' de labels salvos no histórico.
    """
    if not label:
        return None

    parts = label.split()

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
    Tenta interpretar datas de matérias no formato '8 jul, 14:30'.
    Se não conseguir, retorna None.
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

        now = _now_br()
        hour, minute = hour_min.split(":")

        return datetime(
            now.year,
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
        "narratives": analysis.get("narratives", [])[:6],
        "coverage": analysis.get("coverage", [])[:8],
        "creators": [],
        "risks": analysis.get("risks", [])[:3],
        "heroOpp": analysis.get("heroOpp") or {
            "title": "Sem oportunidade validada hoje",
            "desc": "Sem dados sociais conectados para sugerir ação sem inferência.",
            "facts": [
                ["Fonte", "notícias reais"],
                ["Marco", "teaser 25/03/2026"],
                ["Social", "não conectado"],
                ["Dados fictícios", "não"]
            ]
        },
        "opps": analysis.get("opps", [])[:4],
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
        "risks": [],
        "heroOpp": {
            "title": "Sem oportunidade validada nesta semana",
            "desc": "Não houve cobertura real suficiente nesta janela semanal.",
            "facts": [
                ["Janela", label],
                ["Marco", "teaser 25/03/2026"],
                ["Dados fictícios", "não"],
                ["Status", "aguardando cobertura"]
            ]
        },
        "opps": [],
        "ephem": []
    }


def _build_week_from_days(days, start, end, label):
    selected = []

    for day in days:
        day_dt = _parse_date_from_label(day.get("label"))

        if not day_dt:
            continue

        if start.date() <= day_dt.date() <= end.date():
            selected.append(day)

    if not selected:
        return _empty_week(start, end, label)

    coverage = []
    narratives = []
    risks = []

    pos_values = []
    neu_values = []
    neg_values = []

    buzz7 = []

    for day in selected:
        coverage.extend(day.get("coverage", []))
        narratives.extend(day.get("narratives", []))
        risks.extend(day.get("risks", []))

        senti = day.get("senti", {})
        pos_values.append(int(senti.get("pos", 0)))
        neu_values.append(int(senti.get("neu", 100)))
        neg_values.append(int(senti.get("neg", 0)))

        buzz7.extend(day.get("buzz7", []))

    coverage = coverage[:12]
    narratives = narratives[:6]
    risks = risks[:3]

    count = len(coverage)

    pos = round(sum(pos_values) / len(pos_values)) if pos_values else 0
    neu = round(sum(neu_values) / len(neu_values)) if neu_values else 100
    neg = round(sum(neg_values) / len(neg_values)) if neg_values else 0

    net = (pos - neg)
    buzz = min(100, 20 + count * 8 + round(max(0, net) / 2))

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
            "tone": "Consolidação semanal desde o teaser"
        },
        "buzz7": (buzz7[-7:] if len(buzz7) >= 7 else buzz7 + [count] * (7 - len(buzz7))),
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
        "coverage": coverage[:8],
        "creators": [],
        "risks": risks,
        "heroOpp": {
            "title": "Leitura semanal desde o teaser",
            "desc": f"Semana consolidada a partir do marco de lançamento do teaser em 25/03/2026. Janela: {label}.",
            "facts": [
                ["Janela", label],
                ["Marco", "25/03/2026"],
                ["Matérias", str(count)],
                ["Dados fictícios", "não"]
            ]
        },
        "opps": [],
        "ephem": []
    }


def _build_weeks(day):
    """
    Cria semanas desde 25/03/2026.

    w0 = semana atual.
    w-1 = semana anterior.
    """
    now = _now_br()

    if now < TEASER_DATE:
        total_weeks = 0
    else:
        total_weeks = (now.date() - TEASER_DATE.date()).days // 7

    history_days = _load_history_days()

    # Garante que o dia atual entre na consolidação mesmo antes de estar salvo.
    history_days.append(day)

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

        weeks[key] = _build_week_from_days(history_days, start, end, label)

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
