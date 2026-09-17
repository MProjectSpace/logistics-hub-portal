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
HISTORY_WAIT = 5000


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
# EXTRACT VESSEL ID
# ============================================================

def extract_ves_id(url):
    if not url:
        return ""

    match = re.search(
        r"[?&]ves_id=([^&]+)",
        url,
        re.IGNORECASE,
    )

    if match:
        return clean_text(match.group(1))

    return ""


# ============================================================
# PARSE ONE VESSEL BLOCK
# ============================================================

async def parse_vessel_element(element):

    record = make_empty_record()

    # --------------------------------------------------------
    # Get all visible text blocks
    # --------------------------------------------------------

    divs = element.locator("div.ves_along_sched")

    count = await divs.count()

    if count == 0:
        return None

    lines = []

    for i in range(count):

        div = divs.nth(i)

        try:
            text = await div.inner_text()
        except Exception:
            continue

        text = clean_text(text)

        if text:
            lines.append(text)

    if not lines:
        return None

    # --------------------------------------------------------
    # Vessel name
    # --------------------------------------------------------

    vessel_name = ""

    first_b = element.locator("div.ves_along_sched b").first

    try:
        if await first_b.count():

            vessel_title = clean_text(
                await first_b.inner_text()
            )

            match = re.match(
                r"^(.*?)\s*\(([^()]+)\)$",
                vessel_title,
            )

            if match:

                record["vesselName"] = clean_text(
                    match.group(1)
                )

                record["vesselCode"] = clean_text(
                    match.group(2)
                )

            else:

                record["vesselName"] = vessel_title

    except Exception:
        pass

    if not record["vesselName"]:
        return None

    # --------------------------------------------------------
    # Links
    # --------------------------------------------------------

    links = element.locator("a[data-url]")

    link_count = await links.count()

    for i in range(link_count):

        a = links.nth(i)

        try:
            data_url = await a.get_attribute("data-url")
            title = await a.get_attribute("title")
            link_text = clean_text(
                await a.inner_text()
            )
        except Exception:
            continue

        data_url = data_url or ""

        ves_id = extract_ves_id(data_url)

        if ves_id and not record["vesId"]:
            record["vesId"] = ves_id

        if "vessel_audit" in data_url:
            record["historyUrl"] = data_url

        elif "ves_schedule_det" in data_url:
            record["detailUrl"] = data_url

        elif title and not record["vesselName"]:
            record["vesselName"] = clean_text(title)

    # --------------------------------------------------------
    # Parse lines
    # --------------------------------------------------------

    for index, line in enumerate(lines):

        # --------------------------------------------
        # TYPE
        # --------------------------------------------

        if line in ("INTERNATIONAL", "DOMESTIC"):

            record["type"] = line

            continue

        # --------------------------------------------
        # ETA
        # --------------------------------------------

        if line.startswith("ETA :"):

            record["eta"] = clean_text(
                line[len("ETA :"):]
            )

            continue

        # --------------------------------------------
        # ETB
        # --------------------------------------------

        if line.startswith("ETB :"):

            record["etb"] = clean_text(
                line[len("ETB :"):]
            )

            continue

        # --------------------------------------------
        # ATB
        # --------------------------------------------

        if line.startswith("ATB :"):

            record["atb"] = clean_text(
                line[len("ATB :"):]
            )

            continue

        # --------------------------------------------
        # ETD
        # --------------------------------------------

        if line.startswith("ETD :"):

            record["etd"] = clean_text(
                line[len("ETD :"):]
            )

            continue

        # --------------------------------------------
        # ATD
        # --------------------------------------------

        if line.startswith("ATD :"):

            record["atd"] = clean_text(
                line[len("ATD :"):]
            )

            continue

        # --------------------------------------------
        # OPEN STACK
        # --------------------------------------------

        if line.startswith("Open Stack :"):

            record["openStack"] = clean_text(
                line[len("Open Stack :"):]
            )

            continue

        # --------------------------------------------
        # CLOSING TIME
        # --------------------------------------------

        if line.startswith("Closing Time :"):

            record["closingTime"] = clean_text(
                line[len("Closing Time :"):]
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
                    1,
                )
            )

            parts = [
                clean_text(x)
                for x in value.split("/")
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
                    1,
                )
            )

            parts = [
                clean_text(x)
                for x in value.split("/")
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
                    1,
                )
            )

            parts = [
                clean_text(x)
                for x in value.split("/")
            ]

            if len(parts) >= 2:

                record["import"] = parts[0]
                record["importTeus"] = parts[1]

            continue

        # --------------------------------------------
        # VOYAGE
        # --------------------------------------------

        if not record["voyage"]:

            if (
                "/" in line
                and ":" not in line
                and line != record["vesselName"]
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
                and "/" not in line
                and line not in (
                    "INTERNATIONAL",
                    "DOMESTIC",
                )
                and line != record["vesselName"]
            ):

                record["shippingLine"] = line

    return record


# ============================================================
# PARSE SECTION CELL
# ============================================================

async def parse_section_cell(cell):

    records = []

    # Each vessel is separated by HR.
    blocks = cell.locator(
        "div.ves_along_sched"
    )

    block_count = await blocks.count()

    if block_count == 0:
        return records

    # Find vessel containers by HR structure.
    #
    # Instead of reconstructing HTML, use the nearest
    # logical parent around each vessel title.
    #

    # Get direct HTML of the cell.
    html = await cell.inner_html()

    # Split using the actual Pelindo separator.
    parts = re.split(
        r'<hr[^>]*class=["\'][^"\']*ves_along_sched_hr[^"\']*["\'][^>]*>',
        html,
        flags=re.IGNORECASE,
    )

    for part in parts:

        if not part.strip():
            continue

        # Parse the individual block as HTML.
        temp = await cell.evaluate(
            """
            (cell, html) => {
                const wrapper = document.createElement("div");
                wrapper.innerHTML = html;
                return wrapper.innerHTML;
            }
            """,
            part,
        )

        # We cannot pass HTML back into locator directly.
        # Instead create a temporary DOM element.
        block_locator = await cell.evaluate(
            """
            (cell, html) => {
                const wrapper = document.createElement("div");
                wrapper.innerHTML = html;

                const nodes = wrapper.querySelectorAll(
                    "div.ves_along_sched"
                );

                return nodes.length > 0;
            }
            """,
            part,
        )

        if not block_locator:
            continue

        # Use locator based on original HTML via JS extraction.
        data = await cell.evaluate(
            """
            (cell, html) => {

                const wrapper =
                    document.createElement("div");

                wrapper.innerHTML = html;

                const divs =
                    [...wrapper.querySelectorAll(
                        "div.ves_along_sched"
                    )];

                if (!divs.length)
                    return null;

                const lines = divs
                    .map(d => d.innerText.trim())
                    .filter(Boolean);

                const b = wrapper.querySelector(
                    "div.ves_along_sched b"
                );

                if (!b)
                    return null;

                const title = b.innerText.trim();

                const links =
                    [...wrapper.querySelectorAll(
                        "a[data-url]"
                    )].map(a => ({
                        url: a.getAttribute("data-url") || "",
                        text: a.innerText.trim(),
                        title: a.getAttribute("title") || ""
                    }));

                return {
                    lines,
                    title,
                    links
                };
            }
            """,
            part,
        )

        if not data:
            continue

        record = parse_vessel_data(data)

        if record:
            records.append(record)

    return records


# ============================================================
# PARSE EXTRACTED JS DATA
# ============================================================

def parse_vessel_data(data):

    record = make_empty_record()

    lines = [
        clean_text(x)
        for x in data.get("lines", [])
        if clean_text(x)
    ]

    if not lines:
        return None

    # --------------------------------------------------------
    # NAME / CODE
    # --------------------------------------------------------

    title = clean_text(
        data.get("title", "")
    )

    if not title:
        return None

    match = re.match(
        r"^(.*?)\s*\(([^()]+)\)$",
        title,
    )

    if match:

        record["vesselName"] = clean_text(
            match.group(1)
        )

        record["vesselCode"] = clean_text(
            match.group(2)
        )

    else:

        record["vesselName"] = title

    # --------------------------------------------------------
    # LINKS
    # --------------------------------------------------------

    for link in data.get("links", []):

        url = link.get("url", "")
        text = clean_text(
            link.get("text", "")
        ).lower()

        ves_id = extract_ves_id(url)

        if ves_id and not record["vesId"]:
            record["vesId"] = ves_id

        if "vessel_audit" in url:

            record["historyUrl"] = url

        elif "ves_schedule_det" in url:

            record["detailUrl"] = url

        elif "detail" in text:

            record["detailUrl"] = url

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    for line in lines:

        if line in (
            "INTERNATIONAL",
            "DOMESTIC",
        ):

            record["type"] = line
            continue

        if line.startswith("ETA :"):

            record["eta"] = clean_text(
                line.replace("ETA :", "", 1)
            )
            continue

        if line.startswith("ETB :"):

            record["etb"] = clean_text(
                line.replace("ETB :", "", 1)
            )
            continue

        if line.startswith("ATB :"):

            record["atb"] = clean_text(
                line.replace("ATB :", "", 1)
            )
            continue

        if line.startswith("ETD :"):

            record["etd"] = clean_text(
                line.replace("ETD :", "", 1)
            )
            continue

        if line.startswith("ATD :"):

            record["atd"] = clean_text(
                line.replace("ATD :", "", 1)
            )
            continue

        if line.startswith("Open Stack :"):

            record["openStack"] = clean_text(
                line.replace(
                    "Open Stack :",
                    "",
                    1,
                )
            )
            continue

        if line.startswith("Closing Time :"):

            record["closingTime"] = clean_text(
                line.replace(
                    "Closing Time :",
                    "",
                    1,
                )
            )
            continue

        if line.startswith(
            "Booking / Open / Actual :"
        ):

            value = clean_text(
                line.replace(
                    "Booking / Open / Actual :",
                    "",
                    1,
                )
            )

            parts = [
                clean_text(x)
                for x in value.split("/")
            ]

            if len(parts) >= 3:

                record["booking"] = parts[0]
                record["open"] = parts[1]
                record["actual"] = parts[2]

            continue

        if line.startswith(
            "Export Box / Teus :"
        ):

            value = clean_text(
                line.replace(
                    "Export Box / Teus :",
                    "",
                    1,
                )
            )

            parts = [
                clean_text(x)
                for x in value.split("/")
            ]

            if len(parts) >= 2:

                record["export"] = parts[0]
                record["exportTeus"] = parts[1]

            continue

        if line.startswith(
            "Import Box / Teus :"
        ):

            value = clean_text(
                line.replace(
                    "Import Box / Teus :",
                    "",
                    1,
                )
            )

            parts = [
                clean_text(x)
                for x in value.split("/")
            ]

            if len(parts) >= 2:

                record["import"] = parts[0]
                record["importTeus"] = parts[1]

            continue

        # Voyage
        if not record["voyage"]:

            if (
                "/" in line
                and ":" not in line
                and line != record["vesselName"]
            ):

                record["voyage"] = line
                continue

        # Shipping line
        if not record["shippingLine"]:

            if (
                ":" not in line
                and "/" not in line
                and line not in (
                    "INTERNATIONAL",
                    "DOMESTIC",
                )
                and line != record["vesselName"]
            ):

                record["shippingLine"] = line

    if not record["vesselName"]:
        return None

    return record


# ============================================================
# PARSE MAIN FOUR SECTIONS
# ============================================================

async def get_main_sections(page):

    main_table = page.locator(
        "table"
    ).first

    cells = main_table.locator(
        "td.vessel"
    )

    count = await cells.count()

    logging.info(
        "Main vessel cells ditemukan: %d",
        count,
    )

    if count < 4:

        raise RuntimeError(
            f"Struktur Pelindo berubah: "
            f"ditemukan {count} td.vessel, "
            f"minimal 4 diperlukan."
        )

    sections = {}

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # The actual main table has 4 td.vessel cells:
    #
    # 0 = Alongside
    # 1 = Confirmed
    # 2 = Open Stack
    # 3 = Schedule
    #
    # This was verified from the supplied Pelindo DOM.
    # --------------------------------------------------------

    sections["alongside"] = await parse_section_cell(
        cells.nth(0)
    )

    sections["confirmed"] = await parse_section_cell(
        cells.nth(1)
    )

    sections["openStack"] = await parse_section_cell(
        cells.nth(2)
    )

    sections["schedule"] = await parse_section_cell(
        cells.nth(3)
    )

    return sections


# ============================================================
# HISTORY
# ============================================================

async def get_history(page):

    history_links = page.locator(
        'a[data-url*="vessel_audit"]'
    )

    count = await history_links.count()

    logging.info(
        "History links ditemukan: %d",
        count,
    )

    if count == 0:
        logging.warning(
            "Tidak ditemukan link History."
        )

        return []

    # --------------------------------------------------------
    # Click the first History link.
    #
    # Pelindo loads History through AJAX.
    # --------------------------------------------------------

    first_link = history_links.first

    try:

        await first_link.click(
            force=True,
            timeout=30000,
        )

    except Exception as e:

        logging.warning(
            "Gagal klik History: %s",
            e,
        )

        return []

    # --------------------------------------------------------
    # Wait for AJAX modal
    # --------------------------------------------------------

    try:

        await page.locator(
            "#TB_ajaxContent"
        ).wait_for(
            state="visible",
            timeout=30000,
        )

    except PlaywrightTimeoutError:

        logging.warning(
            "Modal History tidak muncul."
        )

    await page.wait_for_timeout(
        HISTORY_WAIT
    )

    # --------------------------------------------------------
    # History section appears dynamically
    # --------------------------------------------------------

    history_container = page.locator(
        "#div_ves_history"
    )

    if await history_container.count() == 0:

        logging.warning(
            "#div_ves_history tidak ditemukan."
        )

        # Close modal if possible
        try:
            close = page.locator(
                "#TB_closeWindowButton"
            )

            if await close.count():
                await close.click(
                    force=True
                )

        except Exception:
            pass

        return []

    try:

        records = await parse_section_cell(
            history_container
        )

    except Exception as e:

        logging.error(
            "Gagal parse Vessel History: %s",
            e,
        )

        records = []

    # --------------------------------------------------------
    # Close modal
    # --------------------------------------------------------

    try:

        close = page.locator(
            "#TB_closeWindowButton"
        )

        if await close.count():

            await close.click(
                force=True,
                timeout=10000,
            )

            await page.wait_for_timeout(
                1000
            )

    except Exception:
        pass

    return records


# ============================================================
# DEDUPLICATE
# ============================================================

def deduplicate(records):

    result = []
    seen = set()

    for record in records:

        key = (
            record.get("vesselName", ""),
            record.get("voyage", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(record)

    return result


# ============================================================
# SCRAPER
# ============================================================

async def scrape():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            viewport={
                "width": 1920,
                "height": 1080,
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        page = await context.new_page()

        page.set_default_timeout(
            30000
        )

        try:

            logging.info(
                "Membuka Pelindo TPKS..."
            )

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT,
            )

            logging.info(
                "Halaman berhasil dibuka."
            )

            await page.wait_for_timeout(
                WAIT_AFTER_LOAD
            )

            # ------------------------------------------------
            # MAIN DATA
            # ------------------------------------------------

            sections = await get_main_sections(
                page
            )

            # ------------------------------------------------
            # HISTORY
            #
            # IMPORTANT:
            # Get this AFTER main Schedule has been parsed.
            # Therefore History cannot contaminate Schedule.
            # ------------------------------------------------

            history = await get_history(
                page
            )

            # ------------------------------------------------
            # DATA
            # ------------------------------------------------

            alongside = deduplicate(
                sections["alongside"]
            )

            confirmed = deduplicate(
                sections["confirmed"]
            )

            open_stack = deduplicate(
                sections["openStack"]
            )

            schedule = deduplicate(
                sections["schedule"]
            )

            history = deduplicate(
                history
            )

            # ------------------------------------------------
            # ALL VESSELS
            # ------------------------------------------------

            all_vessels = deduplicate(
                alongside
                + confirmed
                + open_stack
                + schedule
                + history
            )

            # ------------------------------------------------
            # WIB
            # ------------------------------------------------

            updated_at = datetime.now(
                ZoneInfo("Asia/Jakarta")
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            data = {

                "lastUpdated": updated_at,

                "updatedAt": updated_at,

                "source": URL,

                "allVessels": all_vessels,

                "vesselAlongside": alongside,

                "confirmedVessel": confirmed,

                "openStack": open_stack,

                "vesselSchedule": schedule,

                "vesselHistory": history,

                "counts": {

                    "allVessels": len(
                        all_vessels
                    ),

                    "vesselAlongside": len(
                        alongside
                    ),

                    "confirmedVessel": len(
                        confirmed
                    ),

                    "openStack": len(
                        open_stack
                    ),

                    "vesselSchedule": len(
                        schedule
                    ),

                    "vesselHistory": len(
                        history
                    ),
                },
            }

            # ------------------------------------------------
            # SAVE
            # ------------------------------------------------

            with open(
                OUTPUT_FILE,
                "w",
                encoding="utf-8",
            ) as f:

                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            # ------------------------------------------------
            # LOG
            # ------------------------------------------------

            print()
            print("======================================")
            print("HASIL SCRAPING")
            print("======================================")

            print(
                f"Alongside : {len(alongside)}"
            )

            print(
                f"Confirmed : {len(confirmed)}"
            )

            print(
                f"Open Stack: {len(open_stack)}"
            )

            print(
                f"Schedule  : {len(schedule)}"
            )

            print(
                f"History   : {len(history)}"
            )

            print(
                f"All       : {len(all_vessels)}"
            )

            print(
                f"Updated   : {updated_at}"
            )

            print(
                f"Output    : {OUTPUT_FILE}"
            )

            print("======================================")

            print()
            print("SCHEDULE DATA:")

            for item in schedule:

                print(
                    f"- {item['vesselName']} | "
                    f"{item['voyage']} | "
                    f"ETB: {item['etb']}"
                )

            print()
            print("HISTORY DATA:")

            for item in history:

                print(
                    f"- {item['vesselName']} | "
                    f"{item['voyage']}"
                )

            print()
            print("=== SCRAPER SELESAI ===")

            return data

        except Exception as e:

            logging.exception(
                "SCRAPER GAGAL"
            )

            raise

        finally:

            await browser.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            scrape()
        )

    except KeyboardInterrupt:

        print(
            "\nScraper dihentikan."
        )

    except Exception as e:

        print(
            f"\nERROR: {e}"
        )

        raise
