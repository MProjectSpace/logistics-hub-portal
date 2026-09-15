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


async def main():

    print("=== PELINDO LIVE SCRAPER ===")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        page = await browser.new_page(
            viewport={"width": 1440, "height": 900}
        )

        print("[1] Membuka Pelindo...")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("[2] Menunggu data...")

        await page.wait_for_timeout(10000)

        text = await page.locator("body").inner_text()

        lines = [
            x.strip()
            for x in text.splitlines()
            if x.strip()
        ]

        vessels = []

        # ==================================================
        # CARI VESSEL
        # ==================================================

        for i, line in enumerate(lines):

            match = VESSEL_PATTERN.match(line)

            if not match:
                continue

            vessel_name = match.group(1).strip()
            vessel_code = match.group(2).strip()

            # Hindari footer / kontak
            bad_words = [
                "WA Hotline",
                "Telpon/Wa",
                "Support",
                "Contact",
                "Planner"
            ]

            if any(
                word.lower() in vessel_name.lower()
                for word in bad_words
            ):
                continue

            # ==================================================
            # AMBIL BLOK DATA DI BAWAH NAMA VESSEL
            # ==================================================

            block = lines[i + 1:i + 25]

            voyage = ""

            # Voyage biasanya berada tepat setelah nama vessel,
            # tetapi kita cari beberapa baris ke bawah.
            for candidate in block[:5]:

                # Jangan ambil tanggal sebagai voyage
                if DATE_PATTERN.search(candidate):
                    continue

                # Voyage harus mengandung "/"
                if "/" in candidate:

                    # Hindari field tanggal / URL / kontak
                    if (
                        "Booking / Open / Actual" not in candidate
                        and "Open Stack" not in candidate
                        and "Closing Time" not in candidate
                    ):
                        voyage = candidate
                        break

            # ==================================================
            # CEK APAKAH INI BENAR-BENAR BLOK VESSEL
            # ==================================================

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

            is_vessel = (
                voyage
                and any(
                    keyword in block
                    for keyword in operational_keywords
                    for block in [block]
                )
            )

            if not is_vessel:
                continue

            # ==================================================
            # FIELD
            # ==================================================

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
                        "ETA :", ""
                    ).strip()

                elif item.startswith("ETB :"):

                    etb = item.replace(
                        "ETB :", ""
                    ).strip()

                elif item.startswith("ETD :"):

                    etd = item.replace(
                        "ETD :", ""
                    ).strip()

                elif item.startswith("ATB :"):

                    atb = item.replace(
                        "ATB :", ""
                    ).strip()

                elif item.startswith("ATD :"):

                    atd = item.replace(
                        "ATD :", ""
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

                    values = item.replace(
                        "Booking / Open / Actual :",
                        ""
                    ).strip().split("/")

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

        # ==================================================
        # HASIL
        # ==================================================

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

        # ==================================================
        # CLASSIFICATION
        # ==================================================

        alongside = []
        confirmed = []
        open_stack_list = []
        schedule = []

        for v in vessels:

            if v["atb"] or v["atd"]:

                alongside.append({
                    "vesselName": v["vesselName"],
                    "voyage": v["voyage"],
                    "atb": v["atb"],
                    "etd": v["etd"]
                })

            if v["etb"]:

                confirmed.append({
                    "vesselName": v["vesselName"],
                    "voyage": v["voyage"],
                    "etb": v["etb"],
                    "etd": v["etd"],
                    "openStack": v["openStack"],
                    "closingTime": v["closingTime"],
                    "booking": v["booking"],
                    "open": v["open"],
                    "actual": v["actual"]
                })

                schedule.append({
                    "vesselName": v["vesselName"],
                    "voyage": v["voyage"],
                    "etb": v["etb"]
                })

            if v["openStack"]:

                open_stack_list.append({
                    "vesselName": v["vesselName"],
                    "voyage": v["voyage"],
                    "eta": v["eta"],
                    "etb": v["etb"],
                    "etd": v["etd"],
                    "openStack": v["openStack"],
                    "closingTime": v["closingTime"],
                    "booking": v["booking"],
                    "open": v["open"],
                    "actual": v["actual"]
                })

        # ==================================================
        # SIMPAN DATA.JSON
        # ==================================================

        data = {
            "lastUpdated":
                datetime.now().strftime(
                    "%d/%m/%Y %H:%M"
                ),

            "source": URL,

            "vesselAlongside": alongside,

            "confirmedVessel": confirmed,

            "openStack": open_stack_list,

            "vesselSchedule": schedule,

            "allVessels": vessels
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

        await browser.close()

        print("=== SCRAPER SELESAI ===")


if __name__ == "__main__":
    asyncio.run(main())
