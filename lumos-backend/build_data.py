"""
Montagem — transforma coleta + análise no data.json que o dashboard lê.

- Monta o "dia" no formato do contrato (mesmo de data-sample.json).
- Calcula deltas vs. ontem lendo o snapshot anterior em HISTORY_DIR.
- Salva o snapshot do dia no histórico.
- Mantém uma janela semanal simples (consolidação dos últimos snapshots).
"""
import glob
import json
import os
from datetime import datetime

import config

PT_MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]


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
    return round(curr - prev)


def _platforms_from_social(social):
    angles = {"TikTok": -90, "X/Twitter": -38, "Instagram": 16, "YouTube": 70,
              "Reddit": 128, "Threads": 182, "Tumblr": 232}
    out = []
    for name, ang in angles.items():
        s = social.get(name)
        if not s:
            continue
        m = max(s["mentions"], 1)
        pos = round(s["pos"] / m * 100)
        neg = round(s["neg"] / m * 100)
        neu = max(100 - pos - neg, 0)
        senti = "pos" if pos >= 55 else ("neg" if neg >= 35 else ("div" if abs(pos - neg) < 12 else "neu"))
        out.append({"name": name, "vol": s["mentions"], "senti": senti, "ang": ang,
                    "s": {"p": pos, "n": neg, "g": neu}})
    return out


def build_day(collected, analysis):
    now = datetime.now()
    social = collected.get("social", {})
    total_mentions = sum(v["mentions"] for v in social.values()) or \
        max(len(collected.get("news", [])) * 120, 1)

    prev = _load_prev_day()
    prev_kpi = (prev or {}).get("_raw", {})

    senti_index = int(analysis.get("sentiment_index", 50))
    net = (senti_index - 50) * 2  # -100..100 aproximado

    day = {
        "label": _today_label(now),
        "updated": _stamp(now),
        "kpi": {
            "mentions": {"v": _human(total_mentions), "d": _delta(total_mentions, prev_kpi.get("mentions")),
                         "sub": "vs. ontem"},
            "sentiment": {"v": ("+" if net >= 0 else "") + str(net), "suf": "/100",
                          "d": _delta(net, prev_kpi.get("net")), "sub": "índice líquido do dia"},
            "sov": {"v": "—", "d": 0, "dtype": "pts", "sub": "requer base multi-título"},
            "buzz": {"v": str(min(99, 40 + senti_index // 2 + min(total_mentions // 500, 30))),
                     "suf": "/100", "d": 0, "sub": "índice de buzz do dia"},
        },
        "senti": {"pos": analysis.get("pos", 55), "neu": analysis.get("neu", 30),
                  "neg": analysis.get("neg", 15), "tone": analysis.get("tone", "—")},
        "buzz7": _buzz7(prev, total_mentions),
        "stack": _stack(prev, analysis),
        "platforms": _platforms_from_social(social) or _default_platforms(analysis),
        "narratives": analysis.get("narratives", [])[:6],
        "coverage": analysis.get("coverage", [])[:8],
        "creators": [],  # preenchido pela ferramenta de listening quando disponível
        "risks": analysis.get("risks", []),
        "heroOpp": {"title": "Oportunidade do dia", "desc": analysis.get("tone", ""),
                    "facts": [["Fonte", analysis.get("_analysis", "—")], ["Mercado", "BR"],
                              ["Atualizado", now.strftime("%d/%m %H:%M")], ["Período", "Diário"]]},
        "opps": [],
        "ephem": [],
        # dados brutos para o cálculo de delta de amanhã (não usados pelo dashboard)
        "_raw": {"mentions": total_mentions, "net": net},
    }
    return day


def _human(n):
    if n >= 1000:
        return f"{n/1000:.1f} mil".replace(".", ",")
    return str(n)


def _buzz7(prev, today):
    prev7 = (prev or {}).get("buzz7", [])
    series = (prev7[1:] if len(prev7) >= 7 else prev7) + [round(today / 1000, 1)]
    while len(series) < 7:
        series.insert(0, round(today / 1000, 1))
    return series[-7:]


def _stack(prev, analysis):
    prev_stack = (prev or {}).get("stack", [])
    today = [analysis.get("pos", 55), analysis.get("neu", 30), analysis.get("neg", 15)]
    series = (prev_stack[1:] if len(prev_stack) >= 7 else prev_stack) + [today]
    while len(series) < 7:
        series.insert(0, today)
    return series[-7:]


def _default_platforms(analysis):
    # Sem dados sociais: distribui o sentimento agregado como estimativa.
    p, g, n = analysis.get("pos", 55), analysis.get("neu", 30), analysis.get("neg", 15)
    base = [("TikTok", -90), ("X/Twitter", -38), ("Instagram", 16),
            ("YouTube", 70), ("Reddit", 128)]
    return [{"name": nm, "vol": 1000, "senti": "pos" if p > 55 else "neu", "ang": ang,
             "s": {"p": p, "n": n, "g": g}} for nm, ang in base]


def save_history(day):
    os.makedirs(config.HISTORY_DIR, exist_ok=True)
    fname = os.path.join(config.HISTORY_DIR, f"day-{datetime.now():%Y-%m-%d}.json")
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(day, f, ensure_ascii=False, indent=2)


def build_feed(day):
    """Empacota no formato final que o dashboard consome."""
    # remove campo interno antes de publicar
    public_day = {k: v for k, v in day.items() if not k.startswith("_")}
    feed = {
        "generated_at": day["updated"],
        "titles": {
            config.TITLE_ID: {
                "label": config.TITLE_LABEL,
                "topTitle": config.TITLE_TOP,
                "topSub": f"Daily Intelligence · {config.MARKET}",
                "days": {"d0": public_day},
            }
        },
    }
    return feed


def write_feed(feed):
    with open(config.OUTPUT_DATA, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
    print(f"[build] {config.OUTPUT_DATA} gravado.")
