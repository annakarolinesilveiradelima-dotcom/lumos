"""
social_reddit.py

Coleta gratuita de posts públicos do Reddit para complementar o Lumos.

Regras:
- Usa endpoints públicos .json do Reddit.
- Não precisa API key.
- Não inventa posts.
- Filtra por data real do post.
- Retorna no mesmo formato de coverage usado pelo Lumos.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

TIMEOUT = 25

SUBREDDITS = [
    "harrypotter",
    "HarryPotteronHBO",
    "television",
    "HBOMAX",
    "Max",
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
    "John Lithgow Harry Potter",
]

USER_AGENT = "lumos-fandom-intelligence/1.0 by annakarolinesilveiradelima-dotcom"


def _dt_from_utc(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except Exception:
        return None


def _format_time_br(dt):
    if not dt:
        return "sem horário disponível"

    months = [
        "jan", "fev", "mar", "abr", "mai", "jun",
        "jul", "ago", "set", "out", "nov", "dez"
    ]

    # Conversão simples para BRT, sem depender de zoneinfo aqui
    try:
        br = dt.astimezone()
        return f"{br.day} {months[br.month - 1]}, {br:%H:%M}"
    except Exception:
        return dt.isoformat()


def _cat(text):
    t = (text or "").lower()

    if any(w in t for w in ["rumor", "leak", "vazou", "vazamento", "speculation", "especula"]):
        return "esp"

    if any(w in t for w in ["nostalgia", "movies", "filmes", "original cast", "reboot"]):
        return "nos"

    if any(w in t for w in ["bad", "hate", "worried", "terrible", "ruined", "desnecessário", "medo", "crítica"]):
        return "neg"

    if any(w in t for w in ["excited", "love", "great", "perfect", "faithful", "ansioso", "amo", "fiel"]):
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
                response = requests.get(url, headers=headers, timeout=TIMEOUT)

                print(
                    f"[reddit] r/{subreddit} query='{query}' status={response.status_code}"
                )

                if response.status_code == 429:
                    print("[reddit] limite temporário do Reddit. Parando coleta Reddit desta semana.")
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

                    title = post.get("title", "").strip()
                    permalink = post.get("permalink", "")
                    score = post.get("score", 0)
                    comments = post.get("num_comments", 0)

                    if not title or not permalink:
                        continue

                    full_url = "https://www.reddit.com" + permalink
                    cat = _cat(title + " " + post.get("selftext", ""))

                    results.append({
                        "o": f"Reddit · r/{subreddit}",
                        "u": full_url,
                        "title": title,
                        "cat": cat,
                        "time": _format_time_br(created),
                        "scope": f"Social · score {score} · {comments} comentários"
                    })

                time.sleep(1)

            except Exception as exc:
                print(f"[reddit] falha r/{subreddit} query='{query}': {exc}")

    results = _dedupe(results)

    print(f"[reddit] {len(results)} posts reais coletados na semana")

    return results
