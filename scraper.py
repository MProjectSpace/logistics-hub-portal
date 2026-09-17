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

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

BASE_URL = "https://ibstpks.pelindo.co.id"
WEBACCESS_URL = f"{BASE_URL}/webaccess"
OUTPUT_FILE = Path("data.json")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def clean_text(value):
    if value is None:
        return ""
    value = str(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_url(value):
    value = clean_text(value)
    if not value or value.startswith("javascript:"):
        return ""
    return urljoin(BASE_URL, value)


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


def parse_vessel_block(block_soup):
    divs = block_soup.find_all("div", class_="ves_along_sched")
    if not divs:
        return None

    record = make_empty_record()

    # Detail & History Links
    for a in block_soup.find_all("a", attrs={"data-url": True}):
        url = normalize_url(a.get("data-url", ""))
        text = clean_text(a.get_text()).lower()
        if "ves_id=" in url:
            match_ves = re.search(r"ves_id=([^&]+)", url)
            if match_ves:
                record["vesId"] = match_ves.group(1)
        if "audit" in url or "history" in text:
            record["historyUrl"] = url
        elif "detail" in text or "vessel" in url or "ves_schedule_det" in url:
            record["detailUrl"] = url

    # Vessel Name, Code, and Shipping Line from <b> tags
    b_tags = block_soup.find_all("b")
    b_texts = [clean_text(b.get_text()) for b in b_tags if clean_text(b.get_text())]

    if b_texts:
        raw_title = b_texts
        match_code = re.search(r"^(.*?)\s*\\((.*?)\\)$", raw_title)
        if match_code:
            record["vesselName"] = clean_text(match_code.group(1))
            record["vesselCode"] = clean_text(match_code.group(2))
        else:
            record["vesselName"] = clean_text(raw_title)

        if len(b_texts) > 1:
            record["shippingLine"] = b_texts[11]

    # Clean text lines for detailed attributes parsing
    lines = []
    for d in divs:
        if d.find("a", attrs={"data-url": True}):
            continue
        txt = clean_text(d.get_text())
        if txt and not txt.startswith("["):
            lines.append(txt)

    for line in lines:
        if line in ["INTERNATIONAL", "DOMESTIC"]:
            record["type"] = line
        elif "ETA :" in line:
            record["eta"] = clean_text(line.replace("ETA :", ""))
        elif "ETB :" in line:
            record["etb"] = clean_text(line.replace("ETB :", ""))
        elif "ATB :" in line:
            record["atb"] = clean_text(line.replace("ATB :", ""))
        elif "ETD :" in line:
            record["etd"] = clean_text(line.replace("ETD :", ""))
        elif "ATD :" in line:
            record["atd"] = clean_text(line.replace("ATD :", ""))
        elif "Open Stack :" in line:
            record["openStack"] = clean_text(line.replace("Open Stack :", ""))
        elif "Closing Time :" in line:
            record["closingTime"] = clean_text(line.replace("Closing Time :", ""))
        elif "Booking / Open / Actual :" in line:
            parts = [clean_text(p) for p in line.replace("Booking / Open / Actual :", "").split("/") if clean_text(p)]
            if len(parts) == 3:
                record["booking"] = parts
                record["open"] = parts[11]
                record["actual"] = parts[2]
        elif "Export Box / Teus :" in line:
            parts = [clean_text(p) for p in line.replace("Export Box / Teus :", "").split("/") if clean_text(p)]
            if len(parts) == 2:
                record["export"] = parts
                record["exportTeus"] = parts[11]
        elif "Import Box / Teus :" in line:
            parts = [clean_text(p) for p in line.replace("Import Box / Teus :", "").split("/") if clean_text(p)]
            if len(parts) == 2:
                record["import"] = parts
                record["importTeus"] = parts[11]
        elif "/" in line and ":" not in line and not record["voyage"]:
            record["voyage"] = clean_text(line)
        elif not record["shippingLine"] and ":" not in line and line not in ["INTERNATIONAL", "DOMESTIC"]:
            if b_texts and line == b_texts:
                continue
            if record["vesselName"] and line.startswith(record["vesselName"]):
                continue
            if len(line) > 2 and "/" not in line:
                record["shippingLine"] = line

    if not record["vesselName"]:
        return None

    return record


def parse_section(container_elem):
    if container_elem is None:
        return []

    html_str = str(container_elem)
    parts = re.split(
        r'<hr[^>]*class=["\'][^"\']*ves_along_sched_hr[^"\']*["\'][^>]*>',
        html_str,
        flags=re.IGNORECASE,
    )

    records = []
    for part in parts:
        if not part.strip():
            continue
        sub_soup = BeautifulSoup(part, "html.parser")
        rec = parse_vessel_block(sub_soup)
        if rec and rec["vesselName"]:
            records.append(rec)

    return records


def scrape_pelindo_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    tz_wib = timezone(timedelta(hours=7))
    now_str = datetime.now(tz_wib).strftime("%Y-%m-%d %H:%M:%S")

    vessel_alongside = parse_section(soup.select_one("._mCS_1"))
    confirmed_vessel = parse_section(soup.select_one("._mCS_2"))
    open_stack = parse_section(soup.select_one("._mCS_3"))
    vessel_schedule = parse_section(soup.select_one("#div_ves_schedule"))
    vessel_history = parse_section(soup.select_one("#div_ves_history"))

    return {
        "updatedAt": now_str,
        "source": BASE_URL,
        "vesselAlongside": vessel_alongside,
        "confirmedVessel": confirmed_vessel,
        "openStack": open_stack,
        "vesselSchedule": vessel_schedule,
        "vesselHistory": vessel_history,
        "counts": {
            "vesselAlongside": len(vessel_alongside),
            "confirmedVessel": len(confirmed_vessel),
            "openStack": len(open_stack),
            "vesselSchedule": len(vessel_schedule),
            "vesselHistory": len(vessel_history)
        }
    }


def fetch_url(url):
    if not requests:
        raise ImportError("Package 'requests' belum terinstall.")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    logging.info(f"Fetch HTML dari: {url}")
    resp = requests.get(url, headers=headers, timeout=60, verify=False)
    resp.raise_for_status()
    return resp.text


def main():
    parser = argparse.ArgumentParser(description="Pelindo TPKS Data Scraper")
    parser.add_argument("-i", "--input", default=f"{WEBACCESS_URL}/", help="URL target atau path HTML lokal")
    parser.add_argument("-o", "--output", default="data.json", help="Path file output JSON")
    args = parser.parse_args()

    if args.input.startswith("http://") or args.input.startswith("https://"):
        try:
            html_content = fetch_url(args.input)
        except Exception as e:
            logging.error(f"Gagal mengambil URL {args.input}: {e}")
            sys.exit(1)
    else:
        if not os.path.exists(args.input):
            logging.error(f"File lokal tidak ditemukan: {args.input}")
            sys.exit(1)
        logging.info(f"Membaca file HTML lokal: {args.input}")
        with open(args.input, "r", encoding="utf-8") as f:
            html_content = f.read()

    data = scrape_pelindo_html(html_content)

    logging.info(f"Counts: {data['counts']}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logging.info(f"Data berhasil disimpan di: {args.output}")


if __name__ == "__main__":
    main()
