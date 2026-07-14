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
    "nova serie Harry Potter HBO Brasil",
    "Harry Potter HBO elenco Brasil",
    "Paapa Essiedu Harry Potter Brasil",
    "John Lithgow Harry Potter Brasil",
    "Dominic McLaughlin Harry Potter Brasil",
    "Arabella Stanton Harry Potter Brasil"
]

YOUTUBE_QUERIES = [
    "Harry Potter HBO Brasil",
    "Harry Potter HBO Max Brasil",
    "Harry Potter série HBO Brasil",
    "Harry Potter série Max Brasil",
    "Harry Potter HBO Omelete",
    "Harry Potter HBO elenco Brasil",
    "Harry Potter Max Brasil elenco",
    "Harry Potter HBO Brasil Omelete"
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
    "jamesons",
    "coisa de nerd"
]

BLOCKED_YOUTUBE_SIGNALS = [
    "portugal",
    "india",
    "pakistan",
    "pakistani",
    "hindi",
    "ki new update",
