from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests


TIMEOUT = 25
BR_TZ = ZoneInfo("America/Sao_Paulo")

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

QUERIES = [
    "Harry Potter HBO",
    "Harry Potter Max",
    "serie Harry Potter HBO",
    "nova serie Harry Potter",
    "Harry Potter HBO series",
    "Harry Potter cast HBO",
    "Dominic McLaughlin Harry Potter",
    "Arabella Stanton Harry Potter",
    "Alastair Stout Harry Potter",
    "Paapa Essiedu Harry Potter",
    "John Lithgow Harry Potter"
]


def _format_time_br(dt):
    if not dt:
        return "sem horario disponivel"

    try:
        br = dt.astimezone(BR_TZ)
        return f"{br.day} {PT_MONTHS[br.month - 1]}, {br:%H:%M}"
    except Exception:
        return "sem horario disponivel"


def _parse_pubdate(value):
    if not value:
        return None

    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return None


def _cat(text):
    t = (text or "").lower()

    if re.search(r"rumor|especula|supost|vaza|vazou|pode|possivel|teria|leak|leaked", t):
        return "esp"

    if re.search(r"nostalg|filmes|classic|classico|trilha|infancia|reboot|movies|original cast", t):
        return "nos"

    if re.search(r"critic|polem|decep|rejeit|problema|desnecess|medo|hate|worried|terrible|ruined", t):
        return "neg"

    if re.search(r"elogi|acerto|fiel|ansios|empolg|aprova|confirma|revela|estreia|elenco|excited|love|perfect|faithful", t):
        return "pos"

    return "neu"


def _clean_title(title):
    title = re.sub(r"\s+", " ", title or "").strip()

    if " - " in title:
        parts = title.rsplit(" - ", 1)
        if len(parts[0]) > 10:
            return parts[0].strip()

    return title


def _source_from_item(item, fallback_title):
    source = item.findtext("source")

    if source:
        return source.strip()

    title = fallback_title or ""

    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()

    return "Google News"


def _dedupe(items):
    seen = set()
    out = []

    for item in items:
        url = item.get("u", "")
        title = item.get("title", "")

        if not url or not title:
            continue

        key = (url.split("?")[0] + "|" + title).lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def _rss_url(query):
    encoded = quote_plus(query)

    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=pt-BR"
        "&gl=BR"
        "&ceid=BR:pt-419"
    )


def collect_google_news_week(start, end):
    results = []

    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)

    for query in QUERIES:
        # Google News RSS aceita operadores de busca.
        # O filtro final por data tambem e feito no Python pelo pubDate.
        url = _rss_url(query)

        try:
            response = requests.get(url, timeout=TIMEOUT)

            print(
                f"[google_news] query='{query}' "
                f"{start.date()} to {end.date()} status={response.status_code}"
            )

            if response.status_code != 200:
                print("[google_news] resposta:", response.text[:300])
                continue

            root = ET.fromstring(response.content)
            channel = root.find("channel")

            if channel is None:
                continue

            items = channel.findall("item")

            print(f"[google_news] query='{query}' retornou {len(items)} itens RSS")

            for item in items:
                raw_title = item.findtext("title") or ""
                title = _clean_title(raw_title)
                link = item.findtext("link") or ""
                description = item.findtext("description") or ""
                pub_date = _parse_pubdate(item.findtext("pubDate"))

                if not title or not link or not pub_date:
                    continue

                if not (start_utc <= pub_date <= end_utc):
                    continue

                source = _source_from_item(item, raw_title)
                cat = _cat(title + " " + description)

                results.append({
                    "o": source,
                    "u": link,
                    "title": title,
                    "cat": cat,
                    "time": _format_time_br(pub_date),
                    "scope": "Google News RSS"
                })

            time.sleep(1)

        except Exception as exc:
            print(f"[google_news] falha query='{query}': {exc}")

    results = _dedupe(results)

    print(f"[google_news] {len(results)} materias reais coletadas na semana")

    return results
