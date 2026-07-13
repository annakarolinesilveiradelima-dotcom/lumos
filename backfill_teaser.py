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

