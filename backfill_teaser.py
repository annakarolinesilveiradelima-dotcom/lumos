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

import build_data
import config


TIMEOUT = 25
BR_TZ = ZoneInfo("America/Sao_Paulo")

TITLE_ID = getattr(config, "TITLE_ID", "hp")
OUTPUT_DATA = getattr(config, "OUTPUT_DATA", "../data.json")
HISTORY_DIR = getattr(config, "HISTORY_DIR", "../history")

TEASER_DATE = datetime(2026, 3, 25, 0, 0, 0, tzinfo=BR_TZ)

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

SEARCH_QUERIES = [
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

TRENDS_KEYWORDS = [
    "Harry Potter",
    "Harry Potter HBO",
    "Harry Potter Max",
    "Harry Potter series",
    "HBO Harry Potter",
    "nova serie Harry Potter",
    "John Lithgow Harry Potter",
    "Paapa Essiedu Harry Potter"
]

WIKI_PAGES = [
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter",
        "label": "Harry Potter"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter_(film_series)",
        "label": "Harry Potter film series"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter_(TV_series)",
        "label": "Harry Potter TV series"
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
    },
    {
        "project": "pt.wikipedia.org",
        "article": "Harry_Potter",
        "label": "Harry Potter PT"
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


def _yyyymmdd(dt):
    return dt.strftime("%Y%m%d")


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


def _trends_url(query):
    encoded = quote_plus(query)

    return (
        "https://trends.google.com/trends/explore"
        "?date=2026-03-25%202026-07-13"
        "&geo=BR"
        f"&q={encoded}"
    )


def _wiki_url(project, article):
    safe_article = quote(article, safe="")
    return f"https://{project}/wiki/{safe_article}"


