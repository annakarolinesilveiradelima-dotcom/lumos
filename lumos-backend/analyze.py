"""
Lumos analyze.py — análise fiel às fontes coletadas.
Não inventa manchete, URL, horário, quote, creator ou volume social.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import config
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

PT_MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _format_time(value):
    if not value:
        return "sem horário disponível"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return f"{dt.day} {PT_MONTHS[dt.month - 1]}, {dt:%H:%M}"
    except Exception:
        return str(value)[:40]


def _cat(text):
    t = (text or "").lower()
    if re.search(r"rumor|especula|supost|vaza|vazou|pode|possível|teria", t):
        return "esp"
    if re.search(r"nostalg|filmes|clássic|trilha|infância|reboot", t):
        return "nos"
    if re.search(r"crític|polêmic|decep|rejeit|problema|desnecess|medo", t):
        return "neg"
    if re.search(r"elogi|acerto|fiel|ansios|empolg|aprova|confirma|revela|estreia|elenco", t):
        return "pos"
    return "neu"


def _senti(cat):
    return {"pos": "pos", "neg": "neg", "esp": "div", "nos": "pos"}.get(cat, "neu")


def _coverage(news):
    out = []
    for it in news[:12]:
        cat = _cat((it.get("title", "") + " " + it.get("summary", "")))
        out.append({
            "o": it.get("outlet", "Imprensa"),
            "u": it.get("url", "#"),
            "title": it.get("title", "—"),
            "cat": cat,
            "time": _format_time(it.get("published", "")),
            "scope": it.get("scope", "Portal BR"),
        })
    return out


def _narratives_from_coverage(cov):
    # Narrativas = agrupamentos interpretativos das matérias reais. Sem quote inventada e sem volume social inventado.
    narratives = []
    for c in cov[:6]:
        narratives.append({
            "t": c["title"],
            "vol": 1,
            "senti": _senti(c["cat"]),
            "pf": "Imprensa",
            "trend": "flat",
            "growth": "Baseado em cobertura real coletada; social listening não conectado" ,
            "q": "",
            "pct": 50,
            "src": [{"o": c["o"], "u": c["u"]}],
        })
    return narratives


def _sentiment_split(cov):
    if not cov:
        return 0, 100, 0, 50
    pos = sum(1 for c in cov if c["cat"] in ("pos", "nos"))
    neg = sum(1 for c in cov if c["cat"] == "neg")
    total = len(cov)
    p = round(pos / total * 100)
    n = round(neg / total * 100)
    g = max(0, 100 - p - n)
    index = 50 + round((p - n) / 2)
    return p, g, n, index


def analyze(collected):
    news = collected.get("news", []) or []
    social = collected.get("social", {}) or {}
    cov = _coverage(news)

    # Se não tiver notícia real, retorna vazio honesto.
    if not cov:
        return {
            "tone": "Sem cobertura real coletada hoje",
            "sentiment_index": 50,
            "pos": 0,
            "neu": 100,
            "neg": 0,
            "narratives": [],
            "coverage": [],
            "risks": [],
            "heroOpp": {
                "title": "Sem oportunidade validada hoje",
                "desc": "Não houve cobertura real suficiente no feed atual para recomendar ação.",
                "facts": [["Fonte", "sem cobertura"], ["Social", "não conectado"], ["Dados fictícios", "não"], ["Ação", "rodar novamente"]],
            },
            "opps": [],
            "_analysis": "empty_real_only",
        }

    p, g, n, idx = _sentiment_split(cov)
    tone = "Cobertura real coletada; social não conectado" if not social else "Cobertura e social listening conectados"

    return {
        "tone": tone,
        "sentiment_index": idx,
        "pos": p,
        "neu": g,
        "neg": n,
        "narratives": _narratives_from_coverage(cov),
        "coverage": cov[:8],
        "risks": [],
        "heroOpp": {
            "title": "Acompanhar cobertura do dia",
            "desc": "A leitura atual usa apenas matérias reais coletadas. Para recomendações sociais e creators, conecte Brandwatch/Meltwater/Stilingue/Sprinklr via export.",
            "facts": [["Fonte", "notícias reais"], ["Matérias", str(len(cov))], ["Social", "não conectado" if not social else "conectado"], ["Dados fictícios", "não"]],
        },
        "opps": [],
        "_analysis": "real_sources_only",
    }
