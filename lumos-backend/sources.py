"""
Lumos sources.py — coleta real de notícias via GNews.

Regra:
- Usa apenas GNews API quando GNEWS_API_KEY existe.
- Não usa RSS/Google News fallback para evitar links intermediários.
- Nunca cria título, URL, horário ou fonte fictícia.
"""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import requests

import config

TIMEOUT = 25


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value):
    if not value:
        return ""

    try:
        if isinstance(value, str) and value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()

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


def _item(outlet, title, url, published="", summary="", source_type="gnews"):
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

        if "news.google.com" in url:
            continue

        key = url.split("?")[0].lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def collect_news():
    """
    Coleta notícias reais pela GNews API.
    Se não houver chave ou se a API não retornar, volta vazio.
    """
    api_key = os.environ.get("GNEWS_API_KEY", "")

    if not api_key:
        print("[coleta] GNEWS_API_KEY não configurada — sem coleta real.")
        return []

    print("[coleta] usando GNews API com links diretos")

    queries = getattr(config, "QUERIES", [
        "série Harry Potter HBO Max",
        "Harry Potter HBO série",
        "Harry Potter HBO Max elenco"
    ])

    since = _iso(datetime.now(timezone.utc) - timedelta(days=14))
    items = []

    for query in queries:
        try:
            params = {
                "q": query,
                "lang": "pt",
                "country": "br",
                "max": 10,
                "from": since,
                "sortby": "publishedAt",
                "apikey": api_key
            }

            response = requests.get(
                "https://gnews.io/api/v4/search",
                params=params,
                timeout=TIMEOUT
            )

            print(f"[coleta] GNews query='{query}' status={response.status_code}")

            response.raise_for_status()

            data = response.json()

            for article in data.get("articles", []):
                source = article.get("source") or {}
                outlet = source.get("name", "Imprensa")

                item = _item(
                    outlet=outlet,
                    title=article.get("title", ""),
                    url=article.get("url", ""),
                    published=article.get("publishedAt", ""),
                    summary=article.get("description", ""),
                    source_type="gnews"
                )

                items.append(item)

        except Exception as exc:
            print(f"[coleta] GNews falhou para query '{query}': {exc}")

    items = _dedupe(items)

    print(f"[coleta] {len(items)} matérias reais coletadas via GNews.")

    return items


def collect_social():
    """
    Carrega dados sociais de export licenciado, se existir.
    Sem export, retorna vazio e não inventa volumes.
    """
    path = getattr(config, "SOCIAL_EXPORT_PATH", "")

    if not path or not os.path.exists(path):
        print("[coleta] sem social listening — não vamos inventar volumes sociais.")
        return {}

    if path.endswith(".json"):
        with open(path, encoding="utf-8") as file:
            rows = json.load(file)
    else:
        with open(path, encoding="utf-8") as file:
            rows = list(csv.DictReader(file))

    social = {}

    for row in rows:
        platform = str(row.get("platform", "")).strip()

        if not platform:
            continue

        social[platform] = {
            "mentions": int(float(row.get("mentions", 0) or 0)),
            "pos": int(float(row.get("pos", 0) or 0)),
            "neu": int(float(row.get("neu", 0) or 0)),
            "neg": int(float(row.get("neg", 0) or 0))
        }

    print(f"[coleta] social carregado: {len(social)} plataformas.")

    return social


def collect_all():
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "news": collect_news(),
        "social": collect_social()
    }
