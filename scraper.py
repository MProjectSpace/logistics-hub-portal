import json
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment


BASE_URL = "https://ibstpks.pelindo.co.id"
INFORMATION_URL = f"{BASE_URL}/webaccess/information"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE_URL}/webaccess/",
    "X-Requested-With": "XMLHttpRequest",
}


OUTPUT_FILE = "data.json"


SECTION_NAMES = {
    "vesselAlongside": "VESSEL ALONGSIDE",
    "confirmedVessel": "CONFIRMED VESSEL",
    "openStack": "OPEN STACK",
    "vesselSchedule": "VESSEL SCHEDULE",
    "vesselHistory": "VESSEL HISTORY",
}


def clean_text(value):
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def absolute_url(url):
    if not url:
        return ""

    return urljoin(BASE_URL, url)


def normalize_date(value):
    value = clean_text(value)

    if not value:
        return ""

    return value


def extract_number(value):
    value = clean_text(value)

    if not value:
        return 0

    value = value.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return 0

    try:
        number = float(match.group())
        return int(number) if number.is_integer() else number
    except ValueError:
        return 0


def get_label_value(soup, labels):
    """
    Try to find a value based on nearby label text.
    """
    labels = [label.lower() for label in labels]

    for element in soup.find_all(["td", "div", "span", "li"]):
        text = clean_text(element.get_text(" ", strip=True))

        if not text:
            continue

        lower = text.lower()

        for label in labels:
            if label in lower:
                # Same element contains label and value.
                parts = re.split(
                    rf"{re.escape(label)}\s*:?\s*",
                    text,
                    flags=re.IGNORECASE,
                )

                if len(parts) > 1:
                    value = clean_text(parts[-1])

                    if value and value.lower() != label:
                        return value

                # Try next sibling.
                sibling = element.find_next_sibling()

                if sibling:
                    value = clean_text(
                        sibling.get_text(" ", strip=True)
                    )

                    if value:
                        return value

    return ""


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
        "historyUrl": ""
    }


def parse_vessel_block(block):
    """
    Parse one Pelindo vessel block.

    The HTML layout can change, so this parser uses multiple
    fallback methods rather than relying on fixed div indexes.
    """

    result = empty_vessel()

    text = clean_text(block.get_text(" ", strip=True))

    if not text:
        return result

    # ---------------------------------------------------------
    # URLs
    # ---------------------------------------------------------
    links = block.find_all("a", href=True)

    for link in links:
        href = absolute_url(link.get("href", ""))
        link_text = clean_text(link.get_text(" ", strip=True)).lower()

        if not result["detailUrl"] and (
            "detail" in href.lower()
            or "container" in href.lower()
            or "ves_id" in href.lower()
        ):
            result["detailUrl"] = href

        if not result["historyUrl"] and "history" in href.lower():
            result["historyUrl"] = href

        if not result["detailUrl"] and "detail" in link_text:
            result["detailUrl"] = href

        if not result["historyUrl"] and "history" in link_text:
            result["historyUrl"] = href

    # ---------------------------------------------------------
    # Data attributes
    # ---------------------------------------------------------
    attrs = {}

    for tag in block.find_all(True):
        for key, value in tag.attrs.items():
            if key.lower().startswith("data-"):
                attrs[key.lower()] = clean_text(value)

    for key, value in attrs.items():
        if "ves" in key and "id" in key and not result["vesId"]:
            result["vesId"] = value

        if "vessel" in key and "code" in key and not result["vesselCode"]:
            result["vesselCode"] = value

    # ---------------------------------------------------------
    # Tables
    # ---------------------------------------------------------
    rows = block.find_all("tr")

    for row in rows:
        cells = [
            clean_text(cell.get_text(" ", strip=True))
            for cell in row.find_all(["th", "td"])
        ]

        if len(cells) < 2:
            continue

        for i in range(0, len(cells) - 1, 2):
            label = cells[i].lower()
            value = cells[i + 1]

            if "vessel" in label and "name" in label:
                result["vesselName"] = value

            elif label in ("vessel", "vessel name"):
                result["vesselName"] = value

            elif "voyage" in label:
                result["voyage"] = value

            elif "shipping" in label or "line" in label:
                result["shippingLine"] = value

            elif label == "type" or "vessel type" in label:
                result["type"] = value

            elif label == "eta":
                result["eta"] = normalize_date(value)

            elif label == "etb":
                result["etb"] = normalize_date(value)

            elif label == "atb":
                result["atb"] = normalize_date(value)

            elif label == "etd":
                result["etd"] = normalize_date(value)

            elif label == "atd":
                result["atd"] = normalize_date(value)

            elif "open stack" in label:
                result["openStack"] = normalize_date(value)

            elif "closing" in label:
                result["closingTime"] = normalize_date(value)

            elif "booking" in label:
                result["booking"] = extract_number(value)

            elif label == "open":
                result["open"] = extract_number(value)

            elif "actual" in label:
                result["actual"] = extract_number(value)

            elif label.startswith("export"):
                numbers = re.findall(r"\d+(?:,\d+)*", value)

                if numbers:
                    result["export"] = extract_number(numbers[0])

                if len(numbers) > 1:
                    result["exportTeus"] = extract_number(numbers[1])

            elif label.startswith("import"):
                numbers = re.findall(r"\d+(?:,\d+)*", value)

                if numbers:
                    result["import"] = extract_number(numbers[0])

                if len(numbers) > 1:
                    result["importTeus"] = extract_number(numbers[1])

    # ---------------------------------------------------------
    # Generic text fallback
    # ---------------------------------------------------------
    texts = [
        clean_text(x.get_text(" ", strip=True))
        for x in block.find_all(["div", "span", "td", "a"])
    ]

    texts = [x for x in texts if x]

    # First useful text often contains vessel name.
    if not result["vesselName"] and texts:
        for candidate in texts:
            candidate_upper = candidate.upper()

            if (
                len(candidate) >= 3
                and not re.search(r"\d{1,2}/\d{1,2}/\d{4}", candidate)
                and "VESSEL" not in candidate_upper
                and "VOYAGE" not in candidate_upper
                and "BOOKING" not in candidate_upper
            ):
                result["vesselName"] = candidate
                break

    # Try to detect voyage patterns.
    if not result["voyage"]:
        voyage_pattern = re.compile(
            r"\b[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8})?[NS]\b",
            re.IGNORECASE,
        )

        for candidate in texts:
            match = voyage_pattern.search(candidate)

            if match:
                result["voyage"] = candidate
                break

    # ---------------------------------------------------------
    # Date fallback
    # ---------------------------------------------------------
    date_pattern = re.compile(
        r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}"
    )

    dates = []

    for candidate in texts:
        dates.extend(date_pattern.findall(candidate))

    # Remove duplicates but preserve order.
    dates = list(dict.fromkeys(dates))

    if dates:
        if not result["eta"]:
            result["eta"] = dates[0]

        if not result["etb"] and len(dates) > 1:
            result["etb"] = dates[1]

        if not result["etd"] and len(dates) > 2:
            result["etd"] = dates[2]

    # ---------------------------------------------------------
    # Type detection
    # ---------------------------------------------------------
    if not result["type"]:
        upper_text = text.upper()

        if "INTERNATIONAL" in upper_text:
            result["type"] = "INTERNATIONAL"
        elif "DOMESTIC" in upper_text:
            result["type"] = "DOMESTIC"

    # ---------------------------------------------------------
    # Remove obviously invalid vessel name
    # ---------------------------------------------------------
    invalid_names = {
        "",
        "VESSEL",
        "VESSEL NAME",
        "DETAIL",
        "HISTORY",
        "OPEN STACK",
        "CONFIRMED VESSEL",
        "VESSEL SCHEDULE",
        "VESSEL HISTORY",
    }

    if result["vesselName"].strip().upper() in invalid_names:
        result["vesselName"] = ""

    return result


def extract_vessel_blocks(section):
    """
    Detect vessel blocks using Pelindo's vessel CSS classes and
    horizontal separators.
    """

    if not section:
        return []

    blocks = []

    # Primary structure.
    candidates = section.find_all(
        "div",
        class_=re.compile(r"ves_along_sched", re.IGNORECASE)
    )

    # Filter nested/duplicate candidates.
    for candidate in candidates:
        if candidate.find_parent(
            "div",
            class_=re.compile(r"ves_along_sched", re.IGNORECASE)
        ):
            continue

        blocks.append(candidate)

    if blocks:
        return blocks

    # Fallback: split using separator.
    separators = section.find_all(
        "hr",
        class_=re.compile(r"ves_along_sched_hr", re.IGNORECASE)
    )

    if separators:
        html_parts = re.split(
            r'<hr[^>]*class=["\'][^"\']*ves_along_sched_hr[^"\']*["\'][^>]*>',
            str(section),
            flags=re.IGNORECASE,
        )

        for part in html_parts:
            if clean_text(BeautifulSoup(part, "lxml").get_text(" ", strip=True)):
                blocks.append(
                    BeautifulSoup(part, "lxml")
                )

    return blocks


def find_comment_section(soup, section_title):
    """
    Locate a section using HTML comments such as:

    ########## OPEN STACK ##########
    """

    wanted = section_title.upper()

    comments = soup.find_all(
        string=lambda text: isinstance(text, Comment)
    )

    for comment in comments:
        comment_text = clean_text(comment).upper()

        if wanted not in comment_text:
            continue

        start = comment.parent

        collected = []

        for element in start.find_all_next():
            if isinstance(element, Comment):
                current = clean_text(element).upper()

                if (
                    current != comment_text
                    and "##########" in current
                    and any(
                        name in current
                        for name in SECTION_NAMES.values()
                    )
                ):
                    break

            collected.append(element)

        wrapper = BeautifulSoup("<div></div>", "lxml")

        for element in collected:
            wrapper.div.append(
                BeautifulSoup(str(element), "lxml")
            )

        return wrapper.div

    return None


def parse_html_sections(html):
    soup = BeautifulSoup(html, "lxml")

    result = {
        "vesselAlongside": [],
        "confirmedVessel": [],
        "openStack": [],
        "vesselSchedule": [],
        "vesselHistory": [],
    }

    for key, title in SECTION_NAMES.items():
        section = find_comment_section(soup, title)

        if not section:
            continue

        blocks = extract_vessel_blocks(section)

        for block in blocks:
            vessel = parse_vessel_block(block)

            if vessel["vesselName"] or vessel["voyage"]:
                result[key].append(vessel)

    return result


def fetch_page():
    response = requests.get(
        BASE_URL,
        headers=HEADERS,
        timeout=60,
    )

    response.raise_for_status()
    return response.text


def fetch_schedule_ajax():
    """
    Pelindo WebAccess provides an AJAX endpoint:

    POST /webaccess/information
    do=search_vessel_schedule

    This is used as an additional source when the normal page
    does not expose all schedule information.
    """

    payload = {
        "do": "search_vessel_schedule",
        "vesName": "",
        "fromDt": "",
        "toDt": "",
    }

    response = requests.post(
        INFORMATION_URL,
        headers=HEADERS,
        data=payload,
        timeout=100,
    )

    response.raise_for_status()

    return response.text


def merge_vessels(primary, secondary):
    """
    Merge records while avoiding duplicate vessel/voyage records.
    """

    merged = list(primary)

    seen = set()

    for item in merged:
        key = (
            clean_text(item.get("vesselName")).upper(),
            clean_text(item.get("voyage")).upper(),
            clean_text(item.get("vesId")).upper(),
        )

        seen.add(key)

    for item in secondary:
        key = (
            clean_text(item.get("vesselName")).upper(),
            clean_text(item.get("voyage")).upper(),
            clean_text(item.get("vesId")).upper(),
        )

        if key not in seen:
            merged.append(item)
            seen.add(key)

    return merged


def build_output(data):
    now = datetime.now().astimezone().isoformat()

    return {
        "updatedAt": now,
        "source": "Pelindo TPKS WebAccess",

        "vesselAlongside": data.get(
            "vesselAlongside", []
        ),

        "confirmedVessel": data.get(
            "confirmedVessel", []
        ),

        "openStack": data.get(
            "openStack", []
        ),

        "vesselSchedule": data.get(
            "vesselSchedule", []
        ),

        "vesselHistory": data.get(
            "vesselHistory", []
        ),

        "counts": {
            "vesselAlongside": len(
                data.get("vesselAlongside", [])
            ),
            "confirmedVessel": len(
                data.get("confirmedVessel", [])
            ),
            "openStack": len(
                data.get("openStack", [])
            ),
            "vesselSchedule": len(
                data.get("vesselSchedule", [])
            ),
            "vesselHistory": len(
                data.get("vesselHistory", [])
            ),
        },
    }


def main():
    print("========================================")
    print("Pelindo TPKS Scraper")
    print("========================================")

    final_data = {
        "vesselAlongside": [],
        "confirmedVessel": [],
        "openStack": [],
        "vesselSchedule": [],
        "vesselHistory": [],
    }

    # ---------------------------------------------------------
    # 1. Main page
    # ---------------------------------------------------------
    try:
        print("[1/2] Fetching Pelindo main page...")

        html = fetch_page()

        parsed = parse_html_sections(html)

        for key in final_data:
            final_data[key] = merge_vessels(
                final_data[key],
                parsed.get(key, [])
            )

        print("Main page parsed successfully.")

    except Exception as exc:
        print(f"Main page error: {exc}")

    # ---------------------------------------------------------
    # 2. AJAX schedule endpoint
    # ---------------------------------------------------------
    try:
        print("[2/2] Fetching Pelindo vessel schedule AJAX...")

        ajax_html = fetch_schedule_ajax()

        parsed_ajax = parse_html_sections(ajax_html)

        # Schedule endpoint is mainly useful for schedule data.
        final_data["vesselSchedule"] = merge_vessels(
            final_data["vesselSchedule"],
            parsed_ajax.get("vesselSchedule", [])
        )

        # Some responses may return open-stack data too.
        final_data["openStack"] = merge_vessels(
            final_data["openStack"],
            parsed_ajax.get("openStack", [])
        )

        print("AJAX data parsed successfully.")

    except Exception as exc:
        print(f"AJAX error: {exc}")

    # ---------------------------------------------------------
    # Build JSON
    # ---------------------------------------------------------
    output = build_output(final_data)

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("----------------------------------------")
    print("Scraping completed.")
    print(
        f"Vessel Alongside : "
        f"{output['counts']['vesselAlongside']}"
    )
    print(
        f"Confirmed Vessel : "
        f"{output['counts']['confirmedVessel']}"
    )
    print(
        f"Open Stack       : "
        f"{output['counts']['openStack']}"
    )
    print(
        f"Vessel Schedule  : "
        f"{output['counts']['vesselSchedule']}"
    )
    print(
        f"Vessel History   : "
        f"{output['counts']['vesselHistory']}"
    )
    print("----------------------------------------")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
