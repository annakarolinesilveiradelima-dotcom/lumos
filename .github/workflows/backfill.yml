"""
Lumos backfill_teaser.py

Backfill histórico desde o teaser de Harry Potter em 25/03/2026.

O que faz:
- Busca notícias reais via GNews semana a semana.
- Usa from/to por janela semanal.
- Não usa RSS.
- Não usa links news.google.com.
- Não inventa matéria, fonte, horário ou volume.
- Salva snapshots em ../history/day-YYYY-MM-DD.json.
- Regenera ../data.json com weeks preenchido.
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

    if not parsed:
        return "sem horário disponível"

    try:
        dt = datetime.fromisoformat(str(parsed).replace("Z", "+00:00")).astimezone(BR_TZ)
        return f"{dt.day} {PT_MONTHS[dt.month - 1]}, {dt:%H:%M}"
    except Exception:
        return str(value)[:40]


def _clean_title(title):
    return re.sub(r"\s+", " ", (title or "")).strip()


def _cat(text):
    t = (text or "").lower()

    if re.search(r"rumor|especula|supost|vaza|vazou|pode|possível|teria", t):
        return "esp"

    if re.search(r"nostalg|filmes|clássic|trilha|infância|reboot", t):
        return "nos"

    if re.search(r"crític|polêmic|decep|rejeit|problema|desnecess|medo", t):
        return "neg"

    if re.search(r"elogi|acerto|fiel|ansios|empolg|aprova|confirma|revela|estreia|elenco", t):
        return "pos"

    return "neu"


def _senti_from_cat(cat):
    return {
        "pos": "pos",
        "neg": "neg",
        "esp": "div",
        "nos": "pos"
    }.get(cat, "neu")


def _dedupe_coverage(items):
    seen = set()
    out = []

    for item in items:
        url = item.get("u", "")
        title = item.get("title", "")

        if not url or not title:
            continue

        if "news.google.com" in url:
            continue

        key = url.split("?")[0].lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def _build_sentiment(coverage):
    if not coverage:
        return 0, 100, 0, 50

    pos = sum(1 for item in coverage if item.get("cat") in ("pos", "nos"))
    neg = sum(1 for item in coverage if item.get("cat") == "neg")
    total = len(coverage)

    p = round(pos / total * 100)
    n = round(neg / total * 100)
    g = max(0, 100 - p - n)

    index = 50 + round((p - n) / 2)

    return p, g, n, index


def _narratives_from_coverage(coverage):
    narratives = []

    for item in coverage[:6]:
        narratives.append({
            "t": item.get("title", "Cobertura real coletada"),
            "vol": 1,
            "senti": _senti_from_cat(item.get("cat", "neu")),
            "pf": "Imprensa",
            "trend": "flat",
            "growth": "Backfill histórico desde o teaser; social listening não conectado",
            "q": "",
            "pct": 50,
            "src": [
                {
                    "o": item.get("o", "Imprensa"),
                    "u": item.get("u", "#")
                }
            ]
        })

    return narratives


def _gnews_request(api_key, start, end):
    """
    Usa uma query ampla por semana para economizar requests.
    """
    query = "Harry Potter HBO"

    params = {
        "q": query,
        "max": 10,
        "lang": "pt",
        "country": "br",
        "from": _iso_utc(start),
        "to": _iso_utc(end),
        "sortby": "publishedAt",
        "apikey": api_key
    }

    response = requests.get(
        "https://gnews.io/api/v4/search",
        params=params,
        timeout=TIMEOUT
    )

    print(
        f"[backfill] GNews {start.date()} -> {end.date()} status={response.status_code}"
    )

    if response.status_code != 200:
        print("[backfill] resposta GNews:", response.text[:800])

    return response


def _coverage_from_articles(articles):
    coverage = []

    for article in articles:
        source = article.get("source") or {}
        outlet = source.get("name", "Imprensa")
        url = article.get("url", "")

        if not url:
            continue

        if "news.google.com" in url:
            continue

        title = _clean_title(article.get("title", ""))
        summary = article.get("description", "")

        if not title:
            continue

        cat = _cat(title + " " + summary)

        coverage.append({
            "o": outlet,
            "u": url,
            "title": title,
            "cat": cat,
            "time": _format_time(article.get("publishedAt", "")),
            "scope": "Portal BR"
        })

    return _dedupe_coverage(coverage)


def _empty_snapshot(snapshot_date, week_label):
    return {
        "label": _label(snapshot_date),
        "updated": _stamp(snapshot_date),
        "kpi": {
            "mentions": {
                "v": "0 matérias",
                "d": 0,
                "sub": f"sem cobertura real nesta semana · {week_label}"
            },
            "sentiment": {
                "v": "—",
                "suf": "",
                "d": 0,
                "sub": "sem base suficiente"
            },
            "sov": {
                "v": "—",
                "d": 0,
                "dtype": "pts",
                "sub": "requer base multi-título"
            },
            "buzz": {
                "v": "0",
                "suf": "/100",
                "d": 0,
                "sub": "sem cobertura real"
            }
        },
        "senti": {
            "pos": 0,
            "neu": 100,
            "neg": 0,
            "tone": "Sem cobertura real coletada nesta semana"
        },
        "buzz7": [0, 0, 0, 0, 0, 0, 0],
        "stack": [
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0],
            [0, 100, 0]
        ],
        "platforms": [
            {
                "name": "Imprensa",
                "vol": 1,
                "senti": "neu",
                "ang": -90,
                "s": {
                    "p": 0,
                    "n": 0,
                    "g": 100
                }
            }
        ],
        "narratives": [],
        "coverage": [],
        "creators": [],
        "risks": [],
        "heroOpp": {
            "title": "Sem oportunidade validada nesta semana",
            "desc": "Não houve cobertura real suficiente nesta janela semanal.",
            "facts": [
                ["Janela", week_label],
                ["Marco", "teaser 25/03/2026"],
                ["Dados fictícios", "não"],
                ["Status", "sem cobertura real"]
            ]
        },
        "opps": [],
        "ephem": [],
        "_raw": {
            "base_count": 0,
            "unit": "matérias",
            "net": 0,
            "buzz": 0,
            "news_count": 0,
            "social_mentions": 0,
            "backfill": True
        }
    }


def _snapshot_from_coverage(snapshot_date, week_label, coverage):
    coverage = coverage[:8]

    pos, neu, neg, sentiment_index = _build_sentiment(coverage)

    net = pos - neg
    count = len(coverage)
    buzz = min(100, 20 + count * 8 + round(max(0, net) / 2))

    narratives = _narratives_from_coverage(coverage)

    return {
        "label": _label(snapshot_date),
        "updated": _stamp(snapshot_date),
        "kpi": {
            "mentions": {
                "v": f"{count} matéria" + ("" if count == 1 else "s"),
                "d": 0,
                "sub": f"backfill semanal · {week_label}"
            },
            "sentiment": {
                "v": ("+" if net >= 0 else "") + str(net),
                "suf": "/100",
                "d": 0,
                "sub": "índice semanal por cobertura"
            },
            "sov": {
                "v": "—",
                "d": 0,
                "dtype": "pts",
                "sub": "requer base multi-título"
            },
            "buzz": {
                "v": str(buzz),
                "suf": "/100",
                "d": 0,
                "sub": "buzz semanal desde o teaser"
            }
        },
        "senti": {
            "pos": pos,
            "neu": neu,
            "neg": neg,
            "tone": "Backfill semanal baseado em notícias reais"
        },
        "buzz7": [count, count, count, count, count, count, count],
        "stack": [
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg],
            [pos, neu, neg]
        ],
        "platforms": [
            {
                "name": "Imprensa",
                "vol": max(count, 1),
                "senti": "pos" if pos >= 55 else "neg" if neg >= 35 else "neu",
                "ang": -90,
                "s": {
                    "p": pos,
                    "n": neg,
                    "g": neu
                }
            }
        ],
        "narratives": narratives,
        "coverage": coverage,
        "creators": [],
        "risks": [],
        "heroOpp": {
            "title": "Leitura semanal desde o teaser",
            "desc": f"Semana preenchida por backfill de matérias reais. Janela: {week_label}.",
            "facts": [
                ["Janela", week_label],
                ["Marco", "25/03/2026"],
                ["Matérias reais", str(count)],
                ["Dados fictícios", "não"]
            ]
        },
        "opps": [],
        "ephem": [],
        "_raw": {
            "base_count": count,
            "unit": "matérias",
            "net": net,
            "buzz": buzz,
            "news_count": count,
            "social_mentions": 0,
            "backfill": True,
            "sentiment_index": sentiment_index
        }
    }


def _save_snapshot(snapshot_date, snapshot):
    os.makedirs(config.HISTORY_DIR, exist_ok=True)

    path = os.path.join(config.HISTORY_DIR, f"day-{snapshot_date:%Y-%m-%d}.json")

    with open(path, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, ensure_ascii=False, indent=2)

    print(f"[backfill] snapshot salvo: {path}")


def _load_current_day_or_latest_snapshot():
    """
    Tenta preservar o d0 atual do data.json.
    Se não existir, usa o snapshot mais recente do history.
    """
    try:
        with open(config.OUTPUT_DATA, encoding="utf-8") as file:
            feed = json.load(file)

        current_day = feed["titles"][config.TITLE_ID]["days"]["d0"]

        if current_day:
            return current_day

    except Exception as exc:
        print(f"[backfill] não consegui ler d0 atual do data.json: {exc}")

    if os.path.exists(config.HISTORY_DIR):
        files = sorted(
            file_name
            for file_name in os.listdir(config.HISTORY_DIR)
            if file_name.startswith("day-") and file_name.endswith(".json")
        )

        if files:
            latest = os.path.join(config.HISTORY_DIR, files[-1])

            with open(latest, encoding="utf-8") as file:
                return json.load(file)

    return _empty_snapshot(_now_br(), "sem dados")


def regenerate_feed():
    current_day = _load_current_day_or_latest_snapshot()
    feed = build_data.build_feed(current_day)
    build_data.write_feed(feed)
    print("[backfill] data.json regenerado com weeks desde o teaser.")


def main():
    api_key = os.environ.get("GNEWS_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError("GNEWS_API_KEY não configurada. Adicione em GitHub Secrets.")

    now = _now_br()

    print("[backfill] início")
    print("[backfill] marco: teaser em 25/03/2026")
    print(f"[backfill] hoje: {now:%Y-%m-%d %H:%M}")
    print(f"[backfill] API key detectada com {len(api_key)} caracteres")

    start = TEASER_DATE
    week_index = 1

    hit_rate_limit = False

    while start <= now:
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        if end > now:
            end = now

        week_label = _range_label(start, end)

        print(f"[backfill] Semana {week_index}: {week_label}")

        response = _gnews_request(api_key, start, end)

        if response.status_code == 429:
            print("[backfill] limite da GNews atingido: 429 Too Many Requests")
            print("[backfill] parando backfill para preservar os dados já salvos.")
            hit_rate_limit = True
            break

        if response.status_code in (401, 403):
            raise RuntimeError(
                f"GNews retornou {response.status_code}. Verifique GNEWS_API_KEY/plano."
            )

        try:
            response.raise_for_status()
            data = response.json()
            articles = data.get("articles", [])
            coverage = _coverage_from_articles(articles)

            print(f"[backfill] {len(coverage)} matérias reais na semana {week_label}")

            if coverage:
                snapshot = _snapshot_from_coverage(end, week_label, coverage)
            else:
                snapshot = _empty_snapshot(end, week_label)

            _save_snapshot(end, snapshot)

        except Exception as exc:
            print(f"[backfill] erro na semana {week_label}: {exc}")
            snapshot = _empty_snapshot(end, week_label)
            _save_snapshot(end, snapshot)

        time.sleep(2)

        start = start + timedelta(days=7)
        week_index += 1

    regenerate_feed()

    if hit_rate_limit:
        print("[backfill] concluído parcialmente por limite da API.")
    else:
        print("[backfill] concluído")


if __name__ == "__main__":
    main()
