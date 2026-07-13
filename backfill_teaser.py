from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests

import build_data
import config


TIMEOUT = 25
BR_TZ = ZoneInfo("America/Sao_Paulo")

TITLE_ID = getattr(config, "TITLE_ID", "hp")
OUTPUT_DATA = getattr(config, "OUTPUT_DATA", "../data.json")
HISTORY_DIR = getattr(config, "HISTORY_DIR", "../history")

TEASER_DATE = datetime(2026, 3, 25, 0, 0, 0, tzinfo=BR_TZ)

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

SEARCH_QUERIES = [
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

TRENDS_KEYWORDS = [
    "Harry Potter",
    "Harry Potter HBO",
    "Harry Potter Max",
    "Harry Potter series",
    "HBO Harry Potter",
    "nova serie Harry Potter",
    "John Lithgow Harry Potter",
    "Paapa Essiedu Harry Potter"
]


def _now_br():
    return datetime.now(BR_TZ)


def _label(dt):
    return f"{dt.day} {PT_MONTHS[dt.month - 1]} {dt.year}"


def _stamp():
    now = _now_br()
    return f"{_label(now)}, {now:%H:%M}"


def _range_label(start, end):
    if start.month == end.month:
        return f"{start.day}-{end.day} {PT_MONTHS[end.month - 1]} {end.year}"

    return (
        f"{start.day} {PT_MONTHS[start.month - 1]}-"
        f"{end.day} {PT_MONTHS[end.month - 1]} {end.year}"
    )


def _iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_pubdate(value):
    if not value:
        return None

    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return None


def _format_time_br(dt):
    if not dt:
        return "sem horario disponivel"

    try:
        br = dt.astimezone(BR_TZ)
        return f"{br.day} {PT_MONTHS[br.month - 1]}, {br:%H:%M}"
    except Exception:
        return "sem horario disponivel"


def _clean_title(title):
    title = re.sub(r"\s+", " ", title or "").strip()

    if " - " in title:
        parts = title.rsplit(" - ", 1)
        if len(parts[0]) > 10:
            return parts[0].strip()

    return title


def _cat(text):
    t = (text or "").lower()

    if re.search(r"rumor|especula|supost|vaza|vazou|pode|possivel|teria|leak|leaked", t):
        return "esp"

    if re.search(r"nostalg|filmes|classic|classico|trilha|infancia|reboot|movies|original cast", t):
        return "nos"

    if re.search(r"critic|polem|decep|rejeit|problema|desnecess|medo|hate|worried|terrible|ruined", t):
        return "neg"

    if re.search(r"elogi|acerto|fiel|ansios|empolg|aprova|confirma|revela|estreia|elenco|excited|love|perfect|faithful|reaction|review", t):
        return "pos"

    return "neu"


def _senti_from_cat(cat):
    mapping = {
        "pos": "pos",
        "neg": "neg",
        "esp": "div",
        "nos": "pos",
        "neu": "neu"
    }

    return mapping.get(cat, "neu")


def _source_from_rss_item(item, raw_title):
    source = item.findtext("source")

    if source:
        return source.strip()

    if raw_title and " - " in raw_title:
        return raw_title.rsplit(" - ", 1)[-1].strip()

    return "Google News"


def _google_news_url(query):
    encoded = quote_plus(query)

    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=pt-BR"
        "&gl=BR"
        "&ceid=BR:pt-419"
    )


def _trends_url(query):
    return (
        "https://trends.google.com/trends/explore"
        "?date=2026-03-25%202026-07-13"
        "&geo=BR"
        f"&q={quote_plus(query)}"
    )


def _dedupe_coverage(items):
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


def _has_real_coverage(snapshot):
    if not snapshot:
        return False

    coverage = snapshot.get("coverage", [])

    return isinstance(coverage, list) and len(coverage) > 0


def _history_path(snapshot_date):
    return os.path.join(HISTORY_DIR, f"day-{snapshot_date:%Y-%m-%d}.json")


def _load_existing_snapshot(snapshot_date):
    path = _history_path(snapshot_date)

    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        print(f"[backfill] nao consegui ler snapshot existente {path}: {exc}")
        return None


def _load_existing_current_day():
    try:
        with open(OUTPUT_DATA, encoding="utf-8") as file:
            feed = json.load(file)

        return feed["titles"][TITLE_ID]["days"]["d0"]
    except Exception as exc:
        print(f"[backfill] nao consegui ler d0 existente: {exc}")
        return None


def collect_google_news_week(start, end):
    results = []

    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)

    for query in SEARCH_QUERIES:
        url = _google_news_url(query)

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

                source = _source_from_rss_item(item, raw_title)
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

    results = _dedupe_coverage(results)

    print(f"[google_news] {len(results)} materias reais coletadas na semana")

    return results


def collect_youtube_week(start, end, api_key):
    if not api_key:
        print("[youtube] YOUTUBE_API_KEY nao configurada. Pulando YouTube.")
        return []

    results = []

    for query in SEARCH_QUERIES:
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": 10,
            "order": "date",
            "publishedAfter": _iso_utc(start),
            "publishedBefore": _iso_utc(end),
            "regionCode": "BR",
            "relevanceLanguage": "pt",
            "key": api_key
        }

        try:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
                timeout=TIMEOUT
            )

            print(
                f"[youtube] query='{query}' "
                f"{start.date()} to {end.date()} status={response.status_code}"
            )

            if response.status_code != 200:
                print("[youtube] resposta:", response.text[:500])
                continue

            data = response.json()
            items = data.get("items", [])

            print(f"[youtube] query='{query}' retornou {len(items)} videos")

            for item in items:
                video_id = (item.get("id") or {}).get("videoId")
                snippet = item.get("snippet") or {}

                if not video_id:
                    continue

                title = (snippet.get("title") or "").strip()
                description = snippet.get("description") or ""
                channel = snippet.get("channelTitle") or "YouTube"
                published = snippet.get("publishedAt") or ""

                if not title:
                    continue

                pub_date = None

                try:
                    pub_date = datetime.fromisoformat(
                        published.replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except Exception:
                    pub_date = None

                url = f"https://www.youtube.com/watch?v={video_id}"
                cat = _cat(title + " " + description)

                results.append({
                    "o": f"YouTube - {channel}",
                    "u": url,
                    "title": title,
                    "cat": cat,
                    "time": _format_time_br(pub_date),
                    "scope": "Video/Creator - YouTube"
                })

        except Exception as exc:
            print(f"[youtube] falha query='{query}': {exc}")

    results = _dedupe_coverage(results)

    print(f"[youtube] {len(results)} videos reais coletados na semana")

    return results


def _chunk_keywords(keywords, size=5):
    for i in range(0, len(keywords), size):
        yield keywords[i:i + size]


def collect_google_trends_period(global_start, global_end):
    try:
        from pytrends.request import TrendReq
    except Exception as exc:
        print(f"[trends] pytrends nao instalado/disponivel: {exc}")
        return {}

    all_scores = {}

    timeframe = f"{global_start:%Y-%m-%d} {global_end:%Y-%m-%d}"

    # Primeiro tenta Brasil. Se tudo vier zerado, tenta global.
    for geo in ["BR", ""]:
        print(f"[trends] coletando periodo completo timeframe='{timeframe}' geo='{geo or 'GLOBAL'}'")

        geo_scores = {}

        try:
            pytrends = TrendReq(
                hl="pt-BR",
                tz=180,
                timeout=(10, 25),
                retries=2,
                backoff_factor=0.3
            )

            for chunk in _chunk_keywords(TRENDS_KEYWORDS, 5):
                try:
                    pytrends.build_payload(
                        chunk,
                        cat=0,
                        timeframe=timeframe,
                        geo=geo,
                        gprop=""
                    )

                    df = pytrends.interest_over_time()

                    if df is None or df.empty:
                        print(f"[trends] dataframe vazio para chunk={chunk}")
                        continue

                    if "isPartial" in df.columns:
                        df = df.drop(columns=["isPartial"])

                    for date_index, row in df.iterrows():
                        try:
                            date_key = date_index.to_pydatetime().date().isoformat()
                        except Exception:
                            date_key = str(date_index)[:10]

                        if date_key not in geo_scores:
                            geo_scores[date_key] = {}

            
