"""
Lumos backfill_teaser.py

Backfill histórico desde o teaser de Harry Potter em 25/03/2026.

O que faz:
- Busca notícias reais via GNews, semana por semana.
- Busca posts públicos reais do Reddit, se social_reddit.py estiver disponível.
- Usa from/to por janela semanal.
- Não usa RSS.
- Não usa links news.google.com.
- Não inventa matéria, post, fonte, horário ou volume.
- Salva snapshots em history/day-YYYY-MM-DD.json.
- Regenera data.json com weeks preenchido.
"""

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
        return f"{start.day}–{end.day} {PT_MONTHS[end.month - 1]} {end.year}"

    return (
        f"{start.day} {PT_MONTHS[start.month - 1]}–"
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
        return "sem horário disponível"

    try:
        dt = datetime.fromisoformat(str(parsed).replace("Z", "+00:00")).astimezone(BR_TZ)
        return f"{dt.day} {PT_MONTHS[dt.month - 1]}, {dt:%H:%M}"
    except Exception:
        return str(value)[:40]


def _clean_title(title):
    return re.sub(r"\s+", " ", (title or "")).strip()


def _cat(text):
    t = (text or "").lower()

    if re.search(r"rumor|especula|supost|vaza|vazou|pode|possível|teria|leak|leaked", t):
        return "esp"

    if re.search(r"nostalg|filmes|clássic|trilha|infância|reboot|movies|original cast", t):
        return "nos"

    if re.search(r"crític|polêmic|decep|rejeit|problema|desnecess|medo|hate|worried|terrible|ruined", t):
        return "neg"

    if re.search(r"elogi|acerto|fiel|ansios|empolg|aprova|confirma|revela|estreia|elenco|excited|love|perfect|faithful", t):
        return "pos"

    return "neu"


def _senti_from_cat(cat):
    return {
        "pos": "pos",
        "neg": "neg",
        "esp": "div",
        "nos": "pos"
    }.get(cat, "neu")


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
            "growth": "Backfill histórico desde o teaser; baseado em fonte real coletada",
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


def _gnews_request(api_key, start, end):
    """
    Busca notícias reais da semana usando diferentes queries.
    """

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

    queries = [
        "Harry Potter HBO",
        "Harry Potter Max",
        "série Harry Potter HBO",
        "nova série Harry Potter",
        "(Harry Potter) AND (HBO OR Max OR série OR series)",
        "(Harry Potter) AND (cast OR elenco OR teaser OR trailer)",
        "(Harry Potter) AND (Dominic McLaughlin OR Arabella Stanton OR Alastair Stout)",
        "(Harry Potter) AND (Paapa Essiedu OR John Lithgow)"
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
