"""
Lumos sources.py — coleta real de notícias via GNews.

Regras:
- Usa GNews API como fonte principal.
- Não usa RSS/Google News redirect.
- Não inventa título, link, fonte, horário ou volume.
- Se a API não retornar nada, volta vazio.
"""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

import config

TIMEOUT = 25


def _parse_dt(value):
    if not value:
        return ""

    try:
        if isinstance(value, str) and value.endswith("Z"):
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(timezone.utc).isoformat()

        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
