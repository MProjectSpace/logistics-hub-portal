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


def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_vessel_block(block_soup: BeautifulSoup) -> Dict[str, Any]:
    divs = block_soup.find_all("div", class_="ves_along_sched")
    if not divs:
        return {}

    data: Dict[str, Any] = {}

    b_tags = block_soup.find_all("b")
    b_texts = [clean_text(b.get_text()) for b in b_tags if clean_text(b.get_text())]

    raw_title = b_texts if b_texts else clean_text(divs.get_text())
    raw_title_clean = re.sub(r"\\[.*?\\]", "", raw_title).strip()
    match_code = re.search(r"^(.*?)\s*\\((.*?)\\)$", raw_title_clean)
    if match_code:
        data["vesselName"] = clean_text(match_code.group(1))
    else:
        data["vesselName"] = clean_text(raw_title_clean)

    lines = []
    for d in divs:
        if d.find("a", attrs={"data-url": True}):
            continue
        txt = clean_text(d.get_text())
        if txt and not txt.startswith("["):
            lines.append(txt)

    for line in lines:
        if "ETA :" in line:
            data["eta"] = clean_text(line.replace("ETA :", ""))
        elif "ETB :" in line:
            data["etb"] = clean_text(line.replace("ETB :", ""))
        elif "ATB :" in line:
            data["atb"] = clean_text(line.replace("ATB :", ""))
        elif "ETD :" in line:
            data["etd"] = clean_text(line.replace("ETD :", ""))
        elif "ATD :" in line:
            data["atd"] = clean_text(line.replace("ATD :", ""))
        elif "Open Stack :" in line:
            data["openStack"] = clean_text(line.replace("Open Stack :", ""))
        elif "Closing Time :" in line:
            data["closingTime"] = clean_text(line.replace("Closing Time :", ""))
        elif "Booking / Open / Actual :" in line:
            c_str = line.replace("Booking / Open / Actual :", "").strip()
            c_parts = [p.strip() for p in c_str.split("/") if p.strip()]
            if len(c_parts) == 3:
                data["booking"] = c_parts
                data["open"] = c_parts[1]
                data["actual"] = c_parts[2]
            else:
                data["booking"] = "-"
                data["open"] = "-"
                data["actual"] = "-"
        elif "/" in line and ":" not in line and "voyage" not in data:
            data["voyage"] = clean_text(line)

    if "voyage" not in data:
        data["voyage"] = "-"

    return data


def parse_section(container: Optional[BeautifulSoup]) -> List[Dict[str, Any]]:
    if not container:
        return []

    html_str = str(container)
    parts = re.split(
        r'<hr[^>]*class=["\'][^"\']*ves_along_sched_hr[^"\']*["\'][^>]*>',
        html_str,
        flags=re.IGNORECASE,
    )

    items = []
    for part in parts:
        if not part.strip():
            continue
        sub_soup = BeautifulSoup(part, "html.parser")
        parsed = parse_vessel_block(sub_soup)
        if parsed and parsed.get("vesselName"):
            items.append(parsed)

    return items


def scrape_pelindo_html(html_content: str) -> Dict[str, Any]:
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
        "portalUrl": "https://mprojectspace.github.io/logistics-hub-portal/"
    }


def fetch_url(url: str) -> str:
    if not requests:
        raise ImportError("Package 'requests' belum terinstall.")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    logging.info(f"Mengambil data dari URL: {url}")
    resp = requests.get(url, headers=headers, timeout=30, verify=False)
    resp.raise_for_status()
    return resp.text


def main():
    parser = argparse.ArgumentParser(description="Pelindo TPKS Data Scraper")
    parser.add_argument("-i", "--input", default="https://ibstpks.pelindo.co.id/webaccess/", help="Path HTML lokal atau URL")
    parser.add_argument("-o", "--output", default="data.json", help="Path output JSON")
    args = parser.parse_args()

    if args.input.startswith("http://") or args.input.startswith("https://"):
        try:
            html_content = fetch_url(args.input)
        except Exception as e:
            logging.error(f"Gagal mengambil dari URL ({args.input}): {e}")
            sys.exit(1)
    else:
        if not os.path.exists(args.input):
            logging.error(f"File lokal tidak ditemukan: {args.input}")
            sys.exit(1)
        logging.info(f"Membaca file lokal: {args.input}")
        with open(args.input, "r", encoding="utf-8") as f:
            html_content = f.read()

    data = scrape_pelindo_html(html_content)

    summary = {
        "vesselAlongside": len(data["vesselAlongside"]),
        "confirmedVessel": len(data["confirmedVessel"]),
        "openStack": len(data["openStack"]),
        "vesselSchedule": len(data["vesselSchedule"]),
        "lastUpdated": data["lastUpdated"]
    }
    logging.info(f"Hasil ekstraksi: {summary}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logging.info(f"Data berhasil disimpan di: {args.output}")


if __name__ == "__main__":
    main()
