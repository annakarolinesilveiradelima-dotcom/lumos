"""
Lumos backfill_teaser.py

Backfill historico desde o teaser de Harry Potter em 25/03/2026.

O que faz:
- Busca noticias reais via GNews, semana por semana.
- Busca posts publicos reais do Reddit, se social_reddit.py estiver disponivel.
- Usa from/to por janela semanal.
- Nao usa RSS.
- Nao usa links news.google.com.
- Nao inventa materia, post, fonte, horario ou volume.
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
