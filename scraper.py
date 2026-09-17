```python
import json
import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://ibstpks.pelindo.co.id"
INFORMATION_URL = f"{BASE_URL}/webaccess/information"

OUTPUT_FILE = "data.json"
DEBUG_FILE = "debug_pelindo.html"

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
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Referer": f"{BASE_URL}/webaccess/",
}


SECTION_NAMES = {
    "vesselAlongside": "Vessel Alongside",
    "confirmedVessel": "Confirmed Vessel",
    "openStack": "Open Stack",
    "vesselSchedule": "Vessel Schedule",
    "vesselHistory": "Vessel History",
}


def clean(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value).replace("\xa0", " ")
    ).strip()


def absolute_url(value):
    if not value:
        return ""

    return urljoin(BASE_URL, value)


def number(value):
    value = clean(value)

    if not value:
        return 0

    value = value.replace(",", "")

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        value
    )

    if not match:
        return 0

    try:
        result = float(match.group())

        if result.is_integer():
            return int(result)

        return result

    except Exception:
        return 0


def empty_record():
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


def find_value_by_label(block, labels):
    labels = [
        x.lower()
        for x in labels
    ]

    # TABLE
    for row in block.find_all("tr"):

        cells = row.find_all(
            ["th", "td"]
        )

        values = [
            clean(x.get_text(" ", strip=True))
            for x in cells
        ]

        for i, value in enumerate(values):

            lower = value.lower()

            for label in labels:

                if label in lower:

                    if ":" in value:

                        result = value.split(
                            ":",
                            1
                        )[1]

                        if clean(result):
                            return clean(result)

                    if i + 1 < len(values):

                        result = clean(
                            values[i + 1]
                        )

                        if result:
                            return result

    # DIV / SPAN
    elements = block.find_all(
        ["div", "span", "label", "p"]
    )

    for element in elements:

        text = clean(
            element.get_text(
                " ",
                strip=True
            )
        )

        lower = text.lower()

        for label in labels:

            if label not in lower:
                continue

            pattern = (
                rf"{re.escape(label)}"
                rf"\s*:?\s*(.*)"
            )

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                result = clean(
                    match.group(1)
                )

                if result:
                    return result

    return ""


def detect_vessel_name(block):
    """
    Detect vessel name from headings/links first,
    then fallback to the first meaningful text.
    """

    # Headings
    for tag in block.find_all(
        ["h1", "h2", "h3", "h4", "h5", "strong", "b"]
    ):

        text = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        upper = text.upper()

        if upper in {
            "VESSEL",
            "VESSEL NAME",
            "VOYAGE",
            "OPEN STACK",
            "CONFIRMED VESSEL",
            "VESSEL SCHEDULE",
            "VESSEL HISTORY",
        }:
            continue

        if len(text) >= 3:
            return text

    # Links
    for tag in block.find_all("a"):

        text = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if len(text) < 3:
            continue

        if re.search(
            r"\d{1,2}/\d{1,2}/\d{4}",
            text
        ):
            continue

        return text

    return ""


def parse_record(block):

    result = empty_record()

    text = clean(
        block.get_text(
            " ",
            strip=True
        )
    )

    if not text:
        return None

    # ---------------------------------------------------------
    # NAME
    # ---------------------------------------------------------

    result["vesselName"] = (
        detect_vessel_name(block)
    )

    # ---------------------------------------------------------
    # COMMON FIELDS
    # ---------------------------------------------------------

    result["vesselCode"] = find_value_by_label(
        block,
        [
            "vessel code",
            "code",
        ]
    )

    result["voyage"] = find_value_by_label(
        block,
        [
            "voyage",
        ]
    )

    result["shippingLine"] = find_value_by_label(
        block,
        [
            "shipping line",
            "shipping",
            "line",
        ]
    )

    result["type"] = find_value_by_label(
        block,
        [
            "type",
            "vessel type",
        ]
    )

    result["eta"] = find_value_by_label(
        block,
        ["eta"]
    )

    result["etb"] = find_value_by_label(
        block,
        ["etb"]
    )

    result["atb"] = find_value_by_label(
        block,
        ["atb"]
    )

    result["etd"] = find_value_by_label(
        block,
        ["etd"]
    )

    result["atd"] = find_value_by_label(
        block,
        ["atd"]
    )

    result["openStack"] = find_value_by_label(
        block,
        [
            "open stack",
            "openstack",
        ]
    )

    result["closingTime"] = find_value_by_label(
        block,
        [
            "closing time",
            "closing",
        ]
    )

    # ---------------------------------------------------------
    # NUMBERS
    # ---------------------------------------------------------

    result["booking"] = number(
        find_value_by_label(
            block,
            ["booking"]
        )
    )

    result["open"] = number(
        find_value_by_label(
            block,
            ["open"]
        )
    )

    result["actual"] = number(
        find_value_by_label(
            block,
            ["actual"]
        )
    )

    # ---------------------------------------------------------
    # EXPORT / IMPORT
    # ---------------------------------------------------------

    export_text = find_value_by_label(
        block,
        ["export"]
    )

    import_text = find_value_by_label(
        block,
        ["import"]
    )

    export_numbers = re.findall(
        r"\d[\d,]*",
        export_text
    )

    import_numbers = re.findall(
        r"\d[\d,]*",
        import_text
    )

    if export_numbers:

        result["export"] = number(
            export_numbers[0]
        )

    if len(export_numbers) > 1:

        result["exportTeus"] = number(
            export_numbers[1]
        )

    if import_numbers:

        result["import"] = number(
            import_numbers[0]
        )

    if len(import_numbers) > 1:

        result["importTeus"] = number(
            import_numbers[1]
        )

    # ---------------------------------------------------------
    # URLS
    # ---------------------------------------------------------

    for link in block.find_all(
        "a",
        href=True
    ):

        href = absolute_url(
            link.get("href")
        )

        lower = href.lower()

        if not result["detailUrl"]:

            if (
                "detail" in lower
                or "container" in lower
                or "ves_id" in lower
            ):
                result["detailUrl"] = href

        if not result["historyUrl"]:

            if "history" in lower:
                result["historyUrl"] = href

    # ---------------------------------------------------------
    # DATA ATTRIBUTES
    # ---------------------------------------------------------

    for tag in block.find_all(True):

        for key, value in tag.attrs.items():

            if not key.startswith("data-"):
                continue

            value = clean(value)

            lower_key = key.lower()

            if (
                "ves" in lower_key
                and "id" in lower_key
                and not result["vesId"]
            ):
                result["vesId"] = value

            if (
                "vessel" in lower_key
                and "code" in lower_key
                and not result["vesselCode"]
            ):
                result["vesselCode"] = value

    # ---------------------------------------------------------
    # FALLBACK TYPE
    # ---------------------------------------------------------

    upper_text = text.upper()

    if not result["type"]:

        if "INTERNATIONAL" in upper_text:
            result["type"] = "INTERNATIONAL"

        elif "DOMESTIC" in upper_text:
            result["type"] = "DOMESTIC"

    # ---------------------------------------------------------
    # FALLBACK VOYAGE
    # ---------------------------------------------------------

    if not result["voyage"]:

        voyage_pattern = re.compile(
            r"\b[A-Z0-9]{1,10}"
            r"(?:-[A-Z0-9]{1,10})?"
            r"[NS]\b",
            re.IGNORECASE
        )

        matches = voyage_pattern.findall(
            text
        )

        if matches:

            result["voyage"] = (
                " / ".join(
                    dict.fromkeys(matches)
                )
            )

    # ---------------------------------------------------------
    # FALLBACK DATES
    # ---------------------------------------------------------

    date_pattern = re.compile(
        r"\d{1,2}/\d{1,2}/\d{4}"
        r"\s+\d{1,2}:\d{2}"
    )

    dates = list(
        dict.fromkeys(
            date_pattern.findall(text)
        )
    )

    if dates:

        if not result["eta"]:
            result["eta"] = dates[0]

        if len(dates) > 1 and not result["etb"]:
            result["etb"] = dates[1]

        if len(dates) > 2 and not result["etd"]:
            result["etd"] = dates[2]

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------

    if (
        not result["vesselName"]
        and not result["voyage"]
    ):
        return None

    return result


def detect_blocks(soup):

    """
    Main vessel block detector.

    Pelindo uses .ves_along_sched.
    We deliberately search globally rather than depending
    on HTML comments.
    """

    blocks = []

    # ---------------------------------------------------------
    # 1. Primary selector
    # ---------------------------------------------------------

    candidates = soup.select(
```
