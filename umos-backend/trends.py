from pytrends.request import TrendReq

def get_trends():
    pytrends = TrendReq(hl="pt-BR", tz=180)

    keywords = [
        "Harry Potter HBO",
        "Harry Potter série",
        "Harry Potter Max"
    ]

    pytrends.build_payload(
        keywords,
        timeframe="today 3-m",
        geo="BR"
    )

    data = pytrends.interest_over_time()

    if data.empty:
        return {
            "interest": 0,
            "keywords": keywords
        }

    latest = int(data[keywords[0]].iloc[-1])

    return {
        "interest": latest,
        "keywords": keywords
    }
