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

YOUTUBE_QUERIES = [
    "Harry Potter série",
    "Harry Potter serie",
    "Harry Potter série HBO",
    "Harry Potter serie HBO",
    "Harry Potter série Max",
    "Harry Potter serie Max",
    "Harry Potter HBO Brasil",
    "Harry Potter HBO Max Brasil",
    "Harry Potter Max Brasil",
    "Harry Potter série HBO Brasil",
    "Harry Potter serie HBO Brasil",
    "Harry Potter HBO elenco",
    "Harry Potter série elenco",
    "Harry Potter HBO Omelete",
    "nova série Harry Potter",
    "nova serie Harry Potter"
]

BR_CHANNELS = [
    "omelete",
    "omeleteve",
    "jovem nerd",
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

BR_TEXT_SIGNALS = [
    "brasil",
    "hbo brasil",
    "max brasil",
    "hbo max brasil",
    "harry potter série",
    "harry potter serie",
    "série harry potter",
    "serie harry potter",
    "nova série",
    "nova serie",
    "em português",
    "em portugues",
    "português",
    "portugues",
    "pt-br",
    "dublado",
    "legendado",
    "elenco",
    "estreia",
    "omelete",
    "jovem nerd",
    "ei nerd",
    "pipocando",
    "observatório do cinema",
    "observatorio do cinema"
]

BLOCKED_YOUTUBE_SIGNALS = [
    "portugal",
    "india",
    "pakistan",
    "pakistani",
    "hindi",
    "ki new update",
    "subscribe this channel",
    "viral",
    "fyp",
    "breakup",
    "sad",
    "slang",
    "shorts",
    "youtubeshorts",
    "hogwarts nearly",
    "movies never told",
    "cursed child subscribe",
    "draco owns me",
    "flash_viral",
    "rave kishorre",
    "harrypotter_portugal"
]

WIKI_PAGES = [
    {
        "project": "pt.wikipedia.org",
        "article": "Harry_Potter",
        "label": "Harry Potter PT"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter",
        "label": "Harry Potter"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter_(TV_series)",
        "label": "Harry Potter TV series"
    },
    {
        "project": "en.wikipedia.org",
        "article": "Harry_Potter_(film_series)",
        "label": "Harry Potter film series"
    },
    {
