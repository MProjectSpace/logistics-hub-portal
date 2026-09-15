import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright


URL = "https://ibstpks.pelindo.co.id/webaccess/"

VESSEL_PATTERN = re.compile(
    r"^(.+?)\s*\(([^()]+)\)$"
)

DATE_PATTERN = re.compile(
    r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}"
)


def is_valid_vessel_block(block):
    """
    Memastikan kandidat benar-benar blok data vessel,
    bukan footer/contact information.
    """

    # Harus punya voyage
    has_voyage = False

    for line in block[:6]:

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if "Booking / Open / Actual" in line:
            continue

        if "Open Stack" in line:
            continue

        if "Closing Time" in line:
            continue

        has_voyage = True
        break

    if not has_voyage:
        return False

    # Harus punya minimal satu indikator data vessel
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


async def main():

    print("=== PELINDO LIVE SCRAPER ===")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        page = await browser.new_page(
            viewport={
                "width": 1440,
                "height": 900
            }
        )

        print("[1] Membuka Pelindo...")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("[2] Menunggu data...")

        await page.wait_for_timeout(10000)

        text = await page.locator(
            "body"
        ).inner_text()

        print("[3] Data halaman berhasil dibaca")

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        vessels = []

        # =====================================================
        # CARI SEMUA KANDIDAT VESSEL
        # =====================================================

        for i, line in enumerate(lines):

            match = VESSEL_PATTERN.match(line)

            if not match:
                continue

            vessel_name = match.group(1).strip()
            vessel_code = match.group(2).strip()

            # ---------------------------------------------
            # FILTER FOOTER / CONTACT
            # ---------------------------------------------

            blocked_words = [
                "WA Hotline",
                "Telpon/Wa",
                "Support",
                "Contact",
                "Planner"
            ]

            if any(
                word.lower() in vessel_name.lower()
                for word in blocked_words
            ):
                continue

            # ---------------------------------------------
            # AMBIL DATA DI BAWAH NAMA VESSEL
            # ---------------------------------------------

            block = lines[i + 1:i + 25]

            # ---------------------------------------------
            # VALIDASI
            # ---------------------------------------------

            if not is_valid_vessel_block(block):
                continue

            # ---------------------------------------------
            # VOYAGE
            # ---------------------------------------------

            voyage = ""

            for candidate in block[:6]:

                if "/" not in candidate:
                    continue

                if DATE_PATTERN.search(candidate):
                    continue

                if "Booking / Open / Actual" in candidate:
                    continue

                if "Open Stack" in candidate:
                    continue

                if "Closing Time" in candidate:
                    continue

                voyage = candidate
                break

            # ---------------------------------------------
            # FIELD
            # ---------------------------------------------

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

                elif item.startswith(
                    "Open Stack :"
                ):

                    open_stack = item.replace(
                        "Open Stack :",
                        ""
                    ).strip()

                elif item.startswith(
                    "Closing Time :"
                ):

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

            # ---------------------------------------------
            # SIMPAN VESSEL
            # ---------------------------------------------

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

        # =====================================================
        # HASIL SCRAPING
        # =====================================================

        print("======================================")

        print("HASIL SCRAPING")

        print("======================================")

        print(
            "Jumlah vessel:",
            len(vessels)
        )

        if not vessels:

            raise RuntimeError(
                "Tidak ada vessel valid ditemukan."
            )

        # =====================================================
        # CLASSIFICATION
        # =====================================================

        alongside = []

        confirmed = []

        open_stack_list = []

        schedule = []

        for vessel in vessels:

            # ---------------------------------------------
            # VESSEL ALONGSIDE
            # ---------------------------------------------

            if (
                vessel["atb"]
                or vessel["atd"]
            ):

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

            # ---------------------------------------------
            # CONFIRMED VESSEL
            # ---------------------------------------------

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

                # -----------------------------------------
                # SCHEDULE
                # -----------------------------------------

                schedule.append({

                    "vesselName":
                        vessel["vesselName"],

                    "voyage":
                        vessel["voyage"],

                    "etb":
                        vessel["etb"]
                })

            # ---------------------------------------------
            # OPEN STACK
            # ---------------------------------------------

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

        # =====================================================
        # DATA JSON
        # =====================================================

        data = {

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

        # =====================================================
        # SUMMARY
        # =====================================================

        print("======================================")

        print("DATA.JSON BERHASIL DIBUAT")

        print("======================================")

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
            len(open_stack_list)
        )

        print(
            "Schedule:",
            len(schedule)
        )

        print("")

        print("=== SCRAPER SELESAI ===")

        await browser.close()


if __name__ == "__main__":

    asyncio.run(main())
