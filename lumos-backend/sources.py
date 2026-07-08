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
    except Exception:
        try:
            return datetime.fromisoformat(str(value)).astimezone(timezone.utc).isoformat()
        except Exception:
            return str(value)


def _clean_title(title):
    return re.sub(r"\s+", " ", (title or "")).strip()


def _scope(outlet):
    intl = getattr(config, "INTL_OUTLETS", [])

    if outlet in intl:
        return "Internacional"

    return "Portal BR"


def _make_item(outlet, title, url, published="", summary="", source_type="gnews"):
    return {
        "outlet": (outlet or "Imprensa").strip(),
        "title": _clean_title(title),
        "url": (url or "").strip(),
        "published": _parse_dt(published),
        "summary": (summary or "")[:800],
        "scope": _scope(outlet or ""),
        "source_type": source_type
    }


def _dedupe(items):
    seen = set()
    out = []

    for item in items:
        title = item.get("title")
        url = item.get("url")

        if not title or not url:
            continue

        # Remove Google News redirect/intermediário
        if "news.google.com" in url:
            continue

        key = url.split("?")[0].lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def collect_gnews():
    # .strip() remove espaços, enter/quebra de linha e evita erro tipo %0A
    api_key = os.environ.get("GNEWS_API_KEY", "").strip()

    if not api_key:
        print("[coleta] GNEWS_API_KEY não configurada ou vazia.")
        return []

    print("[coleta] usando GNews API com links diretos")

    queries = [
        "Harry Potter HBO",
        "Harry Potter Max",
        "Harry Potter série HBO",
        "Harry Potter HBO Max",
        "Harry Potter elenco HBO",
        "Harry Potter estreia HBO",
        "nova série Harry Potter",
        "série Harry Potter HBO Max"
    ]

    items = []

