"""Monta o data.json no contrato consumido pelo lumos.html, usando horário de Brasília."""
from __future__ import annotations

import glob, json, os
from datetime import datetime
from zoneinfo import ZoneInfo
import config

PT_MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
BR_TZ = ZoneInfo("America/Sao_Paulo")


def _now_br(): return datetime.now(BR_TZ)
def _label(dt): return f"{dt.day} {PT_MONTHS[dt.month-1]} {dt.year}"
def _stamp(dt): return f"{_label(dt)}, {dt:%H:%M}"

def _load_prev_day():
    files = sorted(glob.glob(os.path.join(config.HISTORY_DIR, "day-*.json")))
    if not files: return None
    with open(files[-1], encoding="utf-8") as f: return json.load(f)

def _delta(curr, prev):
    try:
        if prev is None: return 0
        return round(curr - prev)
    except Exception:
        return 0

def _human(n, unit="menções"):
    if unit == "matérias": return f"{n} matéria" + ("" if n == 1 else "s")
    return f"{n/1000:.1f} mil".replace(".", ",") if n >= 1000 else str(n)

def _platforms_from_social(social):
    angles = {"TikTok": -90, "X/Twitter": -38, "Instagram": 16, "YouTube": 70, "Reddit": 128, "Threads": 182, "Tumblr": 232}
    out = []
    for name, s in social.items():
        mentions = max(int(s.get("mentions", 0) or 0), 0)
        if mentions <= 0: continue
        pos = round(int(s.get("pos", 0) or 0) / max(mentions, 1) * 100)
        neg = round(int(s.get("neg", 0) or 0) / max(mentions, 1) * 100)
        neu = max(0, 100 - pos - neg)
        senti = "pos" if pos >= 55 else "neg" if neg >= 35 else "div" if abs(pos-neg) < 12 else "neu"
        out.append({"name": name, "vol": mentions, "senti": senti, "ang": angles.get(name, 0), "s": {"p": pos, "n": neg, "g": neu}})
    return out

def _platforms_news_only(news_count, analysis):
    p, g, n = int(analysis.get("pos", 0)), int(analysis.get("neu", 100)), int(analysis.get("neg", 0))
    senti = "pos" if p >= 55 else "neg" if n >= 35 else "neu"
    return [{"name": "Imprensa", "vol": max(news_count, 1), "senti": senti, "ang": -90, "s": {"p": p, "n": n, "g": g}}]

def _series(prev, key, today):
    old = (prev or {}).get(key, [])
    series = (old[1:] if len(old) >= 7 else old) + [today]
    while len(series) < 7: series.insert(0, today)
    return series[-7:]

def build_day(collected, analysis):
    now = _now_br(); prev = _load_prev_day()
    social = collected.get("social", {}) or {}; news = collected.get("news", []) or []
    social_mentions = sum(int(v.get("mentions", 0) or 0) for v in social.values())
    news_count = len(news); has_social = social_mentions > 0
    base_count = social_mentions if has_social else news_count
    unit = "menções" if has_social else "matérias"
    prev_raw = (prev or {}).get("_raw", {})
    sentiment_index = int(analysis.get("sentiment_index", 50)); net = (sentiment_index - 50) * 2
    buzz = min(100, 20 + min(40, base_count * 4) + round(max(0, sentiment_index) / 2))
    platforms = _platforms_from_social(social) if has_social else _platforms_news_only(news_count, analysis)
    return {
        "label": _label(now), "updated": _stamp(now),
        "kpi": {
            "mentions": {"v": _human(base_count, unit), "d": _delta(base_count, prev_raw.get("base_count")), "sub": "vs. ontem" if has_social else "cobertura real coletada"},
            "sentiment": {"v": ("+" if net >= 0 else "") + str(net), "suf": "/100", "d": _delta(net, prev_raw.get("net")), "sub": "índice líquido do dia"},
            "sov": {"v": "—", "d": 0, "dtype": "pts", "sub": "requer base multi-título"},
            "buzz": {"v": str(buzz), "suf": "/100", "d": _delta(buzz, prev_raw.get("buzz")), "sub": "índice de buzz do dia"},
        },
        "senti": {"pos": int(analysis.get("pos", 0)), "neu": int(analysis.get("neu", 100)), "neg": int(analysis.get("neg", 0)), "tone": analysis.get("tone", "—")},
        "buzz7": _series(prev, "buzz7", round(base_count/1000,1) if has_social else base_count),
        "stack": _series(prev, "stack", [int(analysis.get("pos",0)), int(analysis.get("neu",100)), int(analysis.get("neg",0))]),
        "platforms": platforms,
        "narratives": analysis.get("narratives", [])[:6],
        "coverage": analysis.get("coverage", [])[:8],
        "creators": [],
        "risks": analysis.get("risks", [])[:3],
        "heroOpp": analysis.get("heroOpp") or {"title": "Sem oportunidade validada hoje", "desc": "Sem dados sociais conectados para sugerir ação.", "facts": [["Fonte", "notícias"], ["Mercado", "BR"], ["Social", "não conectado"], ["Dados fictícios", "não"]]},
        "opps": analysis.get("opps", [])[:4], "ephem": [],
        "_raw": {"base_count": base_count, "unit": unit, "net": net, "buzz": buzz, "news_count": news_count, "social_mentions": social_mentions}
    }

def save_history(day):
    os.makedirs(config.HISTORY_DIR, exist_ok=True)
    path = os.path.join(config.HISTORY_DIR, f"day-{_now_br():%Y-%m-%d}.json")
    with open(path, "w", encoding="utf-8") as f: json.dump(day, f, ensure_ascii=False, indent=2)
    print(f"[build] histórico salvo em {path}")

def build_feed(day):
    public_day = {k: v for k, v in day.items() if not k.startswith("_")}
    return {"generated_at": day["updated"], "source": "backend automático", "titles": {config.TITLE_ID: {"label": config.TITLE_LABEL, "topTitle": config.TITLE_TOP, "topSub": f"Daily Intelligence · {config.MARKET}", "days": {"d0": public_day}, "weeks": {"w0": public_day}}}}

def write_feed(feed):
    with open(config.OUTPUT_DATA, "w", encoding="utf-8") as f: json.dump(feed, f, ensure_ascii=False, indent=2)
    print(f"[build] {config.OUTPUT_DATA} gravado.")
