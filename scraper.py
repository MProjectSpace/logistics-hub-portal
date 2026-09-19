#!/usr/bin/env python3

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


URL = "https://ibstpks.pelindo.co.id/webaccess/"

OUTPUT_FILE = Path("data.json")

NAVIGATION_TIMEOUT = 120000
WAIT_AFTER_LOAD = 5000


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ============================================================
# TEXT
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


# ============================================================
# EMPTY RECORD
# ============================================================

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

        "booking": "",
        "open": "",
        "actual": "",

        "export": "",
        "exportTeus": "",
        "import": "",
        "importTeus": "",

        "vesId": "",

        "detailUrl": "",
        "historyUrl": "",
    }


# ============================================================
# EXTRACT ID FROM ONCLICK
# ============================================================

def extract_id_from_onclick(onclick, function_name):
    """
    Contoh:

    waCardDetail('SIBI094')
    waCardHistory('SIBI094')
    """

    if not onclick:
        return ""

    pattern = (
        rf"{re.escape(function_name)}"
        r"\(\s*['\"]([^'\"]+)['\"]\s*\)"
    )

    match = re.search(
        pattern,
        onclick,
        re.IGNORECASE,
    )

    if match:
        return clean_text(match.group(1))

    return ""


# ============================================================
# PARSE VTIME LABELS
# ============================================================

def parse_times(data):
    """
    HTML baru:

    <div class="vtimes">
        <span class="vt-lab">ETA</span>
        <span class="vt-val">...</span>

        <span class="vt-lab">ETB</span>
        <span class="vt-val">...</span>
    </div>

    Kita ambil berdasarkan label, bukan berdasarkan posisi.
    """

    result = {}

    labels = data.get("timeLabels", [])
    values = data.get("timeValues", [])

    for label, value in zip(labels, values):

        label = clean_text(label)
        value = clean_text(value)

        if not label:
            continue

        result[label.lower()] = value

    return result


# ============================================================
# PARSE PROGRESS
# ============================================================

def parse_progress(value):
    """
    Contoh:

    600 / 600 / 442

    menjadi:

    booking = 600
    open    = 600
    actual  = 442
    """

    value = clean_text(value)

    if not value:
        return "", "", ""

    parts = [
        clean_text(x)
        for x in value.split("/")
    ]

    if len(parts) >= 3:

        return (
            parts[0],
            parts[1],
            parts[2],
        )

    return "", "", ""


# ============================================================
# PARSE VESSEL CARD
# ============================================================

def parse_vessel_card(data, category):
    """
    Parser utama untuk .vcard pada HTML baru.

    category:

        alongside
        confirmed
        openStack
        schedule
        history
    """

    record = make_empty_record()

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    record["vesselName"] = clean_text(
        data.get("vesselName", "")
    )

    if not record["vesselName"]:
        return None

    # --------------------------------------------------------
    # VESSEL CODE
    # --------------------------------------------------------

    record["vesselCode"] = clean_text(
        data.get("vesselCode", "")
    )

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    record["type"] = clean_text(
        data.get("type", "")
    )

    # --------------------------------------------------------
    # VOYAGE
    # --------------------------------------------------------

    record["voyage"] = clean_text(
        data.get("voyage", "")
    )

    # --------------------------------------------------------
    # SHIPPING LINE / AGENT
    # --------------------------------------------------------

    record["shippingLine"] = clean_text(
        data.get("agent", "")
    )

    # --------------------------------------------------------
    # VESSEL ID
    # --------------------------------------------------------

    record["vesId"] = clean_text(
        data.get("vesId", "")
    )

    # --------------------------------------------------------
    # TIMES
    # --------------------------------------------------------

    times = parse_times(data)

    record["eta"] = times.get(
        "eta",
        ""
    )

    record["etb"] = times.get(
        "etb",
        ""
    )

    record["atb"] = times.get(
        "atb",
        ""
    )

    record["etd"] = times.get(
        "etd",
        ""
    )

    record["atd"] = times.get(
        "atd",
        ""
    )

    record["openStack"] = times.get(
        "open stack",
        ""
    )

    record["closingTime"] = times.get(
        "closing time",
        ""
    )

    # --------------------------------------------------------
    # HISTORY EXP / IMP
    # --------------------------------------------------------

    record["export"] = times.get(
        "exp",
        ""
    )

    record["import"] = times.get(
        "imp",
        ""
    )

    # --------------------------------------------------------
    # BOOKING / OPEN / ACTUAL
    # --------------------------------------------------------

    (
        record["booking"],
        record["open"],
        record["a]()
