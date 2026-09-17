```python
#!/usr/bin/env python3

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup, Tag

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================
# CONFIG
# ============================================================

SOURCE_URL = "https://ibstpks.pelindo.co.id/webaccess/"
PORTAL_URL = "https://mprojectspace.github.io/logistics-hub-portal/"

TIMEZONE_WIB = timezone(timedelta(hours=7))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value: Any) -> str:
    """
    Normalize whitespace.
    """
    if value is None:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def safe_int(value: Any) -> Any:
    """
    Convert numeric text to integer when possible.
    Otherwise return the original cleaned value.
    """
    value = clean(value)

    if not value:
        return "-"

    value = value.replace(",", "")

    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def title_parts(value: str):
    """
    Convert:
        OKEE CORNELIA (OKEE002)

    into:
        vesselName = OKEE CORNELIA
        vesselCode = OKEE002
    """

    value = clean(value)

    match = re.match(
        r"^(.*?)\s*\(([^()]*)\)\s*$",
        value
    )

    if match:
        return (
            clean(match.group(1)),
            clean(match.group(2)),
        )

    return value, "-"


def normalize_date(value: str) -> str:
    """
    Convert:
        15/09/2026 23:00

    into:
        2026-09-15 23:00

    If conversion fails, return original value.
    """

    value = clean(value)

    if not value or value == "-":
        return "-"

    for fmt in (
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue

    return value


def extract_ves_id(url: str) -> str:
    """
    Extract ves_id from Pelindo URL.
    """

    if not url:
        return "-"

    try:
        query = parse_qs(urlparse(url).query)
        value = query.get("ves_id", ["-"])[0]
        return clean(value)
    except Exception:
        match = re.search(r"[?&]ves_id=([^&]+)", url)
        return clean(match.group(1)) if match else "-"


# ============================================================
# URL HELPERS
# ============================================================

def normalize_url(url: str) -> str:
    """
    Normalize HTML entity encoded URLs.

    BeautifulSoup normally converts &amp; automatically,
    but this function keeps the result safe.
    """

    if not url:
        return "-"

    return (
        url
        .replace("&amp;", "&")
        .replace("&#38;", "&")
        .strip()
    )


# ============================================================
# HTML SECTION EXTRACTION
# ============================================================

def extract_fragment(
    html: str,
    start_pattern: str,
    end_patterns: Optional[List[str]] = None,
) -> str:
    """
    Extract a portion of raw Pelindo HTML.

    This function is intentionally based on HTML markers
    instead of fixed BeautifulSoup indexes because the
    Pelindo page structure can change.
    """

    end_patterns = end_patterns or []

    start_match = re.search(
        start_pattern,
        html,
        flags=re.I | re.S,
    )

    if not start_match:
        return ""

    fragment = html[start_match.start():]

    positions = []

    for pattern in end_patterns:
        match = re.search(
            pattern,
            fragment,
            flags=re.I | re.S,
        )

        if match:
            positions.append(match.start())

    if positions:
        fragment = fragment[:min(positions)]

    return fragment


def extract_comment_section(
    html: str,
    section_name: str,
    next_sections: Optional[List[str]] = None,
) -> str:
    """
    Extract content using:

        <!-- ########## SECTION NAME ########## -->

    This is more reliable than relying on _mCS_ numbers.
    """

    next_sections = next_sections or []

    start_pattern = (
        rf"<!--\s*#+\s*{re.escape(section_name)}\s*#+\s*-->"
    )

    end_patterns = []

    for name in next_sections:
        end_patterns.append(
            rf"<!--\s*#+\s*{re.escape(name)}\s*#+\s*-->"
        )

    return extract_fragment(
        html,
        start_pattern,
        end_patterns,
    )


# ============================================================
# VESSEL BLOCK SPLITTING
# ============================================================

def split_vessel_blocks(container: Any) -> List[BeautifulSoup]:
    """
    Split a section into individual vessel blocks.

    Normal Pelindo structure:

        <div class="ves_along_sched">...</div>
        ...
        <hr class="ves_along_sched_hr">

    The parser also has a fallback for malformed HTML.
    """

    if not container:
        return []

    if isinstance(container, BeautifulSoup):
        html = str(container)
    elif isinstance(container, Tag):
        html = str(container)
    else:
        html = str(container)

    parts = re.split(
        r"<hr\b[^>]*"
        r"class\s*=\s*['\"][^'\"]*"
        r"ves_along_sched_hr"
        r"[^'\"]*['\"][^>]*>",
        html,
        flags=re.I | re.S,
    )

    result = []

    for part in parts:
        if "ves_along_sched" not in part:
            continue

        soup = BeautifulSoup(
            part,
            "html.parser",
        )

        if soup.select_one("div.ves_along_sched"):
            result.append(soup)

    return result


# ============================================================
# VESSEL PARSER
# ============================================================

def parse_box_teus(value: str):
    """
    Convert:

        282 / 401

    into:

        {
            "box": 282,
            "teus": 401
        }
    """

    value = clean(value)

    match = re.match(
        r"^([\d,]+)\s*/\s*([\d,]+)$",
        value,
    )

    if not match:
        return {
            "box": safe_int(value),
            "teus": "-",
        }

    return {
        "box": safe_int(match.group(1)),
        "teus": safe_int(match.group(2)),
    }


def parse_booking_open_actual(value: str):
    """
    Convert:

        870 / 870 / 646

    into structured values.
    """

    value = clean(value)

    parts = [
        clean(x)
        for x in value.split("/")
    ]

    parts = (parts + ["-", "-", "-"])[:3]

    return {
        "booking": safe_int(parts[0]),
        "open": safe_int(parts[1]),
        "actual": safe_int(parts[2]),
    }


def parse_vessel_block(
    block: BeautifulSoup,
    history: bool = False,
) -> Optional[Dict[str, Any]]:

    divs = block.select("div.ves_along_sched")

    if not divs:
        return None

    # --------------------------------------------------------
    # FIND VESSEL TITLE
    # --------------------------------------------------------

    title = ""

    for div in divs:
        bold = div.find("b")

        if bold:
            text = clean(
                bold.get_text(
                    " ",
                    strip=True,
                )
            )

            if text and "(" in text and ")" in text:
                title = text
                break

    if not title:
        return None

    vessel_name, vessel_code = title_parts(title)

    if not vessel_name:
        return None

    # --------------------------------------------------------
    # BASE OBJECT
    # --------------------------------------------------------

    item: Dict[str, Any] = {
        "vesselName": vessel_name,
        "vesselCode": vessel_code,
        "vesId": "-",

        "voyage": "-",
        "shippingLine": "-",
        "type": "-",

        "eta": "-",
        "etb": "-",
        "atb": "-",
        "etd": "-",
        "atd": "-",

        "openStack": "-",
        "closingTime": "-",

        "booking": "-",
        "open": "-",
        "actual": "-",

        "exportBox": "-",
        "exportTeus": "-",
        "importBox": "-",
        "importTeus": "-",

        "detailContainerUrl": "-",
        "historyUrl": "-",
    }

    # --------------------------------------------------------
    # READ TEXT LINES
    # --------------------------------------------------------

    lines: List[str] = []

    for div in divs:

        # Do not treat links as normal text fields.
        if div.find("a", attrs={"data-url": True}):
            continue

        text = clean(
            div.get_text(
                " ",
                strip=True,
            )
        )

        if text:
            lines.append(text)

    # --------------------------------------------------------
    # VESSEL ID FROM URL
    # --------------------------------------------------------

    links = block.find_all(
        "a",
        attrs={"data-url": True},
    )

    for link in links:

        url = normalize_url(
            link.get("data-url", "")
        )

        if not url:
            continue

        ves_id = extract_ves_id(url)

        if ves_id != "-":
            item["vesId"] = ves_id

        title_attr = clean(
            link.get("title", "")
        )

        href_text = clean(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if (
            "detail container" in href_text.lower()
            or "detail container" in title_attr.lower()
            or "[ detail container ]" in href_text.lower()
        ):
            item["detailContainerUrl"] = url

        elif (
            "history" in href_text.lower()
            or "history" in title_attr.lower()
        ):
            item["historyUrl"] = url

    # --------------------------------------------------------
    # PARSE TEXT
    # --------------------------------------------------------

    for index, line in enumerate(lines):

        upper = line.upper()

        # ----------------------------------------------------
        # VOYAGE
        # ----------------------------------------------------

        if (
            item["voyage"] == "-"
            and "/" in line
            and ":" not in line
            and "BOX / TEUS" not in upper
            and "BOOKING / OPEN / ACTUAL" not in upper
        ):
            # Avoid accidentally taking a date-like string.
            if not re.search(
                r"\d{1,2}/\d{1,2}/\d{4}",
                line,
            ):
                item["voyage"] = line
                continue

        # ----------------------------------------------------
        # SHIPPING LINE
        # ----------------------------------------------------

        if (
            item["shippingLine"] == "-"
            and index > 0
            and "INTERNATIONAL" not in upper
            and "DOMESTIC" not in upper
            and not re.match(
                r"^(ETA|ETB|ATB|ETD|ATD)\s*:",
                upper,
            )
            and not "BOX / TEUS" in upper
            and not "BOOKING / OPEN / ACTUAL" in upper
            and "/" not in line
        ):
            # In normal TPKS structure this is immediately
            # after voyage.
            previous = lines[index - 1]

            if previous == item["voyage"]:
                item["shippingLine"] = line
                continue

        # ----------------------------------------------------
        # TYPE
        # ----------------------------------------------------

        if upper in (
            "INTERNATIONAL",
            "DOMESTIC",
        ):
            item["type"] = upper
            continue

        # ----------------------------------------------------
        # STANDARD DATE/TIME FIELDS
        # ----------------------------------------------------

        date_fields = {
            "ETA": "eta",
            "ETB": "etb",
            "ATB": "atb",
            "ETD": "etd",
            "ATD": "atd",
            "OPEN STACK": "openStack",
            "CLOSING TIME": "closingTime",
        }

        matched_date = False

        for label, key in date_fields.items():

            pattern = (
                rf"^{re.escape(label)}\s*:\s*(.+)$"
            )

            match = re.match(
                pattern,
                line,
                flags=re.I,
            )

            if match:
                item[key] = normalize_date(
                    match.group(1)
                )
                matched_date = True
                break

        if matched_date:
            continue

        # ----------------------------------------------------
        # BOOKING / OPEN / ACTUAL
        # ----------------------------------------------------

        if "BOOKING / OPEN / ACTUAL" in upper:

            value = line.split(
                ":",
                1,
            )[1] if ":" in line else ""

            boa = parse_booking_open_actual(
                value
            )

            item["booking"] = boa["booking"]
            item["open"] = boa["open"]
            item["actual"] = boa["actual"]

            continue

        # ----------------------------------------------------
        # EXPORT BOX / TEUS
        # ----------------------------------------------------

        if "EXPORT BOX / TEUS" in upper:

            value = (
                line.split(":", 1)[1]
                if ":" in line
                else ""
            )

            result = parse_box_teus(value)

            item["exportBox"] = result["box"]
            item["exportTeus"] = result["teus"]

            continue

        # ----------------------------------------------------
        # IMPORT BOX / TEUS
        # ----------------------------------------------------

        if "IMPORT BOX / TEUS" in upper:

            value = (
                line.split(":", 1)[1]
                if ":" in line
                else ""
            )

            result = parse_box_teus(value)

            item["importBox"] = result["box"]
            item["importTeus"] = result["teus"]

            continue

    # --------------------------------------------------------
    # FALLBACK SHIPPING LINE
    # --------------------------------------------------------

    if item["shippingLine"] == "-":

        for line in lines:

            upper = line.upper()

            if upper in (
                "INTERNATIONAL",
                "DOMESTIC",
            ):
                continue

            if re.match(
                r"^(ETA|ETB|ATB|ETD|ATD|OPEN STACK|CLOSING TIME)\s*:",
                upper,
            ):
                continue

            if "BOX / TEUS" in upper:
                continue

            if "BOOKING / OPEN / ACTUAL" in upper:
                continue

            if "/" in line:
                continue

            if line == item["vesselName"]:
                continue

            # Usually the shipping line is the first suitable
            # non-date line after voyage.
            if line != item["voyage"]:
                item["shippingLine"] = line
                break

    # --------------------------------------------------------
    # HISTORY FLAG
    # --------------------------------------------------------

    item["history"] = bool(history)

    return item


# ============================================================
# SECTION PARSER
# ============================================================

def parse_section(
    html_or_soup: Any,
    history: bool = False,
) -> List[Dict[str, Any]]:

    if not html_or_soup:
        return []

    if isinstance(
        html_or_soup,
        (BeautifulSoup, Tag),
    ):
        soup = html_or_soup
    else:
        soup = BeautifulSoup(
            str(html_or_soup),
            "html.parser",
        )

    blocks = split_vessel_blocks(soup)

    result = []

    for block in blocks:

        try:
            item = parse_vessel_block(
                block,
                history=history,
            )

            if item and item.get("vesselName"):
                result.append(item)

        except Exception as exc:

            logging.warning(
                "Gagal parse vessel block: %s",
                exc,
            )

    return result


# ============================================================
# SECTION DETECTION
# ============================================================

def parse_marker_sections(
    html: str,
) -> Dict[str, str]:
    """
    Detect all sections between Pelindo comments.

    Example:

        ########## Open Stack ##########
        ########## VESSEL SCHEDULE ##########
        ########## VESSEL HISTORY ##########

    Returns:
        {
            "open_stack": "...",
            "vessel_schedule": "...",
            "vessel_history": "..."
        }
    """

    pattern = re.compile(
        r"<!--\s*#+\s*(.*?)\s*#+\s*-->",
        flags=re.I | re.S,
    )

    matches = list(
        pattern.finditer(html)
    )

    sections: Dict[str, str] = {}

    for index, match in enumerate(matches):

        title = clean(
            match.group(1)
        )

        normalized = re.sub(
            r"[^a-z0-9]+",
            "_",
            title.lower(),
        ).strip("_")

        if not normalized:
            continue

        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = len(html)

        sections[normalized] = html[
            start:end
        ]

    return sections


def find_section(
    sections: Dict[str, str],
    *names: str,
) -> str:

    for name in names:

        key = re.sub(
            r"[^a-z0-9]+",
            "_",
            name.lower(),
        ).strip("_")

        if key in sections:
            return sections[key]

    # Partial fallback
    for key, value in sections.items():

        for name in names:

            normalized = re.sub(
                r"[^a-z0-9]+",
                "_",
                name.lower(),
            ).strip("_")

            if normalized in key:
                return value

    return ""


# ============================================================
# MAIN SCRAPER
# ============================================================

def scrape(html: str) -> Dict[str, Any]:

    logging.info(
        "Memulai parsing HTML Pelindo..."
    )

    # --------------------------------------------------------
    # Detect comment-based sections
    # --------------------------------------------------------

    marker_sections = parse_marker_sections(
        html
    )

    logging.info(
        "Marker sections ditemukan: %d",
        len(marker_sections),
    )

    # --------------------------------------------------------
    # OPEN STACK
    # --------------------------------------------------------

    open_stack_html = find_section(
        marker_sections,
        "Open Stack",
        "OPEN STACK",
    )

    open_stack = parse_section(
        open_stack_html
    )

    # --------------------------------------------------------
    # VESSEL SCHEDULE
    # --------------------------------------------------------

    schedule_html = find_section(
        marker_sections,
        "VESSEL SCHEDULE",
        "Vessel Schedule",
    )

    vessel_schedule = parse_section(
        schedule_html
    )

    # --------------------------------------------------------
    # VESSEL HISTORY
    # --------------------------------------------------------

    history_html = find_section(
        marker_sections,
        "VESSEL HISTORY",
        "Vessel History",
    )

    vessel_history = parse_section(
        history_html,
        history=True,
    )

    # --------------------------------------------------------
    # FALLBACK: ID BASED SECTIONS
    #
    # Keep compatibility with older TPKS HTML.
    # --------------------------------------------------------

    if not vessel_schedule:

        schedule_fragment = extract_fragment(
            html,
            r'<div[^>]+id=["\']div_ves_schedule["\'][^>]*>',
            [
                r'<!--\s*#+\s*VESSEL HISTORY',
            ],
        )

        if schedule_fragment:
            vessel_schedule = parse_section(
                schedule_fragment
            )

    if not vessel_history:

        history_fragment = extract_fragment(
            html,
            r'<div[^>]+id=["\']div_ves_history["\'][^>]*>',
            [],
        )

        if history_fragment:
            vessel_history = parse_section(
                history_fragment,
                history=True,
            )

    # --------------------------------------------------------
    # LEGACY SECTIONS
    #
    # Try old _mCS_ containers only if marker parsing did not
    # produce records.
    # --------------------------------------------------------

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    legacy_sections = {}

    for number in range(1, 10):

        selector_candidates = [
            f".content_vessel._mCS_{number}",
            f"#mCSB_{number} .mCSB_container",
            f"#mCSB_{number}",
        ]

        found = None

        for selector in selector_candidates:

            found = soup.select_one(
                selector
            )

            if found:
                break

        if found:

            legacy_sections[number] = parse_section(
                found
            )

    # Older layout mapping
    vessel_alongside = (
        legacy_sections.get(1, [])
        if legacy_sections
        else []
    )

    confirmed_vessel = (
        legacy_sections.get(2, [])
        if legacy_sections
        else []
    )

    if not open_stack:
        open_stack = legacy_sections.get(
            3,
            [],
        )

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    now = datetime.now(
        TIMEZONE_WIB
    )

    timestamp_wib = now.strftime(
        "%d/%m/%Y %H:%M WIB"
    )

    timestamp_iso = now.isoformat()

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    result: Dict[str, Any] = {

        "lastUpdated": timestamp_wib,
        "scrapedAt": timestamp_iso,

        "source": (
            "Pelindo TPKS Webaccess"
        ),

        "sourceUrl": SOURCE_URL,
        "portalUrl": PORTAL_URL,

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
            ),
        },
    }

    logging.info(
        "Parsing selesai:"
    )

    logging.info(
        "  Alongside       = %d",
        len(vessel_alongside),
    )

    logging.info(
        "  Confirmed       = %d",
        len(confirmed_vessel),
    )

    logging.info(
        "  Open Stack      = %d",
        len(open_stack),
    )

    logging.info(
        "  Vessel Schedule = %d",
        len(vessel_schedule),
    )

    logging.info(
        "  Vessel History  = %d",
        len(vessel_history),
    )

    return result


# ============================================================
# HTTP FETCH
# ============================================================

def fetch(
    url: str,
) -> str:

    logging.info(
        "Mengambil data dari: %s",
        url,
    )

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    response = session.get(
        url,
        timeout=60,
        verify=False,
        allow_redirects=True,
    )

    response.raise_for_status()

    logging.info(
        "HTTP %s | %d bytes",
        response.status_code,
        len(response.text),
    )

    return response.text


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    data: Dict[str, Any],
    output: str,
):

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    logging.info(
        "data.json berhasil dibuat: %s",
        output,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Pelindo TPKS Vessel Scraper"
        )
    )

    parser.add_argument(
        "-i",
        "--input",
        default=SOURCE_URL,
        help=(
            "URL Pelindo atau file HTML lokal"
        ),
    )

    parser.add_argument(
        "-o",
        "--output",
        default="data.json",
        help=(
            "Output JSON"
        ),
    )

    args = parser.parse_args()

    try:

        # ----------------------------------------------------
        # FETCH / READ
        # ----------------------------------------------------

        if args.input.startswith(
            (
                "http://",
                "https://",
            )
        ):

            html = fetch(
                args.input
            )

        else:

            logging.info(
                "Membaca file lokal: %s",
                args.input,
            )

            with open(
                args.input,
                encoding="utf-8",
            ) as file:

                html = file.read()

        # ----------------------------------------------------
        # SCRAPE
        # ----------------------------------------------------

        data = scrape(
            html
        )

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        save_json(
            data,
            args.output,
        )

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        counts = data.get(
            "counts",
            {},
        )

        total = sum(
            value
            for value in counts.values()
            if isinstance(value, int)
        )

        logging.info(
            "Total record seluruh section: %d",
            total,
        )

    except KeyboardInterrupt:

        logging.error(
            "Scraper dihentikan oleh user."
        )

        sys.exit(130)

    except Exception as exc:

        logging.exception(
            "Scraper gagal: %s",
            exc,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
```
