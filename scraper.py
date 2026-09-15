import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

URL = "https://ibstpks.pelindo.co.id/webaccess/"

VESSEL_PATTERN = re.compile(
    r"^(.+?)\s*\(([^()]+)\)$"
)

VOYAGE_PATTERN = re.compile(
    r"^[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)+\s*/\s*[A-Za-z0-9]+"
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

        for i, line in enumerate(lines):

            match = VESSEL_PATTERN.match(line)

            if not match:
                continue

            vessel_name = match.group(1).strip()
            vessel_code = match.group(2).strip()

            # --------------------------------------
            # VALIDASI BLOK VESSEL
            # --------------------------------------

            next_lines = lines[i + 1:i + 8]

            voyage = ""

            for candidate in next_lines:

                if VOYAGE_PATTERN.match(candidate):
                    voyage = candidate
                    break

            # Kalau tidak ada voyage,
            # kemungkinan bukan data vessel.
            if not voyage:
                continue

            # --------------------------------------
            # DATA FIELD
            # --------------------------------------

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

            block = lines[i + 1:i + 25]

            for item in block:

                if item.startswith("ETA :"):
                    eta = item[5:].strip()

                elif item.startswith("ETB :"):
                    etb = item[5:].strip()

                elif item.startswith("ETD :"):
                    etd = item[5:].strip()

                elif item.startswith("ATB :"):
                    atb = item[5:].strip()

                elif item.startswith("ATD :"):
                    atd = item[5:].strip()

                elif item.startswith("Open Stack :"):
                    open_stack = item[
                        len("Open Stack :"):
                    ].strip()

                elif item.startswith("Closing Time :"):
                    closing_time = item[
                        len("Closing Time :"):
                    ].strip()

                elif item.startswith(
                    "Booking / Open / Actual :"
                ):

                    values = item[
                        len(
                            "Booking / Open / Actual :"
                        ):
                    ].strip().split("/")

                    if len(values) == 3:

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

        # ------------------------------------------
        # VALIDASI
        # ------------------------------------------

        print("")
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

        # ------------------------------------------
        # CLASSIFICATION
        # ------------------------------------------

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

        # ------------------------------------------
        # DATA.JSON
        # ------------------------------------------

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

        print("")
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
