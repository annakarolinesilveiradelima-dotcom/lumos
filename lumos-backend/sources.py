"""
Lumos sources.py — coleta real de notícias.
Prioridade: GNews / NewsAPI / Bing News. RSS só como fallback.
Nunca cria título, URL, horário ou fonte fictícia.
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
try:
    import feedparser
except ImportError:
    feedparser = None

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


def _item(outlet, title, url, published="", summary="", source_type="news"):
    return {
        "outlet": (outlet or "Imprensa").strip(),
        "title": re.sub(r"\s+", " ", (title or "")).strip(),
        "url": (url or "").strip(),
        "published": _parse_dt(published),
        "summary": (summary or "")[:800],
        "scope": "Internacional" if (outlet or "") in getattr(config, "INTL_OUTLETS", []) else "Portal BR",
        "source_type": source_type,
    }


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        if not it.get("title") or not it.get("url"):
            continue
        key = (it["url"].split("?")[0].lower() or it["title"].lower()[:90])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def collect_gnews():
    key = os.environ.get("GNEWS_API_KEY") or getattr(config, "GNEWS_API_KEY", "")
    if not key:
        return []
    print("[coleta] usando GNews API")
    items = []
    since = _iso(datetime.now(timezone.utc) - timedelta(days=7))
    queries = getattr(config, "QUERIES", ["série Harry Potter HBO Max"])
    for q in queries:
        params = {
            "q": q,
            "lang": "pt",
            "country": "br",
            "max": 10,
            "from": since,
            "sortby": "publishedAt",
            "apikey": key,
        }
        r = requests.get("https://gnews.io/api/v4/search", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        for a in r.json().get("articles", []):
            src = (a.get("source") or {}).get("name", "Imprensa")
            items.append(_item(src, a.get("title"), a.get("url"), a.get("publishedAt"), a.get("description"), "gnews"))
    return items


def collect_newsapi():
    key = os.environ.get("NEWSAPI_KEY") or getattr(config, "NEWSAPI_KEY", "")
    if not key:
        return []
    print("[coleta] usando NewsAPI")
    items = []
    since = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    queries = getattr(config, "QUERIES", ["série Harry Potter HBO Max"])
    for q in queries:
        params = {
            "q": q,
            "language": "pt",
            "from": since,
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": key,
        }
        r = requests.get("https://newsapi.org/v2/everything", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        for a in r.json().get("articles", []):
            src = (a.get("source") or {}).get("name", "Imprensa")
            items.append(_item(src, a.get("title"), a.get("url"), a.get("publishedAt"), a.get("description"), "newsapi"))
    return items


def collect_bing():
    key = os.environ.get("BING_NEWS_API_KEY") or getattr(config, "BING_NEWS_API_KEY", "")
    if not key:
        return []
    print("[coleta] usando Bing News API")
    items = []
    headers = {"Ocp-Apim-Subscription-Key": key}
    queries = getattr(config, "QUERIES", ["série Harry Potter HBO Max"])
    for q in queries:
        params = {"q": q, "mkt": "pt-BR", "count": 20, "sortBy": "Date"}
        r = requests.get("https://api.bing.microsoft.com/v7.0/news/search", params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        for a in r.json().get("value", []):
            provider = (a.get("provider") or [{}])[0].get("name", "Imprensa")
            items.append(_item(provider, a.get("name"), a.get("url"), a.get("datePublished"), a.get("description"), "bing"))
    return items


def collect_rss():
    if feedparser is None:
        print("[coleta] feedparser não instalado — pulando RSS")
        return []
    print("[coleta] usando RSS fallback")
    feeds = getattr(config, "RSS_FEEDS", [])
    items = []
    for outlet, url in feeds:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
                title = getattr(e, "title", "")
                src = getattr(getattr(e, "source", None), "title", None) or outlet
                if " - " in title and "Google News" in outlet:
                    title, src = title.rsplit(" - ", 1)
                items.append(_item(src, title, getattr(e, "link", ""), getattr(e, "published", ""), getattr(e, "summary", ""), "rss"))
        except Exception as exc:
            print(f"[coleta] falha RSS {outlet}: {exc}")
    return items


def collect_news():
    items = []
    # Não para no primeiro coletor: complementa e deduplica.
    for fn in (collect_gnews, collect_newsapi, collect_bing, collect_rss):
        try:
            items.extend(fn())
        except Exception as exc:
            print(f"[coleta] {fn.__name__} falhou: {exc}")
    items = _dedupe(items)
    print(f"[coleta] {len(items)} notícias reais coletadas")
    return items


def collect_social():
    path = getattr(config, "SOCIAL_EXPORT_PATH", "")
    if not path or not os.path.exists(path):
        print("[coleta] sem social listening — não vamos inventar volumes sociais")
        return {}
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    else:
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    social = {}
    for r in rows:
        platform = str(r.get("platform", "")).strip()
        if not platform:
            continue
        social[platform] = {
            "mentions": int(float(r.get("mentions", 0) or 0)),
            "pos": int(float(r.get("pos", 0) or 0)),
            "neu": int(float(r.get("neu", 0) or 0)),
            "neg": int(float(r.get("neg", 0) or 0)),
        }
    print(f"[coleta] social carregado: {len(social)} plataformas")
    return social


def collect_all():
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "news": collect_news(),
        "social": collect_social(),
    }
