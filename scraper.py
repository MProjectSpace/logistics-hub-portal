#!/usr/bin/env python3
"""
Pelindo TPKS Webaccess Scraper for Logistics Hub Portal
Repository: https://github.com/mprojectspace/logistics-hub-portal
Live Site: https://mprojectspace.github.io/logistics-hub-portal/
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup


BASE_URL = "https://ibstpks.pelindo.co.id"
WEBACCESS_URL = f"{BASE_URL}/webaccess"
OUTPUT_FILE = Path("data.json")


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(value):
    value = clean_text(value)

    if not value:
        return ""

    if value.startswith("javascript:"):
        return ""

    return urljoin(BASE_URL, value)


# ============================================================
# RECORD STRUCTURE
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
        "historyUrl": ""
    }


# ============================================================
# URL / ID EXTRACTION
# ============================================================

def extract_ves_id(url):
    if not url:
        return ""

    match = re.search(
        r"[?&]ves_id=([^&]+)",
        url,
        flags=re.IGNORECASE
    )

    if match:
        return clean_text(match.group(1))

    return ""


# ============================================================
# PARSE SINGLE VESSEL BLOCK
# ============================================================

def parse_vessel_block(block_soup):
    """
    Parse one vessel block.

    A normal vessel block contains:
        <div class="ves_along_sched"><b>VESSEL (CODE)</b></div>
        <div class="ves_along_sched">VOYAGE</div>
        <div class="ves_along_sched">SHIPPING LINE</div>
        ...

    Schedule is different:
        <div class="ves_along_sched"><b>WAN HAI 311</b></div>
        <div class="ves_along_sched">S259 / N260</div>
        <div class="ves_along_sched">ETB : ...</div>

    Therefore vessel code is optional.
    """

    divs = block_soup.find_all(
        "div",
        class_="ves_along_sched"
    )

    if not divs:
        return None

    record = make_empty_record()

    # --------------------------------------------------------
    # LINKS
    # --------------------------------------------------------

    for a in block_soup.find_all(
        "a",
        attrs={"data-url": True}
    ):

        raw_url = a.get("data-url", "")
        url = normalize_url(raw_url)

        link_text = clean_text(
            a.get_text()
        ).lower()

        if not url:
            continue

        ves_id = extract_ves_id(url)

        if ves_id and not record["vesId"]:
            record["vesId"] = ves_id

        if "vessel_audit" in url:
            record["historyUrl"] = url

        elif (
            "ves_schedule_det" in url
            or "do=vessel" in url
            or "detail" in link_text
        ):
            record["detailUrl"] = url

    # --------------------------------------------------------
    # COLLECT CLEAN DIV TEXT
    # --------------------------------------------------------

    lines = []

    for d in divs:

        # Do not treat the link container as normal data.
        if d.find("a", attrs={"data-url": True}):
            continue

        text = clean_text(
            d.get_text(" ", strip=True)
        )

        if text:
            lines.append(text)

    if not lines:
        return None

    # --------------------------------------------------------
    # VESSEL NAME / CODE
    # --------------------------------------------------------

    first_b = None

    for d in divs:

        b = d.find("b")

        if b:
            candidate = clean_text(
                b.get_text()
            )

            if candidate:
                first_b = candidate
                break

    if not first_b:
        return None

    # Normal vessel:
    # TELUK BINTUNI (TEBI065)
    match_code = re.match(
        r"^(.*?)\s*\(([^()]+)\)$",
        first_b
    )

    if match_code:

        record["vesselName"] = clean_text(
            match_code.group(1)
        )

        record["vesselCode"] = clean_text(
            match_code.group(2)
        )

    else:

        # Schedule does not provide vessel code
        # in the title.
        record["vesselName"] = first_b

    # --------------------------------------------------------
    # PARSE DATA LINES
    # --------------------------------------------------------

    for index, line in enumerate(lines):

        # --------------------------------------------
        # TYPE
        # --------------------------------------------

        if line in (
            "INTERNATIONAL",
            "DOMESTIC"
        ):

            record["type"] = line

            continue

        # --------------------------------------------
        # ETA
        # --------------------------------------------

        if line.startswith("ETA :"):

            record["eta"] = clean_text(
                line.replace(
                    "ETA :",
                    "",
                    1
                )
            )

            continue

        # --------------------------------------------
        # ETB
        # --------------------------------------------

        if line.startswith("ETB :"):

            record["etb"] = clean_text(
                line.replace(
                    "ETB :",
                    "",
                    1
                )
            )

            continue

        # --------------------------------------------
        # ATB
        # --------------------------------------------

        if line.startswith("ATB :"):

            record["atb"] = clean_text(
                line.replace(
                    "ATB :",
                    "",
                    1
                )
            )

            continue

        # --------------------------------------------
        # ETD
        # --------------------------------------------

        if line.startswith("ETD :"):

            record["etd"] = clean_text(
                line.replace(
                    "ETD :",
                    "",
                    1
                )
            )

            continue

        # --------------------------------------------
        # ATD
        # --------------------------------------------

        if line.startswith("ATD :"):

            record["atd"] = clean_text(
                line.replace(
                    "ATD :",
                    "",
                    1
                )
            )

            continue

        # --------------------------------------------
        # OPEN STACK
        # --------------------------------------------

        if line.startswith("Open Stack :"):

            record["openStack"] = clean_text(
                line.replace(
                    "Open Stack :",
                    "",
                    1
                )
            )

            continue

        # --------------------------------------------
        # CLOSING TIME
        # --------------------------------------------

        if line.startswith("Closing Time :"):

            record["closingTime"] = clean_text(
                line.replace(
                    "Closing Time :",
                    "",
                    1
                )
            )

            continue

        # --------------------------------------------
        # BOOKING / OPEN / ACTUAL
        # --------------------------------------------

        if line.startswith(
            "Booking / Open / Actual :"
        ):

            value = clean_text(
                line.replace(
                    "Booking / Open / Actual :",
                    "",
                    1
                )
            )

            parts = [
                clean_text(part)
                for part in value.split("/")
            ]

            parts = [
                part
                for part in parts
                if part != ""
            ]

            if len(parts) >= 3:

                record["booking"] = parts[0]
                record["open"] = parts[1]
                record["actual"] = parts[2]

            continue

        # --------------------------------------------
        # EXPORT
        # --------------------------------------------

        if line.startswith(
            "Export Box / Teus :"
        ):

            value = clean_text(
                line.replace(
                    "Export Box / Teus :",
                    "",
                    1
                )
            )

            parts = [
                clean_text(part)
                for part in value.split("/")
            ]

            parts = [
                part
                for part in parts
                if part != ""
            ]

            if len(parts) >= 2:

                record["export"] = parts[0]
                record["exportTeus"] = parts[1]

            continue

        # --------------------------------------------
        # IMPORT
        # --------------------------------------------

        if line.startswith(
            "Import Box / Teus :"
        ):

            value = clean_text(
                line.replace(
                    "Import Box / Teus :",
                    "",
                    1
                )
            )

            parts = [
                clean_text(part)
                for part in value.split("/")
            ]

            parts = [
                part
                for part in parts
                if part != ""
            ]

            if len(parts) >= 2:

                record["import"] = parts[0]
                record["importTeus"] = parts[1]

            continue

        # --------------------------------------------
        # VOYAGE
        # --------------------------------------------

        if not record["voyage"]:

            # Voyage normally contains "/"
            # and does not contain ":".
            if (
                "/" in line
                and ":" not in line
            ):

                record["voyage"] = line

                continue

        # --------------------------------------------
        # SHIPPING LINE
        # --------------------------------------------

        if not record["shippingLine"]:

            if (
                index > 0
                and ":" not in line
                and line not in (
                    "INTERNATIONAL",
                    "DOMESTIC"
                )
                and "/" not in line
            ):

                # Do not mistake vessel title for shipping line.
                if line != record["vesselName"]:

                    record["shippingLine"] = line

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    if not record["vesselName"]:
        return None

    return record


# ============================================================
# PARSE SECTION
# ============================================================

def parse_section(container_elem):
    """
    Parse a section separated by:
        <hr class="ves_along_sched_hr">

    This works for:
        Alongside
        Confirmed
        Open Stack
        Schedule
        History
    """

    if container_elem is None:
        return []

    records = []

    # Work directly with the DOM instead of converting the
    # entire section to a string and using regex.
    current_nodes = []

    for child in container_elem.children:

        # Ignore whitespace/text nodes.
        if getattr(child, "name", None) is None:
            continue

        # HR marks the end of one vessel.
        if (
            child.name == "hr"
            and "ves_along_sched_hr"
            in child.get(
                "class",
                []
            )
        ):

            if current_nodes:

                block_soup = BeautifulSoup(
                    "",
                    "html.parser"
                )

                for node in current_nodes:
                    block_soup.append(
                        BeautifulSoup(
                            str(node),
                            "html.parser"
                        )
                    )

                record = parse_vessel_block(
                    block_soup
                )

                if record:
                    records.append(record)

            current_nodes = []

            continue

        current_nodes.append(child)

    # --------------------------------------------------------
    # Handle final block if there is no trailing HR.
    # --------------------------------------------------------

    if current_nodes:

        block_soup = BeautifulSoup(
            "",
            "html.parser"
        )

        for node in current_nodes:
            block_soup.append(
                BeautifulSoup(
                    str(node),
                    "html.parser"
                )
            )

        record = parse_vessel_block(
            block_soup
        )

        if record:
            records.append(record)

    return records


# ============================================================
# FIND SECTION
# ============================================================

def find_section(soup, selector):
    """
    Return a section using the actual IDs/classes
    found in the Pelindo HTML.
    """

    element = soup.select_one(selector)

    if element is None:
        logging.warning(
            f"Section tidak ditemukan: {selector}"
        )

    return element


# ============================================================
# SCRAPE HTML
# ============================================================

def scrape_pelindo_html(html_content):

    soup = BeautifulSoup(
        html_content,
        "html.parser"
    )

    # WIB
    tz_wib = timezone(
        timedelta(hours=7)
    )

    now_str = datetime.now(
        tz_wib
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # --------------------------------------------------------
    # ACTUAL PELINDO SECTION SELECTORS
    #
    # These selectors are directly supported by the supplied
    # HTML source.
    # --------------------------------------------------------

    alongside_container = find_section(
        soup,
        "._mCS_1"
    )

    confirmed_container = find_section(
        soup,
        "._mCS_2"
    )

    open_stack_container = find_section(
        soup,
        "._mCS_3"
    )

    schedule_container = find_section(
        soup,
        "#div_ves_schedule"
    )

    history_container = find_section(
        soup,
        "#div_ves_history"
    )

    # --------------------------------------------------------
    # PARSE EACH SECTION INDEPENDENTLY
    # --------------------------------------------------------

    vessel_alongside = parse_section(
        alongside_container
    )

    confirmed_vessel = parse_section(
        confirmed_container
    )

    open_stack = parse_section(
        open_stack_container
    )

    vessel_schedule = parse_section(
        schedule_container
    )

    vessel_history = parse_section(
        history_container
    )

    # --------------------------------------------------------
    # DEBUG SUMMARY
    # --------------------------------------------------------

    logging.info(
        "Alongside: %d",
        len(vessel_alongside)
    )

    logging.info(
        "Confirmed: %d",
        len(confirmed_vessel)
    )

    logging.info(
        "Open Stack: %d",
        len(open_stack)
    )

    logging.info(
        "Schedule: %d",
        len(vessel_schedule)
    )

    logging.info(
        "History: %d",
        len(vessel_history)
    )

    # --------------------------------------------------------
    # SCHEDULE DEBUG
    # --------------------------------------------------------

    for item in vessel_schedule:

        logging.info(
            "Schedule | %s | %s | ETB: %s",
            item["vesselName"],
            item["voyage"],
            item["etb"]
        )

    # --------------------------------------------------------
    # HISTORY DEBUG
    # --------------------------------------------------------

    for item in vessel_history:

        logging.info(
            "History | %s | %s",
            item["vesselName"],
            item["voyage"]
        )

    # --------------------------------------------------------
    # RETURN DATA
    # --------------------------------------------------------

    return {
        "updatedAt": now_str,

        "source": BASE_URL,

        "vesselAlongside": vessel_alongside,

        "confirmedVessel": confirmed_vessel,

        "openStack": open_stack,

        "vesselSchedule": vessel_schedule,

        "vesselHistory": vessel_history,

        "counts": {
            "vesselAlongside": len(
                vessel_alongside
            ),

            "confirmedVessel": len(
                confirmed_vessel
            ),

            "openStack": len(
                open_stack
            ),

            "vesselSchedule": len(
                vessel_schedule
            ),

            "vesselHistory": len(
                vessel_history
            )
        }
    }


# ============================================================
# FETCH URL
# ============================================================

def fetch_url(url):

    try:
        import requests
    except ImportError:

        raise ImportError(
            "Package 'requests' belum terinstall."
        )

    try:
        import urllib3

        urllib3.disable_warnings(
            urllib3.exceptions.InsecureRequestWarning
        )

    except ImportError:
        pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    logging.info(
        "Fetch HTML dari: %s",
        url
    )

    response = requests.get(
        url,
        headers=headers,
        timeout=60,
        verify=False
    )

    response.raise_for_status()

    return response.text


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Pelindo TPKS Data Scraper"
    )

    parser.add_argument(
        "-i",
        "--input",
        default=f"{WEBACCESS_URL}/",
        help="URL target atau path HTML lokal"
    )

    parser.add_argument(
        "-o",
        "--output",
        default="data.json",
        help="Path file output JSON"
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------

    if (
        args.input.startswith("http://")
        or args.input.startswith("https://")
    ):

        try:

            html_content = fetch_url(
                args.input
            )

        except Exception as e:

            logging.error(
                "Gagal mengambil URL %s: %s",
                args.input,
                e
            )

            sys.exit(1)

    else:

        if not os.path.exists(
            args.input
        ):

            logging.error(
                "File lokal tidak ditemukan: %s",
                args.input
            )

            sys.exit(1)

        logging.info(
            "Membaca file HTML lokal: %s",
            args.input
        )

        with open(
            args.input,
            "r",
            encoding="utf-8"
        ) as f:

            html_content = f.read()

    # --------------------------------------------------------
    # SCRAPE
    # --------------------------------------------------------

    data = scrape_pelindo_html(
        html_content
    )

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    logging.info(
        "Counts: %s",
        data["counts"]
    )

    # --------------------------------------------------------
    # SAVE JSON
    # --------------------------------------------------------

    with open(
        args.output,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    logging.info(
        "Data berhasil disimpan di: %s",
        args.output
    )


if __name__ == "__main__":
    main()
