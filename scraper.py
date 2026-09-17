```python
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup, Comment


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://ibstpks.pelindo.co.id/webaccess/information"
OUTPUT_FILE = Path(__file__).resolve().parent / "data.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Connection": "keep-alive",
}

SECTION_NAMES = {
    "vesselAlongside": "VESSEL ALONGSIDE",
    "confirmedVessel": "CONFIRMED VESSEL",
    "openStack": "OPEN STACK",
    "vesselSchedule": "VESSEL SCHEDULE",
    "vesselHistory": "VESSEL HISTORY",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    """Normalize whitespace and return a clean string."""
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_date(value):
    """
    Normalize Pelindo date format.

    Input examples:
        17/09/2026 08:00
        17/09/2026

    Output remains human-readable because the dashboard uses
    Pelindo's original date/time format.
    """
    value = clean(value)

    if not value:
        return ""

    formats = [
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)

            if "%H:%M" in fmt:
                return parsed.strftime("%d/%m/%Y %H:%M")

            return parsed.strftime("%d/%m/%Y")

        except ValueError:
            continue

    return value


def number_or_zero(value):
    """Convert a numeric text value to int/float."""
    value = clean(value)

    if not value:
        return 0

    value = value.replace(",", "")

    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return 0

    number = float(match.group(0))

    if number.is_integer():
        return int(number)

    return number


def parse_name_code(value):
    """
    Parse:
        EVER OBEY (OBEY037)

    into:
        vesselName = EVER OBEY
        vesselCode = OBEY037
    """
    value = clean(value)

    match = re.match(
        r"^(.*?)\s*\(([^()]+)\)\s*$",
        value
    )

    if match:
        return (
            clean(match.group(1)),
            clean(match.group(2)),
        )

    return value, ""


def make_absolute_url(url):
    if not url:
        return ""

    return unquote(
        urljoin(BASE_URL, url)
    )


# ============================================================
# RAW SECTION DETECTION
# ============================================================

def find_section_comment_positions(raw_html):
    """
    Pelindo HTML contains comments such as:

        <!-- ########## VESSEL SCHEDULE ########## -->

    We use those comments to identify sections.

    This is safer than relying on:
        _mCS_1
        _mCS_2
        _mCS_3
        _mCS_4

    because those IDs can change when the website layout changes.
    """

    positions = {}

    comments = re.finditer(
        r"<!--\s*##########\s*(.*?)\s*##########\s*-->",
        raw_html,
        flags=re.I | re.S,
    )

    for match in comments:
        title = clean(match.group(1)).upper()

        for key, section_name in SECTION_NAMES.items():

            if title == section_name:
                positions[key] = match.start()

    return positions


def extract_section_html(raw_html, section_key):
    """
    Extract HTML belonging to one Pelindo section.
    """

    positions = find_section_comment_positions(raw_html)

    if section_key not in positions:
        return ""

    start = positions[section_key]

    later_positions = [
        position
        for key, position in positions.items()
        if position > start
    ]

    if later_positions:
        end = min(later_positions)
    else:
        end = len(raw_html)

    return raw_html[start:end]


# ============================================================
# VESSEL BLOCK EXTRACTION
# ============================================================

def extract_vessel_blocks(section_html):
    """
    Pelindo vessel sections use:

        <div class="ves_along_sched">...</div>

    and separate vessel records with:

        <hr class="ves_along_sched_hr">

    We collect all .ves_along_sched elements belonging
    to one vessel until the next HR separator.
    """

    if not section_html:
        return []

    soup = BeautifulSoup(section_html, "lxml")

    blocks = []

    current = []

    # Only inspect direct-ish content vessel elements.
    elements = soup.find_all(
        ["div", "hr"],
        class_=re.compile(r"ves_along_sched")
    )

    for element in elements:

        classes = element.get("class", [])

        # Separator between vessel records.
        if (
            element.name == "hr"
            and "ves_along_sched_hr" in classes
        ):
            if current:
                blocks.append(current)
                current = []

            continue

        # Vessel data element.
        if (
            element.name == "div"
            and "ves_along_sched" in classes
        ):
            current.append(element)

    if current:
        blocks.append(current)

    return blocks


# ============================================================
# LINK EXTRACTION
# ============================================================

def extract_links(block):

    detail_url = ""
    history_url = ""
    ves_id = ""

    for element in block:

        for link in element.find_all("a"):

            data_url = (
                link.get("data-url")
                or link.get("href")
                or ""
            )

            data_url = unquote(data_url)

            # ------------------------------------------------
            # Container Detail
            # ------------------------------------------------

            if "do=vessel" in data_url:
                detail_url = make_absolute_url(data_url)

            # ------------------------------------------------
            # Vessel History
            # ------------------------------------------------

            if "do=vessel_audit" in data_url:
                history_url = make_absolute_url(data_url)

            # ------------------------------------------------
            # Schedule Detail
            # ------------------------------------------------

            if "do=ves_schedule_det" in data_url:
                detail_url = make_absolute_url(data_url)

            # ------------------------------------------------
            # Vessel ID
            # ------------------------------------------------

            match = re.search(
                r"[?&]ves_id=([^&]+)",
                data_url,
                flags=re.I,
            )

            if match:
                candidate = clean(
                    unquote(match.group(1))
                )

                if candidate:
                    ves_id = candidate

    return {
        "detailUrl": detail_url,
        "historyUrl": history_url,
        "vesId": ves_id,
    }


# ============================================================
# FIELD PARSERS
# ============================================================

def parse_booking_open_actual(text):

    match = re.search(
        r"Booking\s*/\s*Open\s*/\s*Actual\s*:\s*"
        r"([\d.,]+)\s*/\s*([\d.,]+)\s*/\s*([\d.,]+)",
        text,
        flags=re.I,
    )

    if not match:
        return 0, 0, 0

    return (
        number_or_zero(match.group(1)),
        number_or_zero(match.group(2)),
        number_or_zero(match.group(3)),
    )


def parse_box_teus(text):

    match = re.search(
        r"(Export|Import)\s+Box\s*/\s*Teus\s*:\s*"
        r"([\d.,]+)\s*/\s*([\d.,]+)",
        text,
        flags=re.I,
    )

    if not match:
        return None

    direction = match.group(1).lower()

    boxes = number_or_zero(match.group(2))
    teus = number_or_zero(match.group(3))

    return direction, boxes, teus


# ============================================================
# STANDARD VESSEL OBJECT
# ============================================================

def empty_vessel():

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

        "booking": 0,
        "open": 0,
        "actual": 0,

        "export": 0,
        "exportTeus": 0,

        "import": 0,
        "importTeus": 0,

        "vesId": "",

        "detailUrl": "",
        "historyUrl": "",
    }


# ============================================================
# VESSEL BLOCK PARSER
# ============================================================

def parse_vessel_block(block, section_key):

    if not block:
        return None

    texts = []

    for element in block:

        text = clean(
            element.get_text(
                " ",
                strip=True
            )
        )

        if text:
            texts.append(text)

    if not texts:
        return None

    item = empty_vessel()

    # --------------------------------------------------------
    # Vessel Name
    # --------------------------------------------------------

    vessel_name, vessel_code = parse_name_code(
        texts[0]
    )

    item["vesselName"] = vessel_name
    item["vesselCode"] = vessel_code

    # --------------------------------------------------------
    # Voyage
    # --------------------------------------------------------

    if len(texts) > 1:

        candidate = texts[1]

        if (
            ":" not in candidate
            and candidate.lower()
            not in {
                "detail container",
                "history",
            }
        ):
            item["voyage"] = candidate

    # --------------------------------------------------------
    # Parse labelled values
    # --------------------------------------------------------

    for text in texts:

        lower = text.lower()

        # ETA
        if lower.startswith("eta"):
            match = re.search(
                r"ETA\s*:\s*(.*)",
                text,
                flags=re.I,
            )

            if match:
                item["eta"] = normalize_date(
                    match.group(1)
                )

        # ETB
        elif lower.startswith("etb"):
            match = re.search(
                r"ETB\s*:\s*(.*)",
                text,
                flags=re.I,
            )

            if match:
                item["etb"] = normalize_date(
                    match.group(1)
                )

        # ATB
        elif lower.startswith("atb"):
            match = re.search(
                r"ATB\s*:\s*(.*)",
                text,
                flags=re.I,
            )

            if match:
                item["atb"] = normalize_date(
                    match.group(1)
                )

        # ETD
        elif lower.startswith("etd"):
            match = re.search(
                r"ETD\s*:\s*(.*)",
                text,
                flags=re.I,
            )

            if match:
                item["etd"] = normalize_date(
                    match.group(1)
                )

        # ATD
        elif lower.startswith("atd"):
            match = re.search(
                r"ATD\s*:\s*(.*)",
                text,
                flags=re.I,
            )

            if match:
                item["atd"] = normalize_date(
                    match.group(1)
                )

        # Open Stack
        elif lower.startswith("open stack"):
            match = re.search(
                r"Open\s+Stack\s*:\s*(.*)",
                text,
                flags=re.I,
            )

            if match:
                item["openStack"] = normalize_date(
                    match.group(1)
                )

        # Closing
        elif lower.startswith("closing"):
            match = re.search(
                r"Closing\s+Time\s*:\s*(.*)",
                text,
                flags=re.I,
            )

            if match:
                item["closingTime"] = normalize_date(
                    match.group(1)
                )

        # Booking / Open / Actual
        elif "booking" in lower and "actual" in lower:

            (
                item["booking"],
                item["open"],
                item["actual"],
            ) = parse_booking_open_actual(text)

        # Export / Import
        box_data = parse_box_teus(text)

        if box_data:

            direction, boxes, teus = box_data

            item[direction] = boxes
            item[f"{direction}Teus"] = teus

    # --------------------------------------------------------
    # Shipping Line + Type
    # --------------------------------------------------------

    for text in texts[1:]:

        upper = clean(text).upper()

        if upper in {
            "DOMESTIC",
            "INTERNATIONAL",
        }:
            item["type"] = upper
            continue

        # Shipping line is normally an unlabelled text
        # between voyage and type.
        if (
            not item["shippingLine"]
            and section_key in {
                "confirmedVessel",
                "openStack",
                "vesselHistory",
            }
            and ":" not in text
            and text != item["voyage"]
            and upper not in {
                "DOMESTIC",
                "INTERNATIONAL",
            }
            and "[ DETAIL CONTAINER ]" not in upper
            and "[ HISTORY ]" not in upper
        ):
            item["shippingLine"] = text

    # --------------------------------------------------------
    # URLs / Vessel ID
    # --------------------------------------------------------

    links = extract_links(block)

    item["detailUrl"] = links["detailUrl"]
    item["historyUrl"] = links["historyUrl"]

    item["vesId"] = (
        links["vesId"]
        or item["vesselCode"]
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not item["vesselName"]:
        return None

    invalid_names = {
        "detail",
        "history",
        "vessel schedule",
        "vessel history",
    }

    if item["vesselName"].lower() in invalid_names:
        return None

    return item


# ============================================================
# SECTION PARSER
# ============================================================

def parse_section(raw_html, section_key):

    section_html = extract_section_html(
        raw_html,
        section_key,
    )

    if not section_html:
        return []

    blocks = extract_vessel_blocks(
        section_html
    )

    records = []
    seen = set()

    for block in blocks:

        item = parse_vessel_block(
            block,
            section_key,
        )

        if not item:
            continue

        unique_key = (
            item["vesselName"].upper(),
            item["voyage"].upper(),
            item["vesId"].upper(),
        )

        if unique_key in seen:
            continue

        seen.add(unique_key)

        records.append(item)

    return records


# ============================================================
# VESSEL SCHEDULE AJAX
# ============================================================

def request_vessel_schedule(session):

    """
    Pelindo provides:

        POST /webaccess/information

    with:

        do=search_vessel_schedule
        vesName=
        fromDt=
        toDt=

    This is the same endpoint used by the site's
    searchVessel() JavaScript.
    """

    payload = {
        "do": "search_vessel_schedule",
        "vesName": "",
        "fromDt": "",
        "toDt": "",
    }

    try:

        response = session.post(
            BASE_URL,
            data=payload,
            headers={
                **HEADERS,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": BASE_URL,
            },
            timeout=100,
        )

        response.raise_for_status()

        return response.text

    except requests.RequestException as exc:

        print(
            f"[WARNING] Vessel Schedule AJAX failed: {exc}"
        )

        return ""


def parse_schedule_ajax(html):

    if not html:
        return []

    # The AJAX response may contain only the schedule
    # content without the original section comment.
    wrapped_html = (
        "<!-- ########## VESSEL SCHEDULE ########## -->"
        + html
    )

    return parse_section(
        wrapped_html,
        "vesselSchedule",
    )


# ============================================================
# MAIN PAGE REQUEST
# ============================================================

def get_main_page(session):

    response = session.get(
        BASE_URL,
        params={
            "do": "home"
        },
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()

    return response.text


# ============================================================
# DATA VALIDATION
# ============================================================

def validate_data(data):

    required_sections = [
        "vesselAlongside",
        "confirmedVessel",
        "openStack",
        "vesselSchedule",
        "vesselHistory",
    ]

    for section in required_sections:

        if section not in data:
            data[section] = []

        if not isinstance(
            data[section],
            list
        ):
            data[section] = []

    data["counts"] = {
        section: len(data[section])
        for section in required_sections
    }

    return data


# ============================================================
# SCRAPER
# ============================================================

def scrape():

    print("=" * 70)
    print("PELINDO TPKS SCRAPER")
    print("=" * 70)

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    # --------------------------------------------------------
    # Main page
    # --------------------------------------------------------

    print("[1/5] Downloading Pelindo TPKS page...")

    raw_html = get_main_page(
        session
    )

    print(
        f"[OK] HTML downloaded: {len(raw_html):,} bytes"
    )

    # --------------------------------------------------------
    # Parse five main sections
    # --------------------------------------------------------

    print("[2/5] Parsing Vessel Alongside...")

    vessel_alongside = parse_section(
        raw_html,
        "vesselAlongside",
    )

    print(
        f"      Found: {len(vessel_alongside)}"
    )

    print("[3/5] Parsing Confirmed Vessel...")

    confirmed_vessel = parse_section(
        raw_html,
        "confirmedVessel",
    )

    print(
        f"      Found: {len(confirmed_vessel)}"
    )

    print("[4/5] Parsing Open Stack...")

    open_stack = parse_section(
        raw_html,
        "openStack",
    )

    print(
        f"      Found: {len(open_stack)}"
    )

    print("[5/5] Parsing Vessel Schedule + History...")

    vessel_schedule = parse_section(
        raw_html,
        "vesselSchedule",
    )

    # If the normal HTML does not expose schedule records,
    # use Pelindo's AJAX endpoint as fallback.
    if not vessel_schedule:

        print(
            "      Main schedule empty. "
            "Trying Pelindo search_vessel_schedule AJAX..."
        )

        schedule_html = request_vessel_schedule(
            session
        )

        vessel_schedule = parse_schedule_ajax(
            schedule_html
        )

    vessel_history = parse_section(
        raw_html,
        "vesselHistory",
    )

    print(
        f"      Schedule: {len(vessel_schedule)}"
    )

    print(
        f"      History : {len(vessel_history)}"
    )

    # --------------------------------------------------------
    # Build final JSON
    # --------------------------------------------------------

    now = datetime.now().astimezone()

    data = {

        "source": "Pelindo TPKS WebAccess",

        "sourceUrl": BASE_URL,

        "lastUpdated": now.strftime(
            "%Y-%m-%d %H:%M:%S %z"
        ),

        "scrapedAt": now.isoformat(),

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

        "vesselAlongside": vessel_alongside,

        "confirmedVessel": confirmed_vessel,

        "openStack": open_stack,

        "vesselSchedule": vessel_schedule,

        "vesselHistory": vessel_history,
    }

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    data = validate_data(
        data
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    OUTPUT_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SCRAPE COMPLETED")
    print("=" * 70)

    print(
        f"Vessel Alongside : "
        f"{data['counts']['vesselAlongside']}"
    )

    print(
        f"Confirmed Vessel : "
        f"{data['counts']['confirmedVessel']}"
    )

    prin
```
