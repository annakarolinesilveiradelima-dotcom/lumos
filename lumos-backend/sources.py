"""
Coleta — camada de fontes.

- Notícias: lê feeds RSS (gratuito) definidos em config.RSS_FEEDS.
- Social: se SOCIAL_EXPORT_PATH apontar para um export da ferramenta de
  listening (CSV ou JSON), carrega de lá. Senão, retorna vazio e o pipeline
  segue só com a camada de notícias.

Depende apenas de `requests` e `feedparser` (ver requirements.txt).
"""
import csv
import json
import os
from datetime import datetime, timezone

import requests

try:
    import feedparser
except ImportError:
    feedparser = None

import config


def collect_news():
    """Retorna lista de itens: {outlet, title, url, published, summary}."""
    items = []
    if feedparser is None:
        print("[coleta] feedparser não instalado — pulando RSS.")
        return items
    for outlet, url in config.RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:25]:
                items.append({
                    "outlet": outlet if "Google News" not in outlet else _guess_source(e),
                    "title": getattr(e, "title", "").strip(),
                    "url": getattr(e, "link", ""),
                    "published": getattr(e, "published", ""),
                    "summary": getattr(e, "summary", "")[:400],
                })
        except Exception as exc:  # noqa: BLE001
            print(f"[coleta] falha no feed {outlet}: {exc}")
    print(f"[coleta] {len(items)} itens de notícia coletados.")
    return _dedupe(items)


def _guess_source(entry):
    # Google News costuma trazer a fonte em entry.source.title
    src = getattr(entry, "source", None)
    if src and getattr(src, "title", None):
        return src.title
    return "Imprensa"


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        key = (it["title"] or "").lower()[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def collect_social():
    """
    Carrega dados sociais de um export da ferramenta de listening, se houver.
    Espera um CSV com colunas: platform, mentions, pos, neu, neg
    ou um JSON no mesmo formato (lista de objetos).
    Retorna: {platform: {mentions, pos, neu, neg}}
    """
    path = config.SOCIAL_EXPORT_PATH
    if not path or not os.path.exists(path):
        print("[coleta] sem export social — feed sairá só com camada de notícias.")
        return {}
    rows = []
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    else:
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    social = {}
    for r in rows:
        social[r["platform"]] = {
            "mentions": int(float(r.get("mentions", 0))),
            "pos": int(float(r.get("pos", 0))),
            "neu": int(float(r.get("neu", 0))),
            "neg": int(float(r.get("neg", 0))),
        }
    print(f"[coleta] social: {len(social)} plataformas.")
    return social


def collect_all():
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "news": collect_news(),
        "social": collect_social(),
    }
