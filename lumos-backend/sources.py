"""
Lumos sources.py — coleta real de notícias.

Regras:
- Usa GNews API como fonte principal.
- Usa NewsAPI como fallback opcional, se NEWSAPI_KEY existir.
- Não usa RSS/Google News redirect.
- Não inventa título, link, fonte, horário ou volume.
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


def _make_item(outlet, title, url, published="", summary="", source_type="api"):
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


def collect_gnews():
    api_key = os.environ.get("GNEWS_API_KEY", "")

    if not api_key:
        print("[coleta] GNEWS_API_KEY não configurada.")
        return []

    print("[coleta] usando GNews API com links diretos")

    queries = [
        "Harry Potter HBO",
        "série Harry Potter HBO",
        "Harry Potter Max",
        "Harry Potter série HBO Max",
        "Harry Potter HBO elenco",
        "Harry Potter HBO série estreia"
    ]

    since = _iso(datetime.now(timezone.utc) - timedelta(days=30))
    items = []

    for query in queries:
        try:
            params = {
                "q": query,
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

                items.append(
                    _make_item(
                        outlet=outlet,
                        title=article.get("title", ""),
                        url=article.get("url", ""),
                        published=article.get("publishedAt", ""),
                        summary=article.get("description", ""),
                        source_type="gnews"
                    )
                )

        except Exception as exc:
            print(f"[coleta] GNews falhou para query '{query}': {exc}")

    return _dedupe(items)


def collect_newsapi():
    api_key = os.environ.get("NEWSAPI_KEY", "")

    if not api_key:
        print("[coleta] NEWSAPI_KEY não configurada.")
        return []

    print("[coleta] usando NewsAPI como fallback")

    queries = [
        "Harry Potter HBO",
        "Harry Potter Max",
        "série Harry Potter HBO"
    ]

    since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()
    items = []

    for query in queries:
        try:
            params = {
                "q": query,
                "language": "pt",
                "from": since,
                "sortBy": "publishedAt",
                "pageSize": 20,
                "apiKey": api_key
            }

            response = requests.get(
                "https://newsapi.org/v2/everything",
                params=params,
                timeout=TIMEOUT
            )

            print(f"[coleta] NewsAPI query='{query}' status={response.status_code}")

            response.raise_for_status()

            data = response.json()

            for article in data.get("articles", []):
                source = article.get("source") or {}
                outlet = source.get("name", "Imprensa")

                items.append(
                    _make_item(
                        outlet=outlet,
                        title=article.get("title", ""),
                        url=article.get("url", ""),
                        published=article.get("publishedAt", ""),
                        summary=article.get("description", ""),
                        source_type="newsapi"
                    )
                )

        except Exception as exc:
            print(f"[coleta] NewsAPI falhou para query '{query}': {exc}")

    return _dedupe(items)


def collect_news():
    items = []

    items.extend(collect_gnews())

    if not items:
        items.extend(collect_newsapi())

    items = _dedupe(items)

    print(f"[coleta] {len(items)} matérias reais coletadas com link direto.")

    return items


def collect_social():
    """
    Social listening só entra se houver export licenciado.
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
