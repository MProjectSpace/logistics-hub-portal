#!/usr/bin/env python3
"""
Pelindo TPKS Webaccess Scraper for Logistics Hub Portal.

Repository:
https://github.com/mprojectspace/logistics-hub-portal

Live Site:
https://mprojectspace.github.io/logistics-hub-portal/
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

try:
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

SOURCE_URL = "https://ibstpks.pelindo.co.id/webaccess/"
PORTAL_URL = "https://mprojectspace.github.io/logistics-hub-portal/"


def clean_text(text: str) -> str:
    """Normalize whitespace and trim text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def split_vessel_name_and_code(title: str) -> tuple[str, str]:
    """
    Extract vessel name from a title such as:
    'VESSEL NAME (CODE)'.

    Returns:
        (vessel_name, code)
    """
    title = clean_text(title)
    title = re.sub(r"\[.*?\]", "", title).strip()

    match = re.search(r"^(.*?)\s*\((.*?)\)\s*$", title)
    if match:
        return clean_text(match.group(1)), clean_text(match.group(2))

    return title, ""


def parse_vessel_block(block_soup: BeautifulSoup) -> Dict[str, Any]:
    """Parse one vessel block from the Pelindo Webaccess HTML."""
    divs = block_soup.find_all("div", class_="ves_along_sched")
    if not divs:
        return {}

    data: Dict[str, Any] = {}

    # The vessel title is normally contained in <b>.
    b_texts = [
        clean_text(tag.get_text(" ", strip=True))
        for tag in block_soup.find_all("b")
    ]
    b_texts = [text for text in b_texts if text]

    if b_texts:
        raw_title = b_texts[0]
    else:
        # Avoid calling get_text() on a ResultSet/list.
        raw_title = clean_text(
            " ".join(div.get_text(" ", strip=True) for div in divs)
        )

    vessel_name, vessel_code = split_vessel_name_and_code(raw_title)

    if not vessel_name:
        return {}

    data["vesselName"] = vessel_name
    if vessel_code:
        data["vesselCode"] = vessel_code

    lines: List[str] = []

    for div in divs:
        # Navigation/detail links can contain unrelated text.
        if div.find("a", attrs={"data-url": True}):
            continue

        text = clean_text(div.get_text(" ", strip=True))
        if text and not text.startswith("["):
            lines.append(text)

    for line in lines:
        if "ETA :" in line:
            data["eta"] = clean_text(line.split("ETA :", 1)[1])

        elif "ETB :" in line:
            data["etb"] = clean_text(line.split("ETB :", 1)[1])

        elif "ATB :" in line:
            data["atb"] = clean_text(line.split("ATB :", 1)[1])

        elif "ETD :" in line:
            data["etd"] = clean_text(line.split("ETD :", 1)[1])

        elif "ATD :" in line:
            data["atd"] = clean_text(line.split("ATD :", 1)[1])

        elif "Open Stack :" in line:
            data["openStack"] = clean_text(
                line.split("Open Stack :", 1)[1]
            )

        elif "Closing Time :" in line:
            data["closingTime"] = clean_text(
                line.split("Closing Time :", 1)[1]
            )

        elif "Booking / Open / Actual :" in line:
            value = clean_text(
                line.split("Booking / Open / Actual :", 1)[1]
            )
            parts = [part.strip() for part in value.split("/")]

            # Preserve the three expected fields even if one is blank.
            parts = [part for part in parts if part]
            if len(parts) == 3:
                data["booking"] = parts[0]
                data["open"] = parts[1]
                data["actual"] = parts[2]
                data["bookingOpenActual"] = parts
            else:
                data["booking"] = "-"
                data["open"] = "-"
                data["actual"] = "-"
                data["bookingOpenActual"] = ["-", "-", "-"]

        elif "/" in line and ":" not in line and "voyage" not in data:
            data["voyage"] = clean_text(line)

    # Keep a stable schema for the dashboard.
    for key in (
        "eta",
        "etb",
        "atb",
        "etd",
        "atd",
        "openStack",
        "closingTime",
        "voyage",
        "booking",
        "open",
        "actual",
    ):
        data.setdefault(key, "-")

    data.setdefault("bookingOpenActual", ["-", "-", "-"])

    return data


def parse_section(container: Optional[BeautifulSoup]) -> List[Dict[str, Any]]:
    """Parse all vessel blocks inside one dashboard section."""
    if not container:
        return []

    html_str = str(container)

    # Pelindo separates vessel blocks using ves_along_sched_hr.
    parts = re.split(
        r'<hr[^>]*class=["\'][^"\']*ves_along_sched_hr[^"\']*["\'][^>]*>',
        html_str,
        flags=re.IGNORECASE,
    )

    items: List[Dict[str, Any]] = []

    for part in parts:
        if not part.strip():
            continue

        sub_soup = BeautifulSoup(part, "html.parser")
        parsed = parse_vessel_block(sub_soup)

        if parsed.get("vesselName"):
            items.append(parsed)

    return items


def scrape_pelindo_html(html_content: str) -> Dict[str, Any]:
    """Convert Pelindo HTML into the JSON structure used by the portal."""
    soup = BeautifulSoup(html_content, "html.parser")

    tz_wib = timezone(timedelta(hours=7))
    now_wib = datetime.now(tz_wib).strftime("%d/%m/%Y %H:%M WIB")

    return {
        "vesselAlongside": parse_section(soup.select_one("._mCS_1")),
        "confirmedVessel": parse_section(soup.select_one("._mCS_2")),
        "openStack": parse_section(soup.select_one("._mCS_3")),
        "vesselSchedule": parse_section(soup.select_one("#div_ves_schedule")),
        "lastUpdated": now_wib,
        "source": "Pelindo TPKS Webaccess",
        "portalUrl": PORTAL_URL,
    }


def fetch_url(url: str) -> str:
    """Fetch HTML from Pelindo Webaccess."""
    if requests is None:
        raise ImportError("Package 'requests' belum terinstall.")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    logging.info("Mengambil data dari URL: %s", url)

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
        verify=False,
    )
    response.raise_for_status()

    logging.info(
        "HTTP %s | %s bytes",
        response.status_code,
        len(response.content),
    )

    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pelindo TPKS Data Scraper"
    )
    parser.add_argument(
        "-i",
        "--input",
        default=SOURCE_URL,
        help="Path HTML lokal atau URL Pelindo Webaccess",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="data.json",
        help="Path output JSON",
    )

    args = parser.parse_args()

    try:
        if args.input.startswith(("http://", "https://")):
            html_content = fetch_url(args.input)
        else:
            if not os.path.exists(args.input):
                raise FileNotFoundError(
                    f"File lokal tidak ditemukan: {args.input}"
                )

            logging.info("Membaca file lokal: %s", args.input)
            with open(args.input, "r", encoding="utf-8") as file:
                html_content = file.read()

        data = scrape_pelindo_html(html_content)

        summary = {
            "vesselAlongside": len(data["vesselAlongside"]),
            "confirmedVessel": len(data["confirmedVessel"]),
            "openStack": len(data["openStack"]),
            "vesselSchedule": len(data["vesselSchedule"]),
            "lastUpdated": data["lastUpdated"],
        }

        logging.info("Hasil ekstraksi: %s", summary)

        with open(args.output, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        logging.info("Data berhasil disimpan di: %s", args.output)

    except Exception as exc:
        logging.error("Scraper gagal: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
