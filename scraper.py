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
    """
    Memastikan kandidat merupakan blok vessel,
    bukan footer/contact information.
    """

    # Harus ada kandidat voyage
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

    # Harus ada indikator bahwa blok ini adalah vessel
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
    """
    Mencari voyage dari beberapa baris pertama
    setelah nama vessel.
    """

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

        # ============================================
        # FILTER NON-VESSEL / FOOTER
        # ============================================

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

        # ============================================
        # AMBIL BLOK
        # ============================================

        block = lines[i + 1:i + 25]

        if not is_valid_vessel_block(block):
            continue

        voyage = extract_voyage(block)

        if not voyage:
            continue

        # ============================================
        # FIELD
        # ============================================

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

        print(
            f"[FOUND] {vessel_name} | {voyage}"
        )

    return vessels


def build_data(vessels):

    alongside = []
    confirmed = []
    open_stack_list = []
    schedule = []

    for vessel in vessels:

        # ============================================
        # ALONGSIDE
        # ============================================

        if vessel["atb"] or vessel["atd"]:

            alongside.append({
                "vesselName":
                    vessel["vesselName"],

                "voyage":
                    vessel["voyage"],

                "atb":
                    vessel["atb"],

                "etd":
                    vessel["etd"]
            })

        # ============================================
        # CONFIRMED
        # ============================================

        if vessel["etb"]:

            confirmed.append({
                "vesselName":
                    vessel["vesselName"],

                "voyage":
                    vessel["voyage"],

                "etb":
                    vessel["etb"],

                "etd":
                    vessel["etd"],

                "openStack":
                    vessel["openStack"],

                "closingTime":
                    vessel["closingTime"],

                "booking":
                    vessel["booking"],

                "open":
                    vessel["open"],

                "actual":
                    vessel["actual"]
            })

            schedule.append({
                "vesselName":
                    vessel["vesselName"],

                "voyage":
                    vessel["voyage"],

                "etb":
                    vessel["etb"]
            })

        # ============================================
        # OPEN STACK
        # ============================================

        if vessel["openStack"]:

            open_stack_list.append({
                "vesselName":
                    vessel["vesselName"],

                "voyage":
                    vessel["voyage"],

                "eta":
                    vessel["eta"],

                "etb":
                    vessel["etb"],

                "etd":
                    vessel["etd"],

                "openStack":
                    vessel["openStack"],

                "closingTime":
                    vessel["closingTime"],

                "booking":
                    vessel["booking"],

                "open":
                    vessel["open"],

                "actual":
                    vessel["actual"]
            })

    return {
        "lastUpdated":
            datetime.now().strftime(
                "%d/%m/%Y %H:%M"
            ),

        "source": URL,

        "vesselAlongside":
            alongside,

        "confirmedVessel":
            confirmed,

        "openStack":
            open_stack_list,

        "vesselSchedule":
            schedule,

        "allVessels":
            vessels
    }


async def open_pelindo(page):
    """
    Membuka Pelindo dengan beberapa strategi.
    """

    for attempt in range(1, MAX_RETRIES + 1):

        print(
            f"[CONNECT] Percobaan {attempt}/{MAX_RETRIES}"
        )

        try:

            # Strategi normal
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

            # Cek apakah browser sebenarnya
            # sudah mendapatkan halaman
            try:

                current_url = page.url

                print(
                    f"[CONNECT] URL saat ini: {current_url}"
                )

                body_count = await page.locator(
                    "body"
                ).count()

                if body_count > 0:

                    print(
                        "[CONNECT] Body halaman tersedia."
                    )

                    return True

            except Exception as check_error:

                print(
                    "[WARNING] Pemeriksaan halaman gagal:",
                    check_error
                )

            # Retry berikutnya
            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 5

                print(
                    f"[CONNECT] Menunggu {wait_seconds} detik "
                    "sebelum retry..."
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


async def main():

    print("======================================")
    print("PELINDO LIVE SCRAPER")
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

        # ============================================
        # BUKA PELINDO
        # ============================================

        print("[1] Membuka Pelindo...")

        success = await open_pelindo(page)

        if not success:

            await browser.close()

            raise RuntimeError(
                "Pelindo tidak dapat diakses setelah "
                f"{MAX_RETRIES} percobaan."
            )

        # ============================================
        # TUNGGU DATA JAVASCRIPT
        # ============================================

        print(
            "[2] Menunggu data vessel..."
        )

        await page.wait_for_timeout(
            WAIT_AFTER_LOAD
        )

        # ============================================
        # BACA BODY
        # ============================================

        print(
            "[3] Membaca data halaman..."
        )

        text = await page.locator(
            "body"
        ).inner_text()

        if not text.strip():

            await browser.close()

            raise RuntimeError(
                "Halaman Pelindo terbuka tetapi "
                "tidak menghasilkan text."
            )

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        print(
            f"[4] Total baris halaman: {len(lines)}"
        )

        # ============================================
        # PARSE
        # ============================================

        print(
            "[5] Mencari vessel..."
        )

        vessels = parse_vessels(lines)

        # ============================================
        # VALIDASI HASIL
        # ============================================

        print("")
        print("======================================")
        print("HASIL SCRAPING")
        print("======================================")

        print(
            "Jumlah vessel:",
            len(vessels)
        )

        if len(vessels) == 0:

            await browser.close()

            raise RuntimeError(
                "Pelindo berhasil dibuka tetapi "
                "tidak ada vessel valid ditemukan."
            )

        # ============================================
        # BUAT DATA
        # ============================================

        data = build_data(vessels)

        # ============================================
        # SIMPAN
        # ============================================

        with open(
            "data.json",
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        print("")
        print("======================================")
        print("DATA.JSON BERHASIL DIBUAT")
        print("======================================")

        print(
            "Alongside:",
            len(data["vesselAlongside"])
        )

        print(
            "Confirmed:",
            len(data["confirmedVessel"])
        )

        print(
            "Open Stack:",
            len(data["openStack"])
        )

        print(
            "Schedule:",
            len(data["vesselSchedule"])
        )

        print("")
        print("=== SCRAPER SELESAI ===")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
