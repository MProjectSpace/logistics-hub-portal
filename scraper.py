import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment


BASE_URL = "https://ibstpks.pelindo.co.id"
WEBACCESS_URL = f"{BASE_URL}/webaccess"
INFORMATION_URL = f"{WEBACCESS_URL}/information"

OUTPUT_FILE = Path("data.json")
DEBUG_FILE = Path("debug_pelindo.html")

TIMEOUT = 60

SECTION_NAMES = [
    ("VESSEL ALONGSIDE", "vesselAlongside"),
    ("CONFIRMED VESSEL", "confirmedVessel"),
    ("OPEN STACK", "openStack"),
    ("VESSEL SCHEDULE", "vesselSchedule"),
    ("VESSEL HISTORY", "vesselHistory"),
]

OUTPUT_SECTIONS = [
    "vesselAlongside",
    "confirmedVessel",
    "openStack",
    "vesselSchedule",
    "vesselHistory",
]


session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
})


def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_url(value):
    value = clean_text(value)

    if not value:
        return ""

    if value.startswith("javascript:"):
        return ""

    return urljoin(BASE_URL, value)


def is_voyage(value):
    value = clean_text(value)

    patterns = [
        r"\d+[A-Z]\s*/\s*\d+[A-Z]",
        r"\d+-\d+[A-Z]\s*/\s*\d+-\d+[A-Z]",
        r"\d+/\d{4}\s*/\s*\d+/\d{4}",
        r"[A-Z0-9\-]+S\s*/\s*[A-Z0-9\-]+N",
    ]

    return any(
        re.fullmatch(pattern, value, re.I)
        for pattern in patterns
    )


def extract_dates(text):
    patterns = [
        r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}",
        r"\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}",
        r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}",
    ]

    result = []

    for pattern in patterns:
        result.extend(re.findall(pattern, text))

    return list(dict.fromkeys(result))


def find_labeled_datetime(text, labels):
    for label in labels:
        pattern = (
            rf"{re.escape(label)}"
            rf"\s*:?\s*"
            rf"("
            rf"\d{{2}}/\d{{2}}/\d{{4}}\s+\d{{2}}:\d{{2}}"
            rf"|"
            rf"\d{{2}}-\d{{2}}-\d{{4}}\s+\d{{2}}:\d{{2}}"
            rf"|"
            rf"\d{{4}}-\d{{2}}-\d{{2}}\s+\d{{2}}:\d{{2}}"
            rf")"
        )

        match = re.search(pattern, text, re.I)

        if match:
            return match.group(1)

    return ""


def find_number(text, label):
    pattern = rf"\b{re.escape(label)}\s*:?\s*(\d+(?:\.\d+)?)"

    match = re.search(
        pattern,
        text,
        re.I
    )

    if match:
        return match.group(1)

    return ""


def detect_type(text):
    upper = text.upper()

    if "INTERNATIONAL" in upper:
        return "INTERNATIONAL"

    if "DOMESTIC" in upper:
        return "DOMESTIC"

    return ""


def make_empty_record():
    return {
        "vesselName": "",
        "vesselCode": "",
        "voyage": "",
        "shippingLine": "",
        "type": "",
        "eta": "",
        "etb": "",
        "atb": "",
        "etd": "",
        "atd": "",
        "openStack": "",
        "closingTime": "",
        "booki
