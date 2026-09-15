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


def is_valid_vessel_block(block):

    has_voyage = False

    for line in block[:6]:

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if line.startswith("Booking / Open / Actual"):
            continue

        if line.startswith("Open Stack"):
            continue

        if line.startswith("Closing Time"):
            continue

        has_voyage = True
        break

    if not has_voyage:
        return False

    operational_keywords = [
        "DOMESTIC",
        "INTERNATIONAL",
        "ETA :",
        "ETB :",
        "ETD :",
        "ATB :",
        "ATD :",
        "Open Stack :",
        "Closing Time :",
        "Booking / Open / Actual :"
    ]

    for line in block:

        for keyword in operational_keywords:

            if keyword in line:
                return True

    return False


def extract_voyage(block):

    for line in block[:6]:

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if line.startswith("Booking / Open / Actual"):
            continue

        if line.startswith("Open Stack"):
            continue

        if line.startswith("Closing Time"):
            continue

        return line

    return ""


def parse_vessels(lines):

    vessels = []

    for i, line in enumerate(lines):

        match = VESSEL_PATTERN.match(line)

        if not match:
            continue

        vessel_name = match.group(1).strip()
        vessel_code = match.group(2).strip()

        blocked_words = [
            "WA Hotline",
            "Telpon/Wa",
            "Support",
            "Contact",
            "Planner",
            "Customer Service"
        ]

        if any(
            word.lower() in vessel_name.lower()
            for word in blocked_words
        ):
            continue

        block = lines[i + 1:i + 25]

        if not is_valid_vessel_block(block):
            continue

        voyage = extract_voyage(block)

        if not voyage:
            continue

        eta = ""
        etb = ""
        etd = ""
        atb = ""
        atd = ""

        open_stack = ""
        closing_time = ""

        booking = ""
        open_qty = ""
        actual = ""

        for item in block:

            if item.startswith("ETA :"):

                eta = item.replace(
                    "ETA :",
                    ""
                ).strip()

            elif item.startswith("ETB :"):

                etb = item.replace(
                    "ETB :",
                    ""
                ).strip()

            elif item.startswith("ETD :"):

                etd = item.replace(
                    "ETD :",
                    ""
                ).strip()

            elif item.startswith("ATB :"):

                atb = item.replace(
                    "ATB :",
                    ""
                ).strip()

            elif item.startswith("ATD :"):

                atd = item.replace(
                    "ATD :",
                    ""
                ).strip()

            elif item.startswith("Open Stack :"):

                open_stack = item.replace(
                    "Open Stack :",
                    ""
                ).strip()

            elif item.startswith("Closing Time :"):

                closing_time = item.replace(
                    "Closing Time :",
                    ""
                ).strip()

            elif item.startswith(
                "Booking / Open / Actual :"
            ):

                raw = item.replace(
                    "Booking / Open / Actual :",
                    ""
                ).strip()

                values = raw.split("/")

                if len(values) >= 3:

                    booking = values[0].strip()
                    open_qty = values[1].strip()
                    actual = values[2].strip()

        vessel = {
            "vesselName": vessel_name,
            "vesselCode": vessel_code,
            "voyage": voyage,
            "eta": eta,
            "etb": etb,
            "etd": etd,
            "atb": atb,
            "atd": atd,
            "openStack": open_stack,
            "closingTime": closing_time,
            "booking": booking,
            "open": open_qty,
            "actual": actual
        }

        vessels.append(vessel)

    return vessels


async def open_pelindo(page):

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"[CONNECT] Percobaan "
            f"{attempt}/{MAX_RETRIES}"
        )

        try:

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT
            )

            print(
                "[CONNECT] Pelindo berhasil dibuka."
            )

            return True

        except PlaywrightTimeoutError:

            print(
                "[WARNING] Navigation timeout."
            )

            try:

                body_count = await page.locator(
                    "body"
                ).count()

                if body_count > 0:

                    print(
                        "[CONNECT] Body halaman tersedia."
                    )

                    return True

            except Exception:
                pass

            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 5

                print(
                    f"[CONNECT] Menunggu "
                    f"{wait_seconds} detik..."
                )

                await page.wait_for_timeout(
                    wait_seconds * 1000
                )

        except Exception as error:

            print(
                f"[WARNING] Koneksi gagal: {error}"
            )

            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 5

                print(
                    f"[CONNECT] Retry dalam "
                    f"{wait_seconds} detik..."
                )

                await page.wait_for_timeout(
                    wait_seconds * 1000
                )

    return False


async def diagnose_history(page):

    print("")
    print("======================================")
    print("HISTORY BUTTON DIAGNOSTIC")
    print("======================================")

    # ==========================================
    # CARI SEMUA ELEMEN HISTORY
    # ==========================================

    history_elements = await page.evaluate(
        """
        () => {

            const result = [];

            const elements =
                document.querySelectorAll("*");

            for (const el of elements) {

                const text =
                    (el.innerText || "").trim();

                if (
                    text.toLowerCase() === "history"
                ) {

                    result.push({

                        tag:
                            el.tagName,

                        id:
                            el.id || "",

                        className:
                            typeof el.className === "string"
                                ? el.className
                                : "",

                        href:
                            el.getAttribute("href") || "",

                        onclick:
                            el.getAttribute("onclick") || "",

                        outerHTML:
                            el.outerHTML.substring(
                                0,
                                2000
                            )
                    });
                }
            }

            return result;
        }
        """
    )

    print(
        "Jumlah elemen exact 'History':",
        len(history_elements)
    )

    for index, item in enumerate(
        history_elements[:20],
        1
    ):

        print("")
        print(
            f"[HISTORY {index}]"
        )

        print(
            f"TAG = {item['tag']}"
        )

        print(
            f"ID = {item['id']}"
        )

        print(
            f"CLASS = {item['className']}"
        )

        print(
            f"HREF = {item['href']}"
        )

        print(
            f"ONCLICK = {item['onclick']}"
        )

        print(
            "HTML ="
        )

        print(
            item["outerHTML"]
        )

    # ==========================================
    # CARI TD.VESSEL
    # ==========================================

    vessel_cells = page.locator(
        "td.vessel"
    )

    count = await vessel_cells.count()

    print("")
    print(
        "Jumlah td.vessel:",
        count
    )

    # ==========================================
    # CARI VESSEL PERTAMA YANG MEMILIKI HISTORY
    # ==========================================

    for i in range(count):

        cell = vessel_cells.nth(i)

        text = (
            await cell.inner_text()
        ).strip()

        if "History" not in text:

            continue

        print("")
        print("======================================")
        print(
            f"VESSEL CELL PERTAMA DENGAN HISTORY: "
            f"{i + 1}"
        )
        print("======================================")

        print(
            text[:2000]
        )

        # ======================================
        # CARI LINK / BUTTON HISTORY
        # ======================================

        candidates = cell.locator(
            "a, button, input, span"
        )

        candidate_count = (
            await candidates.count()
        )

        print("")
        print(
            "Jumlah kandidat tombol/link:",
            candidate_count
        )

        for j in range(
            candidate_count
        ):

            candidate = candidates.nth(j)

            candidate_text = (
                await candidate.inner_text()
            ).strip()

            value = await candidate.get_attribute(
                "value"
            )

            href = await candidate.get_attribute(
                "href"
            )

            onclick = await candidate.get_attribute(
                "onclick"
            )

            if (
                "history" in candidate_text.lower()
                or (
                    value
                    and "history"
                    in value.lower()
                )
            ):

                print("")
                print(
                    f"[CANDIDATE {j + 1}]"
                )

                print(
                    "TEXT =",
                    candidate_text
                )

                print(
                    "VALUE =",
                    value
                )

                print(
                    "HREF =",
                    href
                )

                print(
                    "ONCLICK =",
                    onclick
                )

                print(
                    "HTML ="
                )

                print(
                    (
                        await candidate.evaluate(
                            "(el) => el.outerHTML"
                        )
                    )[:3000]
                )

        break


async def main():

    print("======================================")
    print("PELINDO HISTORY DIAGNOSTIC")
    print("======================================")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        page = await browser.new_page(
            viewport={
                "width": 1440,
                "height": 900
            }
        )

        print("[1] Membuka Pelindo...")

        success = await open_pelindo(page)

        if not success:

            await browser.close()

            raise RuntimeError(
                "Pelindo tidak dapat diakses."
            )

        print(
            "[2] Menunggu data vessel..."
        )

        await page.wait_for_timeout(
            WAIT_AFTER_LOAD
        )

        print(
            "[3] Menjalankan diagnostic..."
        )

        await diagnose_history(page)

        print("")
        print("======================================")
        print("DIAGNOSTIC SELESAI")
        print("======================================")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
