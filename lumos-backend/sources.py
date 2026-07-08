"""
Lumos sources.py — coleta real de notícias via GNews.

Regras:
- Usa GNews API como fonte principal.
- Tenta buscar desde o teaser: 25/03/2026.
- Se o plano da GNews não permitir histórico, cai para busca recente.
- Não usa RSS/Google News redirect.
- Não inventa título, link, fonte, horário ou volume.
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
TEASER_DATE_ISO = "2026-03-25T00:00:00Z"


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
        title = item.get("title", "")
        url = item.get("url", "")

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


def _request_gnews(query, api_key, use_teaser_date=True):
    params = {
        "q": query,
        "max": 10,
        "lang": "pt",
        "country": "br",
        "sortby": "publishedAt",
        "apikey": api_key
    }

    if use_teaser_date:
        params["from"] = TEASER_DATE_ISO

    response = requests.get(
        "https://gnews.io/api/v4/search",
        params=params,
        timeout=TIMEOUT
    )

    return response


def collect_gnews():
    api_key = os.environ.get("GNEWS_API_KEY", "").strip()

    if not api_key:
        print("[coleta] GNEWS_API_KEY não configurada ou vazia.")
        return []

    print("[coleta] usando GNews API com links diretos")
    print(f"[coleta] GNEWS_API_KEY detectada com {len(api_key)} caracteres")
    print("[coleta] marco semanal configurado: teaser em 25/03/2026")

    queries = [
        "Harry Potter HBO",
        "Harry Potter HBO Max",
        "série Harry Potter HBO",
        "nova série Harry Potter"
    ]

    items = []

    for query in queries:
        try:
            response = _request_gnews(query, api_key, use_teaser_date=True)

            print(
                f"[coleta] GNews query='{query}' from=2026-03-25 status={response.status_code}"
            )

            if response.status_code != 200:
                print("[coleta] resposta GNews com from:", response.text[:500])
                print("[coleta] tentando novamente sem from, para plano/free recente...")

                response = _request_gnews(query, api_key, use_teaser_date=False)

                print(
                    f"[coleta] GNews query='{query}' sem from status={response.status_code}"
                )

            if response.status_code != 200:
                print("[coleta] resposta GNews:", response.text[:800])

            response.raise_for_status()

            data = response.json()
            articles = data.get("articles", [])

            print(f"[coleta] GNews query='{query}' retornou {len(articles)} artigos")

            for article in articles:
                source = article.get("source") or {}
                outlet = source.get("name", "Imprensa")
                url = article.get("url", "")

                if not url:
                    continue

                if "news.google.com" in url:
                    continue

                item = _make_item(
                    outlet=outlet,
                    title=article.get("title", ""),
                    url=url,
                    published=article.get("publishedAt", ""),
                    summary=article.get("description", ""),
                    source_type="gnews"
                )

                items.append(item)

        except Exception as exc:
            print(f"[coleta] GNews falhou para query '{query}': {exc}")

    items = _dedupe(items)

    print(f"[coleta] {len(items)} matérias reais coletadas com link direto via GNews.")

    return items


def collect_news():
    items = collect_gnews()
    items = _dedupe(items)

    print(f"[coleta] {len(items)} matérias reais finais para o data.json.")

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
