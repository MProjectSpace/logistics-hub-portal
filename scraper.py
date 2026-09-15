import asyncio
import json
import re
from datetime import datetime

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError
)


URL = "https://ibstpks.pelindo.co.id/webaccess/"

MAX_RETRIES = 3
NAVIGATION_TIMEOUT = 120000
WAIT_AFTER_LOAD = 10000


VESSEL_PATTERN = re.compile(
    r"^(.+?)\s*\(([^()]+)\)$"
)

DATE_PATTERN = re.compile(
    r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}"
)


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")

    lines = []

    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def clean_lines(text):
    text = normalize_text(text)

    return [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]


def is_footer_name(name):
    name = name.strip().lower()

    footer_names = {
        "close",
        "close or esc key",
        "detail",
        "[ detail ]",
        "history",
        "[ history ]"
    }

    return name in footer_names


# ============================================================
# VESSEL PARSER
# ============================================================

def extract_voyage(lines):
    for line in lines:

        if not line:
            continue

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if line.startswith("ETB :"):
            continue

        if line.startswith("ETA :"):
            continue

        if line.startswith("ATB :"):
            continue

        if line.startswith("ATD :"):
            continue

        if line.startswith("ETD :"):
            continue

        if line in ("Detail", "[ Detail ]"):
            continue

        if line in ("[ History ]", "History"):
            continue

        return line

    return ""


def is_valid_vessel_block(lines):

    if not lines:
        return False

    match = VESSEL_PATTERN.match(lines[0])

    if not match:
        return False

    vessel_name = match.group(1).strip()

    if is_footer_name(vessel_name):
        return False

    return True


def parse_vessel_block(lines):

    if not is_valid_vessel_block(lines):
        return None

    match = VESSEL_PATTERN.match(lines[0])

    vessel_name = match.group(1).strip()
    vessel_code = match.group(2).strip()

    voyage = extract_voyage(lines[1:])

    result = {
        "vesselName": vessel_name,
        "vesselCode": vessel_code,
        "voyage": voyage,
        "eta": "",
        "etb": "",
        "atb": "",
        "etd": "",
        "openStack": "",
        "closingTime": "",
        "booking": "",
        "open": "",
        "actual": ""
    }

    for line in lines[1:]:

        if line.startswith("ETA :"):
            result["eta"] = line.replace(
                "ETA :", "", 1
            ).strip()

        elif line.startswith("ETB :"):
            result["etb"] = line.replace(
                "ETB :", "", 1
            ).strip()

        elif line.startswith("ATB :"):
            result["atb"] = line.replace(
                "ATB :", "", 1
            ).strip()

        elif line.startswith("ETD :"):
            result["etd"] = line.replace(
                "ETD :", "", 1
            ).strip()

        elif line.startswith("Open Stack :"):
            result["openStack"] = line.replace(
                "Open Stack :", "", 1
            ).strip()

        elif line.startswith("Closing Time :"):
            result["closingTime"] = line.replace(
                "Closing Time :", "", 1
            ).strip()

        elif line.startswith("Booking :"):
            result["booking"] = line.replace(
                "Booking :", "", 1
            ).strip()

        elif line.startswith("Open :"):
            result["open"] = line.replace(
                "Open :", "", 1
            ).strip()

        elif line.startswith("Actual :"):
            result["actual"] = line.replace(
                "Actual :", "", 1
            ).strip()

    return result


def parse_vessel_cell(text):

    lines = clean_lines(text)

    vessel_positions = []

    for i, line in enumerate(lines):

        match = VESSEL_PATTERN.match(line)

        if not match:
            continue

        vessel_name = match.group(1).strip()

        if is_footer_name(vessel_name):
            continue

        vessel_positions.append(i)

    vessels = []

    for position_index, start in enumerate(vessel_positions):

        if position_index + 1 < len(vessel_positions):
            end = vessel_positions[position_index + 1]
        else:
            end = len(lines)

        block = lines[start:end]

        parsed = parse_vessel_block(block)

        if parsed:
            vessels.append(parsed)

    return vessels


# ============================================================
# GET MAIN VESSEL SECTIONS
# ============================================================

async def get_vessel_sections(page):

    cells = await page.locator(
        "td.vessel"
    ).evaluate_all("""
        els => els.map((el, index) => {

            const heading = el.querySelector(
                "span.images-v"
            );

            return {
                index: index,

                text: el.innerText || "",

                headingClass: heading
                    ? heading.className
                    : "",

                headingText: heading
                    ? heading.innerText
                    : ""
            };
        })
    """)

    sections = {}

    print()
    print("=" * 70)
    print("DOM VESSEL SECTIONS")
    print("=" * 70)

    for cell in cells:

        index = cell["index"]

        raw_text = cell["text"]
        text = normalize_text(raw_text)

        heading_class = cell["headingClass"] or ""
        heading_text = normalize_text(
            cell["headingText"] or ""
        )

        print()
        print(f"[CELL {index}]")
        print(f"Heading Text : {heading_text}")
        print(f"Heading Class: {heading_class}")

        # ----------------------------------------------------
        # IMPORTANT:
        # Section identification is based on the actual
        # Pelindo DOM heading class.
        # ----------------------------------------------------

        if "images-v2" in heading_class:

            sections["alongside"] = text

            print("IDENTIFIED   : ALONGSIDE")

        elif "images-v3" in heading_class:

            sections["confirmed"] = text

            print("IDENTIFIED   : CONFIRMED")

        elif "images-v4" in heading_class:

            sections["openStack"] = text

            print("IDENTIFIED   : OPEN STACK")

        elif "images-v5" in heading_class:

            # This is the actual Vessel Schedule section.
            sections["schedule"] = text

            print("IDENTIFIED   : SCHEDULE")

        else:

            print("IDENTIFIED   : UNKNOWN")

    print()
    print("=" * 70)
    print("SECTION SUMMARY")
    print("=" * 70)

    print(
        "Alongside section :",
        "YES" if "alongside" in sections else "NO"
    )

    print(
        "Confirmed section :",
        "YES" if "confirmed" in sections else "NO"
    )

    print(
        "Open Stack section:",
        "YES" if "openStack" in sections else "NO"
    )

    print(
        "Schedule section  :",
        "YES" if "schedule" in sections else "NO"
    )

    print("=" * 70)

    return sections


# ============================================================
# LOAD VESSEL HISTORY
# ============================================================

async def load_history_section(page):

    history_links = page.locator(
        'a[data-url*="vessel_audit"]'
    )

    count = await history_links.count()

    print()
    print("=" * 70)
    print("LOADING VESSEL HISTORY")
    print("=" * 70)

    print("History links found:", count)

    if count == 0:
        print("No History link found.")
        return ""

    # --------------------------------------------------------
    # Only one History click is required to trigger the
    # dynamic Vessel History section.
    # --------------------------------------------------------

    try:

        await history_links.first.click()

        await page.wait_for_timeout(1500)

        print("History modal opened.")

    except Exception as e:

        print(
            "Failed to click History:",
            repr(e)
        )

        return ""

    # --------------------------------------------------------
    # Read dynamically loaded Vessel History section.
    #
    # We deliberately search by visible heading text here,
    # because History is dynamically inserted after clicking.
    # --------------------------------------------------------

    history_cells = await page.locator(
        "td.vessel"
    ).evaluate_all("""
        els => els.map((el, index) => {

            const heading = el.querySelector(
                "span.images-v"
            );

            return {
                index: index,
                text: el.innerText || "",
                headingClass: heading
                    ? heading.className
                    : "",
                headingText: heading
                    ? heading.innerText
                    : ""
            };
        })
    """)

    history_text = ""

    for cell in history_cells:

        text = normalize_text(
            cell["text"]
        )

        heading_text = normalize_text(
            cell["headingText"]
        )

        if "Vessel History" in heading_text:
            history_text = text
            break

        if "Vessel History" in text:
            history_text = text
            break

    # --------------------------------------------------------
    # Close modal.
    # --------------------------------------------------------

    try:

        close_button = page.locator(
            "#TB_closeWindowButton"
        )

        if await close_button.count() > 0:

            await close_button.first.click()

            await page.wait_for_timeout(500)

            print("History modal closed.")

    except Exception as e:

        print(
            "Failed to close History modal:",
            repr(e)
        )

    print(
        "History section found:",
        "YES" if history_text else "NO"
    )

    print("=" * 70)

    return history_text


# ============================================================
# PARSE SCHEDULE
# ============================================================

def parse_schedule(text):

    lines = clean_lines(text)

    schedules = []

    vessel_positions = []

    for i, line in enumerate(lines):

        match = VESSEL_PATTERN.match(line)

        if not match:
            continue

        vessel_name = match.group(1).strip()

        if is_footer_name(vessel_name):
            continue

        vessel_positions.append(i)

    for position_index, start in enumerate(vessel_positions):

        line = lines[start]

        match = VESSEL_PATTERN.match(line)

        if not match:
            continue

        vessel_name = match.group(1).strip()
        vessel_code = match.group(2).strip()

        if position_index + 1 < len(vessel_positions):
            end = vessel_positions[position_index + 1]
        else:
            end = len(lines)

        block = lines[start + 1:end]

        voyage = ""
        etb = ""

        # ----------------------------------------------------
        # Find voyage.
        # ----------------------------------------------------

        for block_line in block:

            if DATE_PATTERN.search(block_line):
                continue

            if block_line.startswith("ETB :"):
                continue

            if block_line in (
                "Detail",
                "[ Detail ]"
            ):
                continue

            if "/" in block_line:

                voyage = block_line

                break

        # ----------------------------------------------------
        # Find ETB.
        # ----------------------------------------------------

        for block_line in block:

            if block_line.startswith("ETB :"):

                etb = block_line.replace(
                    "ETB :",
                    "",
                    1
                ).strip()

                break

        if not voyage or not etb:
            continue

        schedules.append({
            "vesselName": vessel_name,
            "vesselCode": vessel_code,
            "voyage": voyage,
            "etb": etb
        })

    return schedules


# ============================================================
# BUILD DATA
# ============================================================

def build_data(
    alongside,
    confirmed,
    open_stack,
    schedule,
    history
):

    all_vessels = []

    all_vessels.extend(alongside)
    all_vessels.extend(confirmed)
    all_vessels.extend(open_stack)

    # Remove duplicate vessels based on vesselCode.
    unique_vessels = {}

    for vessel in all_vessels:

        code = vessel.get(
            "vesselCode",
            ""
        ).strip()

        if not code:
            continue

        if code not in unique_vessels:
            unique_vessels[code] = vessel

    return {
        "lastUpdated": datetime.now().strftime(
            "%d/%m/%Y %H:%M"
        ),

        "allVessels": list(
            unique_vessels.values()
        ),

        "vesselAlongside": alongside,

        "confirmedVessel": confirmed,

        "openStack": open_stack,

        "vesselSchedule": schedule,

        "vesselHistory": history
    }


# ============================================================
# OPEN PELINDO
# ============================================================

async def open_pelindo(page):

    await page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT
    )

    await page.wait_for_timeout(
        WAIT_AFTER_LOAD
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        page.set_default_timeout(
            NAVIGATION_TIMEOUT
        )

        try:

            success = False

            for attempt in range(
                1,
                MAX_RETRIES + 1
            ):

                print()
                print(
                    f"SCRAPING ATTEMPT {attempt}/{MAX_RETRIES}"
                )

                try:

                    await open_pelindo(page)

                    success = True

                    break

                except PlaywrightTimeoutError:

                    print(
                        "Page load timeout."
                    )

                except Exception as e:

                    print(
                        "Page load error:",
                        repr(e)
                    )

                if attempt < MAX_RETRIES:

                    await page.wait_for_timeout(
                        3000
                    )

            if not success:

                raise RuntimeError(
                    "Pelindo page gagal dibuka."
                )

            # =================================================
            # IMPORTANT ORDER
            #
            # 1. Read the four original sections FIRST.
            # 2. Only AFTER that, open History.
            #
            # This prevents the dynamically inserted History
            # section from interfering with Schedule detection.
            # =================================================

            sections = await get_vessel_sections(
                page
            )

            alongside_text = sections.get(
                "alongside",
                ""
            )

            confirmed_text = sections.get(
                "confirmed",
                ""
            )

            open_stack_text = sections.get(
                "openStack",
                ""
            )

            schedule_text = sections.get(
                "schedule",
                ""
            )

            # -------------------------------------------------
            # Parse the four original sections.
            # -------------------------------------------------

            alongside = parse_vessel_cell(
                alongside_text
            )

            confirmed = parse_vessel_cell(
                confirmed_text
            )

            open_stack = parse_vessel_cell(
                open_stack_text
            )

            schedule = parse_schedule(
                schedule_text
            )

            # =================================================
            # ONLY NOW load Vessel History.
            # =================================================

            history_text = await load_history_section(
                page
            )

            history = parse_vessel_cell(
                history_text
            )

            # =================================================
            # RESULT
            # =================================================

            data = build_data(
                alongside,
                confirmed,
                open_stack,
                schedule,
                history
            )

            print()
            print("=" * 70)
            print("HASIL SCRAPING")
            print("=" * 70)

            print(
                "Alongside:",
                len(alongside)
            )

            print(
                "Confirmed:",
                len(confirmed)
            )

            print(
                "Open Stack:",
                len(open_stack)
            )

            print(
                "Schedule:",
                len(schedule)
            )

            print(
                "History:",
                len(history)
            )

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

            # =================================================
            # SAVE DATA.JSON
            # =================================================

            with open(
                "data.json",
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            print()
            print(
                "DATA.JSON BERHASIL DIBUAT"
            )

            print("=" * 70)
            print("SCRAPER SELESAI")
            print("=" * 70)

        finally:

            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
