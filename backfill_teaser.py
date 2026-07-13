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

