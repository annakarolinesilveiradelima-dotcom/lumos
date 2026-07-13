from __future__ import annotations

from datetime import timezone
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
    "Harry Potter HBO series",
    "Harry Potter serie HBO",
    "nova serie Harry Potter",
    "Dominic McLaughlin Harry Potter",
    "Arabella Stanton Harry Potter",
    "Alastair Stout Harry Potter",
    "Paapa Essiedu Harry Potter",
    "John Lithgow Harry Potter"
]


def _iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_time_br(value):
    if not value:
        return "sem horario disponivel"

    try:
        dt = value.astimezone(BR_TZ)
        return f"{dt.day} {PT_MONTHS[dt.month - 1]}, {dt:%H:%M}"
    except Exception:
        return "sem horario disponivel"


def _cat(text):
    t = (text or "").lower()

    speculation_words = [
        "rumor",
        "leak",
        "leaked",
        "vazou",
        "vazamento",
        "speculation",
        "especula",
        "suposto",
        "suposta"
    ]

    nostalgia_words = [
        "nostalgia",
        "nostalgic",
        "movies",
        "filmes",
        "original cast",
        "reboot"
    ]

    negative_words = [
        "bad",
        "hate",
        "worried",
        "terrible",
        "ruined",
        "desnecessario",
        "desnecessário",
        "medo",
        "critica",
        "crítica",
        "criticism"
    ]

    positive_words = [
        "excited",
        "love",
        "great",
        "perfect",
        "faithful",
        "ansioso",
        "ansiosa",
        "amo",
        "amei",
        "fiel",
        "perfeito",
        "reaction",
        "review"
    ]

    if any(word in t for word in speculation_words):
        return "esp"

    if any(word in t for word in nostalgia_words):
        return "nos"

    if any(word in t for word in negative_words):
        return "neg"

    if any(word in t for word in positive_words):
        return "pos"

    return "neu"


def _dedupe(items):
    seen = set()
    out = []

    for item in items:
        url = item.get("u", "")
        title = item.get("title", "")

        if not url or not title:
            continue

        key = url.split("?")[0].lower()

        if key in seen:
            continue

        seen.add(key)
        out.append(item)

    return out


def collect_youtube_week(start, end, api_key):
    if not api_key:
        print("[youtube] YOUTUBE_API_KEY nao configurada. Pulando YouTube.")
        return []

    results = []

    for query in QUERIES:
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

            if response.status_code in (400, 401, 403, 429):
                print("[youtube] resposta:", response.text[:500])
                continue

            if response.status_code != 200:
                print("[youtube] resposta inesperada:", response.text[:500])
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

                url = f"https://www.youtube.com/watch?v={video_id}"
                cat = _cat(title + " " + description)

                results.append({
                    "o": f"YouTube - {channel}",
                    "u": url,
                    "title": title,
                    "cat": cat,
                    "time": _format_published_at(published),
                    "scope": "Video/Creator - YouTube"
                })

        except Exception as exc:
            print(f"[youtube] falha query='{query}': {exc}")

    results = _dedupe(results)

    print(f"[youtube] {len(results)} videos reais coletados na semana")

    return results


def _format_published_at(value):
    if not value:
        return "sem horario disponivel"

    try:
        from datetime import datetime

        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(BR_TZ)
        return f"{dt.day} {PT_MONTHS[dt.month - 1]}, {dt:%H:%M}"
    except Exception:
        return str(value)[:40]
