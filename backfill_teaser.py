from __future__ import annotations

import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, quote_plus
from zoneinfo import ZoneInfo

import requests
import config

try:
    from pytrends.request import TrendReq
except Exception:
    TrendReq = None


TIMEOUT = 25
BR_TZ = ZoneInfo("America/Sao_Paulo")

TITLE_ID = getattr(config, "TITLE_ID", "hp")
OUTPUT_DATA = os.environ.get("OUTPUT_DATA", getattr(config, "OUTPUT_DATA", "../data.json"))
HISTORY_DIR = os.environ.get("HISTORY_DIR", getattr(config, "HISTORY_DIR", "../history"))

TEASER_DATE = datetime(2026, 3, 25, 0, 0, 0, tzinfo=BR_TZ)

PT_MONTHS = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez"
]

NEWS_QUERIES = [
    "Harry Potter HBO Brasil",
    "Harry Potter Max Brasil",
    "Harry Potter HBO Max Brasil",
    "serie Harry Potter HBO Brasil",
    "série Harry Potter HBO Brasil",
    "nova serie Harry Potter HBO Brasil",
    "nova série Harry Potter HBO Brasil",
    "Harry Potter HBO elenco Brasil",
    "Paapa Essiedu Harry Potter Brasil",
    "John Lithgow Harry Potter Brasil",
    "Dominic McLaughlin Harry Potter Brasil",
    "Arabella Stanton Harry Potter Brasil"
]

TRENDS_KEYWORDS = [
    "Harry Potter série",
    "Harry Potter HBO",
    "Harry Potter Max",
    "Harry Potter HBO Max",
    "nova série Harry Potter"
]

YOUTUBE_QUERIES = [
    "harry potter série brasil",
    "harry potter serie brasil",
    "nova série harry potter brasil",
    "nova serie harry potter brasil",
    "harry potter hbo max brasil",
    "harry potter hbo elenco",
    "harry potter nova série elenco"
]

X_QUERIES = [
    '(("harry potter" "série") OR ("harry potter" "serie") OR ("harry potter" "hbo") OR ("harry potter" "max")) lang:pt -is:retweet',
    '(("nova série" "harry potter") OR ("nova serie" "harry potter")) lang:pt -is:retweet',
    '(("harry potter" "hbo max") OR ("harry potter" "max brasil") OR ("harry potter" "hbo brasil")) lang:pt -is:retweet',
    '(("harry potter" "elenco") OR ("harry potter" "atores") OR ("harry potter" "atriz")) lang:pt -is:retweet'
]

BR_CHANNELS = [
    "omelete",
    "omeleteve",
    "jovem nerd",
    "jovemnerd",
    "nerdbunker",
    "ei nerd",
    "pipocando",
    "legião dos heróis",
    "legiao dos herois",
    "observatório do cinema",
    "observatorio do cinema",
    "canal peewee",
    "entre migas",
    "super oito",
    "nerdland",
    "cinematologia",
    "refúgio cult",
    "refugio cult",
    "heróis e mais",
    "herois e mais",
    "nerd rabugento",
    "canaltech",
    "tecmundo",
    "adorocinema",
    "cinepop",
    "coisa de nerd"
]

HARRY_POTTER_SIGNALS = [
    "harry potter",
    "potter"
]

SERIES_SIGNALS = [
    "série",
    "serie",
    "nova série",
    "nova serie",
    "hbo",
    "hbo max",
    "max",
    "streaming",
