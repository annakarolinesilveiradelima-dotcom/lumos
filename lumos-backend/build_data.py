"""
Montagem — transforma coleta + análise no data.json que o dashboard lê.

- Monta o "dia" no formato do contrato do Lumos.
- Usa horário de Brasília.
- Calcula deltas vs. ontem lendo o snapshot anterior em HISTORY_DIR.
- Salva o snapshot do dia no histórico.
- Não inventa volume social quando não existe ferramenta de listening conectada.
"""

import glob
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import config

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

BR_TZ = ZoneInfo("America/Sao_Paulo")


def _now_br():
    return datetime.now(BR_TZ)


def _today_label(dt):
    return f"{dt.day} {PT_MONTHS[dt.month - 1]} {dt.year}"


def _stamp(dt):
    return f"{_today_label(dt)}, {dt:%H:%M}"


def _load_prev_day():
    files = sorted(glob.glob(os.path.join(config.HISTORY_DIR, "day-*.json")))
    if not files:
        return None

    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def _delta(curr, prev):
    if prev is None:
        return 0
    try:
        return round(curr - prev)
    except Exception:
        return 0


def _human(n, unit="menções"):
    if unit == "matérias":
        return f"{n} matéria" + ("" if n == 1 else "s")

    if n >= 1000:
        return f"{n / 1000:.1f} mil".replace(".", ",")

    return str(n)


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

    for name, ang in angles.items():
        s = social.get(name)

        if not s:
            continue

        mentions = max(int(s.get("mentions", 0)), 1)
        pos = round(int(s.get("pos", 0)) / mentions * 100)
        neg = round(int(s.get("neg", 0)) / mentions * 100)
        neu = max(100 - pos - neg, 0)

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
            "ang": ang,
            "s": {
                "p": pos,
                "n": neg,
                "g": neu
            }
        })

    return out


def _platforms_news_only(news_count, analysis):
    """
    Sem social listening conectado, não simulamos TikTok/X/Instagram.
    O radar mostra apenas a camada real disponível: imprensa.
    """
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


def _buzz_score(base_count, sentiment_index):
    """
    Score simples e transparente:
    - volume disponível
    - qualidade do sentimento
    - sem simular social
    """
    base = min(40, base_count * 4)
    sentiment_component = min(40, max(0, sentiment_index))
    return min(100, 20 + base + round(sentiment_component / 2))


def _buzz7(prev, today):
    prev7 = (prev or {}).get("buzz7", [])
    series = (prev7[1:] if len(prev7) >= 7 else prev7) + [today]

    while len(series) < 7:
        series.insert(0, today)

    return series[-7:]


def _stack(prev, analysis):
    prev_stack = (prev or {}).get("stack", [])

    today = [
        int(analysis.get("pos", 0)),
        int(analysis.get("neu", 100)),
        int(analysis.get("neg", 0))
    ]

    series = (prev_stack[1:] if len(prev_stack) >= 7 else prev_stack) + [today]

    while len(series) < 7:
        series.insert(0, today)

    return series[-7:]


def build_day(collected, analysis):
    now = _now_br()

    social = collected.get("social", {}) or {}
    news = collected.get("news", []) or []

    social_mentions = sum(int(v.get("mentions", 0)) for v in social.values())
    news_count = len(news)

    has_social = social_mentions > 0

    if has_social:
        base_count = social_mentions
        base_unit = "menções"
        mentions_label = _human(base_count, "menções")
        mentions_sub = "vs. ontem"
    else:
        base_count = news_count
        base_unit = "matérias"
        mentions_label = _human(base_count, "matérias")
        mentions_sub = "cobertura real coletada"

    prev = _load_prev_day()
    prev_raw = (prev or {}).get("_raw", {})

    sentiment_index = int(analysis.get("sentiment_index", 50))
    net = (sentiment_index - 50) * 2

    buzz = _buzz_score(base_count, sentiment_index)

    if has_social:
        platforms = _platforms_from_social(social)
    else:
        platforms = _platforms_news_only(news_count, analysis)

    day = {
        "label": _today_label(now),
        "updated": _stamp(now),
        "kpi": {
            "mentions": {
                "v": mentions_label,
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
        "buzz7": _buzz7(prev, round(base_count / 1000, 1) if has_social else base_count),
        "stack": _stack(prev, analysis),
        "platforms": platforms,
        "narratives": analysis.get("narratives", [])[:6],
        "coverage": analysis.get("coverage", [])[:8],
        "creators": [],
        "risks": analysis.get("risks", [])[:3],
        "heroOpp": analysis.get("heroOpp") or {
            "title": "Oportunidade do dia",
            "desc": analysis.get("tone", "Sem leitura suficiente para recomendação acionável."),
            "facts": [
                ["Fonte", analysis.get("_analysis", "backend")],
                ["Mercado", "BR"],
                ["Atualizado", now.strftime("%d/%m %H:%M")],
                ["Período", "Diário"]
            ]
        },
        "opps": analysis.get("opps", [])[:4],
        "ephem": [],
        "_raw": {
            "base_count": base_count,
            "base_unit": base_unit,
            "mentions": social_mentions,
            "news_count": news_count,
            "net": net,
            "buzz": buzz
        }
    }

    return day


def save_history(day):
    os.makedirs(config.HISTORY_DIR, exist_ok=True)

    now = _now_br()
    fname = os.path.join(config.HISTORY_DIR, f"day-{now:%Y-%m-%d}.json")

    with open(fname, "w", encoding="utf-8") as f:
        json.dump(day, f, ensure_ascii=False, indent=2)

    print(f"[build] histórico salvo em {fname}")


def build_feed(day):
    """
    Empacota no formato final que o dashboard consome.
    Inclui days e weeks para o frontend funcionar tanto no modo diário quanto semanal.
    """
    public_day = {
        k: v for k, v in day.items()
        if not k.startswith("_")
    }

    feed = {
        "generated_at": day["updated"],
        "source": "backend automático",
        "titles": {
            config.TITLE_ID: {
                "label": config.TITLE_LABEL,
                "topTitle": config.TITLE_TOP,
                "topSub": f"Daily Intelligence · {config.MARKET}",
                "days": {
                    "d0": public_day
                },
                "weeks": {
                    "w0": public_day
                }
            }
        }
    }

    return feed


def write_feed(feed):
    with open(config.OUTPUT_DATA, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)

    print(f"[build] {config.OUTPUT_DATA} gravado.")
