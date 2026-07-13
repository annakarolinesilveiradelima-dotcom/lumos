
social_reddit.py

Coleta gratuita de posts publicos do Reddit para complementar o Lumos.

Regras:
- Usa endpoints publicos .json do Reddit.
- Nao precisa API key.
- Nao inventa posts.
- Filtra por data real do post.
- Retorna no formato de coverage usado pelo Lumos.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import requests

TIMEOUT = 25

BR_TZ = ZoneInfo("America/Sao_Paulo")

SUBREDDITS = [
    "harrypotter",
    "HarryPotteronHBO",
    "television",
    "HBOMAX"
]

QUERIES = [
    "Harry Potter HBO",
    "Harry Potter Max",
    "Harry Potter series",
    "Harry Potter HBO series",
    "Dominic McLaughlin Harry Potter",
    "Arabella Stanton Harry Potter",
    "Alastair Stout Harry Potter",
    "Paapa Essiedu Harry Potter",
    "John Lithgow Harry Potter"
]

USER_AGENT = "lumos-fandom-intelligence/1.0 by annakarolinesilveiradelima-dotcom"

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]


def _dt_from_utc(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except Exception:
        return None


def _format_time_br(dt):
    if not dt:
        return "sem horario disponivel"

    try:
        br = dt.astimezone(BR_TZ)
        return f"{br.day} {PT_MONTHS[br.month - 1]}, {br:%H:%M}"
    except Exception:
        return dt.isoformat()


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
        "perfeito"
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


def collect_reddit_week(start, end):
    """
    Coleta posts de Reddit publicados entre start e end.

    start/end devem ser datetime com timezone.
    """

    headers = {
        "User-Agent": USER_AGENT
    }

    results = []

    for subreddit in SUBREDDITS:
        for query in QUERIES:
            url = (
                f"https://www.reddit.com/r/{subreddit}/search.json"
                f"?q={quote_plus(query)}"
                f"&restrict_sr=1"
                f"&sort=new"
                f"&t=all"
                f"&limit=25"
            )

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=TIMEOUT
                )

                print(
                    f"[reddit] r/{subreddit} query='{query}' "
                    f"status={response.status_code}"
                )

                if response.status_code == 429:
                    print("[reddit] limite temporario do Reddit. Parando coleta desta semana.")
                    return _dedupe(results)

                if response.status_code != 200:
                    print("[reddit] resposta:", response.text[:300])
                    continue

                data = response.json()
                children = data.get("data", {}).get("children", [])

                for child in children:
                    post = child.get("data", {})
                    created = _dt_from_utc(post.get("created_utc"))

                    if not created:
                        continue

                    if not (start <= created <= end):
                        continue

                    title = (post.get("title") or "").strip()
                    permalink = post.get("permalink", "")
                    score = post.get("score", 0)
                    comments = post.get("num_comments", 0)
                    selftext = post.get("selftext") or ""

                    if not title or not permalink:
                        continue

                    full_url = "https://www.reddit.com" + permalink
                    cat = _cat(title + " " + selftext)

                    results.append({
                        "o": f"Reddit · r/{subreddit}",
                        "u": full_url,
                        "title": title,
                        "cat": cat,
                        "time": _format_time_br(created),
                        "scope": f"Social · score {score} · {comments} comentarios"
                    })

                time.sleep(1)

            except Exception as exc:
                print(f"[reddit] falha r/{subreddit} query='{query}': {exc}")

    results = _dedupe(results)

    print(f"[reddit] {len(results)} posts reais coletados na semana")

    return results
