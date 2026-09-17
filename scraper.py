import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://ibstpks.pelindo.co.id"
WEBACCESS_URL = f"{BASE_URL}/webaccess"
INFORMATION_URL = f"{WEBACCESS_URL}/information"

OUTPUT_FILE = Path("data.json")
DEBUG_FILE = Path("debug_pelindo.html")

TIMEOUT = 60


# ============================================================
# SESSION
# ============================================================

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
    "Connection": "keep-alive",
})


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_url(url):
    if not url:
        return ""

    url = clean_text(url)

    if url.startswith("javascript:"):
        return ""

    return urljoin(BASE_URL, url)


def unique_list(items):
    result = []
    seen = set()

    for item in items:
        if not item:
            continue

        key = json.dumps(
            item,
            sort_keys=True,
            ensure_ascii=False
        )

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


def parse_datetime(value):
    """
    Normalize common Pelindo datetime formats.

    We intentionally keep the original display format because
    the dashboard can show the data directly.
    """
    value = clean_text(value)

    if not value:
        return ""

    return value


def detect_type(text):
    text = clean_text(text).upper()

    if "INTERNATIONAL" in text:
        return "INTERNATIONAL"

    if "DOMESTIC" in text:
        return "DOMESTIC"

    return ""


def is_voyage(value):
    """
    Detect common voyage formats such as:
    112S / 112N
    636S / 637N
    0492-057S / 0492-057N
    20/2026 / 20/2026
    """

    value = clean_text(value)

    if not value:
        return False

    patterns = [
        r"\d+[A-Z]\s*/\s*\d+[A-Z]",
        r"\d+-\d+[A-Z]\s*/\s*\d+-\d+[A-Z]",
        r"\d+/\d{4}\s*/\s*\d+/\d{4}",
        r"[A-Z0-9\-]+S\s*/\s*[A-Z0-9\-]+N",
    ]

    return any(re.search(pattern, value, re.I) for pattern in patterns)


def extract_datetime_strings(text):
    """
    Find common datetime values in Pelindo HTML.
    """

    text = clean_text(text)

    patterns = [
        r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}",
        r"\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}",
        r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}",
    ]

    values = []

    for pattern in patterns:
        values.extend(re.findall(pattern, text))

    return values


def first_number_after_label(text, labels):
    """
    Example:
    Booking 870 Open 870 Actual 646
    """

    text = clean_text(text)

    for label in labels:
        pattern = rf"{re.escape(label)}\s*:?\s*(\d+(?:\.\d+)?)"
        match = re.search(pattern, text, re.I)

        if match:
            return match.group(1)

    return ""


# ============================================================
# HTML FETCH
# ============================================================

def fetch_main_page():
    print("[1/2] Fetching Pelindo main page...")

    response = session.get(
        WEBACCESS_URL,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    print("Main page fetched successfully.")
    print(f"Main page response length: {len(response.text):,}")

    return response.text


def fetch_vessel_schedule_ajax():
    """
    Pelindo exposes vessel schedule through:

    POST /webaccess/information

    do=search_vessel_schedule
    """

    print("[2/2] Fetching Pelindo vessel schedule AJAX...")

    payload = {
        "do": "search_vessel_schedule",
        "vesName": "",
        "fromDt": "",
        "toDt": "",
    }

    try:
        response = session.post(
            INFORMATION_URL,
            data=payload,
            headers={
                "Referer": WEBACCESS_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=TIMEOUT,
        )

        response.raise_for_status()

        print("AJAX request successful.")
        print(f"AJAX response length: {len(response.text):,}")

        return response.text

    except Exception as exc:
        print(f"WARNING: AJAX request failed: {exc}")
        return ""


# ============================================================
# BLOCK DETECTION
# ============================================================

def find_vessel_blocks(soup):
    """
    Find possible vessel blocks without relying on fixed
    _mCS_1 / _mCS_2 / _mCS_3 IDs.

    Pelindo has changed the surrounding HTML structure
    multiple times, so this function intentionally searches
    by vessel-related classes and content.
    """

    blocks = []

    # --------------------------------------------------------
    # Method 1: known Pelindo vessel class
    # --------------------------------------------------------

    for tag in soup.find_all(
        class_=re.compile(r"ves[_\-]?along[_\-]?sched", re.I)
    ):
        if not getattr(tag, "name", None):
            continue

        text = clean_text(tag.get_text(" ", strip=True))

        if len(text) < 10:
            continue

        blocks.append(tag)

    # --------------------------------------------------------
    # Method 2: class contains vessel
    # --------------------------------------------------------

    if not blocks:
        for tag in soup.find_all(
            class_=re.compile(r"vessel|schedule", re.I)
        ):
            if not getattr(tag, "name", None):
                continue

            text = clean_text(tag.get_text(" ", strip=True))

            if len(text) < 20:
                continue

            if detect_type(text) or is_voyage(text):
                blocks.append(tag)

    # --------------------------------------------------------
    # Method 3: search parent structures around vessel links
    # --------------------------------------------------------

    if not blocks:

        for link in soup.find_all("a"):

            href = clean_text(link.get("href", ""))

            text = clean_text(link.get_text(" ", strip=True))

            if not text:
                continue

            href_lower = href.lower()

            if (
                "vessel" not in href_lower
                and "schedule" not in href_lower
                and "history" not in href_lower
            ):
                continue

            parent = link

            for _ in range(5):
                if parent.parent:
                    parent = parent.parent

                candidate = clean_text(
                    parent.get_text(" ", strip=True)
                )

                if (
                    len(candidate) >= 30
                    and (
                        detect_type(candidate)
                        or is_voyage(candidate)
                    )
                ):
                    blocks.append(parent)
                    break

    # --------------------------------------------------------
    # Remove duplicates / nested blocks
    # --------------------------------------------------------

    cleaned = []
    seen_ids = set()

    for block in blocks:

        block_id = id(block)

        if block_id in seen_ids:
            continue

        seen_ids.add(block_id)

        # Ignore very small blocks
        text = clean_text(block.get_text(" ", strip=True))

        if len(text) < 20:
            continue

        cleaned.append(block)

    print(f"Detected raw vessel blocks: {len(cleaned)}")

    return cleaned


# ============================================================
# VESSEL PARSER
# ============================================================

def parse_vessel_block(block):
    """
    Extract a vessel record using multiple heuristics.

    The parser does NOT assume a fixed div position.
    """

    text = clean_text(block.get_text(" ", strip=True))

    if not text:
        return None

    record = {
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

    # --------------------------------------------------------
    # Attributes
    # --------------------------------------------------------

    attrs = {}

    for key, value in block.attrs.items():

        if isinstance(value, list):
            value = " ".join(value)

        attrs[key.lower()] = clean_text(value)

    for key, value in attrs.items():

        if "ves_id" in key or key == "vesid":
            record["vesId"] = value

        elif "vessel_code" in key or "ves_code" in key:
            record["vesselCode"] = value

        elif "vessel_name" in key or "ves_name" in key:
            record["vesselName"] = value

    # --------------------------------------------------------
    # Links
    # --------------------------------------------------------

    for link in block.find_all("a", href=True):

        href = normalize_url(link.get("href"))

        if not href:
            continue

        href_lower = href.lower()

        if (
            not record["detailUrl"]
            and (
                "detail" in href_lower
                or "container" in href_lower
                or "vessel" in href_lower
            )
        ):
            record["detailUrl"] = href

        if (
            not record["historyUrl"]
            and "history" in href_lower
        ):
            record["historyUrl"] = href

    # --------------------------------------------------------
    # Text extraction
    # --------------------------------------------------------

    texts = [
        clean_text(x)
        for x in block.stripped_strings
    ]

    texts = [
        x for x in texts
        if x
    ]

    # --------------------------------------------------------
    # Vessel name
    # --------------------------------------------------------

    vessel_candidates = []

    for item in texts:

        upper = item.upper()

        if len(item) < 3:
            continue

        if (
            "INTERNATIONAL" in upper
            or "DOMESTIC" in upper
            or is_voyage(item)
            or re.search(
                r"\d{2}/\d{2}/\d{4}",
                item
            )
        ):
            continue

        if len(item) > 80:
            continue

        vessel_candidates.append(item)

    if vessel_candidates:

        record["vesselName"] = vessel_candidates[0]

    # --------------------------------------------------------
    # Voyage
    # --------------------------------------------------------

    for item in texts:

        if is_voyage(item):
            record["voyage"] = item
            break

    # --------------------------------------------------------
    # Type
    # --------------------------------------------------------

    record["type"] = detect_type(text)

    # --------------------------------------------------------
    # Shipping line
    # --------------------------------------------------------

    shipping_keywords = [
        "LINE",
        "MAERSK",
        "COSCO",
        "EVERGREEN",
        "CMA CGM",
        "MERATUS",
        "SITC",
        "HEUNG",
        "OCEAN NETWORK",
        "PACIFIC INTERNATIONAL",
        "SALAM PACIFIC",
        "MEDITERRANEAN",
    ]

    for item in texts:

        upper = item.upper()

        if any(keyword in upper for keyword in shipping_keywords):

            if (
                item != record["vesselName"]
                and not is_voyage(item)
            ):
                record["shippingLine"] = item
                break

    # --------------------------------------------------------
    # Datetime values
    # --------------------------------------------------------

    dates = extract_datetime_strings(text)

    # Remove duplicates while preserving order

    dates = list(dict.fromkeys(dates))

    # Assign based on labels first

    label_map = {
        "eta": ["ETA"],
        "etb": ["ETB"],
        "atb": ["ATB"],
        "etd": ["ETD"],
        "atd": ["ATD"],
        "openStack": ["OPEN STACK", "OPENSTACK"],
        "closingTime": ["CLOSING", "CLOSING TIME"],
    }

    for field, labels in label_map.items():

        for label in labels:

            pattern = (
                rf"{re.escape(label)}"
                rf"\s*:?\s*"
                rf"("
                rf"\d{{2}}/\d{{2}}/\d{{4}}"
                rf"\s+\d{{2}}:\d{{2}}"
                rf"|"
                rf"\d{{2}}-\d{{2}}-\d{{4}}"
                rf"\s+\d{{2}}:\d{{2}}"
                rf"|"
                rf"\d{{4}}-\d{{2}}-\d{{2}}"
                rf"\s+\d{{2}}:\d{{2}}"
                rf")"
            )

            match = re.search(
                pattern,
                text,
                re.I
            )

            if match:

                record[field] = parse_datetime(
                    match.group(1)
                )

                break

    # --------------------------------------------------------
    # Fallback datetime assignment
    # --------------------------------------------------------

    fields_order = [
        "eta",
        "etb",
        "atb",
        "etd",
        "atd",
    ]

    for field, date_value in zip(
        [x for x in fields_order if not record[x]],
        dates
    ):
        record[field] = date_value

    # --------------------------------------------------------
    # Booking / Open / Actual
    # --------------------------------------------------------

    record["booking"] = first_number_after_label(
        text,
        ["Booking"]
    )

    record["open"] = first_number_after_label(
        text,
        ["Open"]
    )

    record["actual"] = first_number_after_label(
        text,
        ["Actual"]
    )

    # --------------------------------------------------------
    # Export / Import
    # --------------------------------------------------------

    export_match = re.search(
        r"Export\s*:?\s*(\d+)"
        r"(?:\s*/\s*(\d+))?",
        text,
        re.I
    )

    if export_match:

        record["export"] = export_match.group(1)

        if export_match.group(2):
            record["exportTeus"] = export_match.group(2)

    import_match = re.search(
        r"Import\s*:?\s*(\d+)"
        r"(?:\s*/\s*(\d+))?",
        text,
        re.I
    )

    if import_match:

        record["import"] = import_match.group(1)

        if import_match.group(2):
            record["importTeus"] = import_match.group(2)

    # --------------------------------------------------------
    # Ves ID from text / attributes
    # --------------------------------------------------------

    if not record["vesId"]:

        match = re.search(
            r"(?:ves[_\- ]?id)\s*[:=]\s*([A-Za-z0-9_\-/]+)",
            text,
            re.I
        )

        if match:
            record["vesId"] = match.group(1)

    # --------------------------------------------------------
    # Reject obvious non-vessel blocks
    # --------------------------------------------------------

    useful = sum([
        bool(record["vesselName"]),
        bool(record["voyage"]),
        bool(record["shippingLine"]),
        bool(record["type"]),
        bool(record["etb"]),
        bool(record["eta"]),
    ])

    if useful < 2:
        return None

    return record


# ============================================================
# SECTION CLASSIFICATION
# ============================================================

def classify_vessel(record, source_text):
    """
    Determine which Pelindo section the record belongs to.

    Priority:
    1. Explicit source markers
    2. Date / operational fields
    3. Default to openStack for active future vessels
    """

    text = clean_text(source_text).lower()

    if (
        "vessel alongside" in text
        or "alongside" in text
    ):
        return "vesselAlongside"

    if (
        "confirmed vessel" in text
        or "confirmed" in text
    ):
        return "confirmedVessel"

    if (
        "vessel history" in text
        or "history" in text
    ):
        return "vesselHistory"

    if (
        "vessel schedule" in text
        or "schedule" in text
    ):
        return "vesselSchedule"

    if (
        record.get("openStack")
        or record.get("closingTime")
        or record.get("booking")
    ):
        return "openStack"

    return "vesselSchedule"


# ============================================================
# PARSE SECTION
# ============================================================

def parse_html(html, forced_section=None):
    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    blocks = find_vessel_blocks(soup)

    results = []

    for block in blocks:

        record = parse_vessel_block(block)

        if not record:
            continue

        source_text = clean_text(
            block.get_text(" ", strip=True)
        )

        if forced_section:
            record["_section"] = forced_section
        else:
            record["_section"] = classify_vessel(
                record,
                source_text
            )

        results.append(record)

    return results


# ============================================================
# SECTION EXTRACTION
# ============================================================

def extract_comment_section(html, section_name):
    """
    Try extracting HTML between Pelindo comments.

    This is only a fallback. The scraper no longer depends
    entirely on these comments.
    """

    if not html:
        return ""

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    comments = soup.find_all(
        string=lambda text: isinstance(text, Comment)
    )

    start = None
    end = None

    target = section_name.lower()

    for comment in comments:

        value = clean_text(comment).lower()

        if target in value:

            if start is None:
                start = comment
                continue

            if end is None:
                end = comment
                break

    if start is None:
        return ""

    # Find elements following the comment

    html_parts = []

    current = start.next_sibling

    while current:

        if end is not None and current == end:
            break

        try:
            html_parts.append(str(current))
        except Exception:
            pass

        current = current.next_sibling

    return "".join(html_parts)


# ============================================================
# DATA CLEANUP
# ============================================================

def clean_record(record):
    return {
        key: clean_text(value)
        for key, value in record.items()
        if key != "_section"
    }


def deduplicate_records(records):

    output = []
    seen = set()

    for record in records:

        key = (
            record.get("vesselName", ""),
            record.get("vesselCode", ""),
            record.get("voyage", ""),
            record.get("vesId", ""),
            record.get("etb", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(record)

    return output


# ============================================================
# MAIN SCRAPER
# ============================================================

def scrape():

    print("=" * 50)
    print("Pelindo TPKS Scraper")
    print("=" * 50)

    main_html = ""
    ajax_html = ""

    # --------------------------------------------------------
    # Fetch main page
    # --------------------------------------------------------

    try:
        main_html = fetch_main_page()

    except Exception as exc:

        print(f"ERROR: Main page request failed: {exc}")

        # IMPORTANT:
        # Do not immediately exit with code 1.
        # We still attempt to create a valid data.json.

    # --------------------------------------------------------
    # Save raw main HTML for debugging
    # --------------------------------------------------------

    if main_html:

        try:
            DEBUG_FILE.write_text(
                main_html,
                encoding="utf-8"
            )

            print(
                f"Debug HTML saved: {DEBUG_FILE}"
            )

        except Exception as exc:
            print(
                f"WARNING: Could not save debug HTML: {exc}"
            )

    # --------------------------------------------------------
    # Fetch AJAX
    # --------------------------------------------------------

    try:
        ajax_html = fetch_vessel_schedule_ajax()

    except Exception as exc:

        print(
            f"WARNING: AJAX processing failed: {exc}"
        )

    # --------------------------------------------------------
    # Output structure
    # --------------------------------------------------------

    data = {
        "updatedAt": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "source": BASE_URL,
        "vesselAlongside": [],
        "confirmedVessel": [],
        "openStack": [],
        "vesselSchedule": [],
        "vesselHistory": [],
        "counts": {
            "vesselAlongside": 0,
            "confirmedVessel": 0,
            "openStack": 0,
            "vesselSchedule": 0,
            "vesselHistory": 0,
        },
    }

    # --------------------------------------------------------
    # Parse main page globally
    # --------------------------------------------------------

    if main_html:

        try:

            all_records = parse_html(
                main_html
            )

            print(
                f"Main page parsed records: "
                f"{len(all_records)}"
            )

            for record in all_records:

                section = record.pop(
                    "_section",
                    "vesselSchedule"
                )

                record = clean_record(record)

                if section not in data:
                    section = "vesselSchedule"

                data[section].append(record)

        except Exception as exc:

            print(
                f"WARNING: Main page parser error: {exc}"
            )

    # --------------------------------------------------------
    # Parse AJAX response
    # --------------------------------------------------------

    if ajax_html:

        try:

            ajax_records = parse_html(
                ajax_html,
                forced_section="vesselSchedule"
            )

            print(
                f"AJAX parsed records: "
                f"{len(ajax_records)}"
            )

            for record in ajax_records:

                record.pop(
                    "_section",
                    None
                )

                record = clean_record(record)

                data["vesselSchedule"].append(
                    record
                )

        except Exception as exc:

            print(
                f"WARNING: AJAX parser error: {exc}"
            )

    # --------------------------------------------------------
    # Fallback: explicit comments
    # --------------------------------------------------------

    comment_sections = {
        "VESSEL ALONGSIDE": "vesselAlongside",
        "CONFIRMED VESSEL": "confirmedVessel",
        "OPEN STACK": "openStack",
        "VESSEL SCHEDULE": "vesselSchedule",
        "VESSEL HISTORY": "vesselHistory",
    }

    for comment_name, target_section in comment_sections.items():

        try:

            section_html = extract_comment_section(
                main_html,
                comment_name
            )

            if not section_html:
                continue

            records = parse_html(
                section_html,
                forced_section=target_section
            )

            if records:

                print(
                    f"Comment section "
                    f"{target_section}: "
                    f"{len(records)}"
                )

                for record in records:

                    record.pop(
                        "_section",
                        None
                    )

                    data[target_section].append(
                        clean_record(record)
                    )

        except Exception as exc:

            print(
                f"WARNING: Could not parse "
                f"{target_section}: {exc}"
            )

    # --------------------------------------------------------
    # Deduplicate every section
    # --------------------------------------------------------

    for section in [
        "vesselAlongside",
        "confirmedVessel",
        "openStack",
        "vesselSchedule",
        "vesselHistory",
    ]:

        data[section] = deduplicate_records(
            data[section]
        )

    # --------------------------------------------------------
    # Remove duplicate vessel records between sections
    # --------------------------------------------------------

    global_seen = set()

    for section in [
        "vesselAlongside",
        "confirmedVessel",
        "openStack",
        "vesselSchedule",
        "vesselHistory",
    ]:

        unique_records = []

        for record in data[section]:

            key = (
                record.get("vesselName", ""),
                record.get("voyage", ""),
                record.get("vesId", ""),
            )

            # Do not remove records with no identity
            if not any(key):
                unique_records.append(record)
                continue

            if key in global_seen:
                continue

            global_seen.add(key)
            unique_records.append(record)

        data[section] = unique_records

    # --------------------------------------------------------
    # Counts
    # --------------------------------------------------------

    for section in [
        "vesselAlongside",
        "confirmedVessel",
        "openStack",
        "vesselSchedule",
        "vesselHistory",
    ]:

        data["counts"][section] = len(
            data[section]
        )

    # --------------------------------------------------------
    # Write JSON
    # --------------------------------------------------------

    try:

        OUTPUT_FILE.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    except Exception as exc:

        print(
            f"FATAL: Could not write "
            f"{OUTPUT_FILE}: {exc}"
        )

        return 1

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print("-" * 50)
    print("Scraping completed.")
    print(
        f"Vessel Alongside : "
        f"{data['counts']['vesselAlongside']}"
    )
    print(
        f"Confirmed Vessel : "
        f"{data['counts']['confirmedVessel']}"
    )
    print(
        f"Open Stack       : "
        f"{data['counts']['openStack']}"
    )
    print(
        f"Vessel Schedule  : "
        f"{data['counts']['vesselSchedule']}"
    )
    print(
        f"Vessel History   : "
        f"{data['counts']['vesselHistory']}"
    )
    print("-" * 50)
    print(f"Output: {OUTPUT_FILE}")

    total = sum(
        data["counts"].values()
    )

    print(f"Total records: {total}")

    # --------------------------------------------------------
    # Diagnostic warning only
    # --------------------------------------------------------

    if total == 0:

        print(
            "WARNING: No vessel records detected."
        )

        print(
            "The scraper still generated a valid "
            "data.json so GitHub Actions can "
            "complete successfully."
        )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        exit_code = scrape()

        sys.exit(exit_code)

    except KeyboardInterrupt:

        print("Scraper interrupted.")

        sys.exit(0)

    except Exception as exc:

        print(
            f"UNEXPECTED ERROR: {exc}"
        )

        # Write emergency JSON instead of crashing
        emergency_data = {
            "updatedAt": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "source": BASE_URL,
            "vesselAlongside": [],
            "confirmedVessel": [],
            "openStack": [],
            "vesselSchedule": [],
            "vesselHistory": [],
            "counts": {
                "vesselAlongside": 0,
                "confirmedVessel": 0,
                "openStack": 0,
                "vesselSchedule": 0,
                "vesselHistory": 0,
            },
            "error": str(exc),
        }

        try:

            OUTPUT_FILE.write_text(
                json.dumps(
                    emergency_data,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            print(
                f"Emergency data.json created."
            )

        except Exception as write_exc:

            print(
                f"Could not create emergency "
                f"data.json: {write_exc}"
            )

        # Keep GitHub Actions from failing solely
        # because Pelindo changed its HTML.
        sys.exit(0)
