import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

URL = "https://ibstpks.pelindo.co.id/webaccess/"


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

        print("[3] Data halaman berhasil dibaca")

        lines = [
            x.strip()
            for x in text.splitlines()
            if x.strip()
        ]

        vessels = []

        # Pola nama vessel:
        # NAMA KAPAL (KODE)
        vessel_pattern = re.compile(
            r"^(.+?)\s*\(([^()]+)\)$"
        )

        # Pola tanggal
        date_pattern = re.compile(
            r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}"
        )

        i = 0

        while i < len(lines):

            match = vessel_pattern.match(lines[i])

            if not match:
                i += 1
                continue

            vessel_name = match.group(1).strip()
            vessel_code = match.group(2).strip()

            # Hindari false positive
            if len(vessel_name) < 3:
                i += 1
                continue

            voyage = ""
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

            # Ambil maksimal 20 baris setelah nama kapal
            block = lines[i + 1:i + 21]

            for line in block:

                if not voyage and (
                    "/" in line
                    and not date_pattern.search(line)
                ):
                    voyage = line

                if line.startswith("ETA :"):
                    eta = line.replace(
                        "ETA :", ""
                    ).strip()

                elif line.startswith("ETB :"):
                    etb = line.replace(
                        "ETB :", ""
                    ).strip()

                elif line.startswith("ETD :"):
                    etd = line.replace(
                        "ETD :", ""
                    ).strip()

                elif line.startswith("ATB :"):
                    atb = line.replace(
                        "ATB :", ""
                    ).strip()

                elif line.startswith("ATD :"):
                    atd = line.replace(
                        "ATD :", ""
                    ).strip()

                elif line.startswith("Open Stack :"):
                    open_stack = line.replace(
                        "Open Stack :", ""
                    ).strip()

                elif line.startswith("Closing Time :"):
                    closing_time = line.replace(
                        "Closing Time :", ""
                    ).strip()

                elif line.startswith(
                    "Booking / Open / Actual :"
                ):

                    values = line.replace(
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
                "actual": actual,
            }

            vessels.append(vessel)

            print(
                f"[FOUND] {vessel_name} | {voyage}"
            )

            i += 1

        # ==========================================
        # VALIDATION
        # ==========================================

        print("")
        print("======================================")
        print("HASIL SCRAPING")
        print("======================================")

        print(
            "Jumlah vessel:",
            len(vessels)
        )

        if not vessels:

            print(
                "ERROR: Tidak ada vessel ditemukan."
            )

            await browser.close()

            raise RuntimeError(
                "Pelindo tidak menghasilkan data vessel."
            )

        # ==========================================
        # CLASSIFICATION
        # ==========================================

        vessel_alongside = []
        confirmed_vessel = []
        open_stack_vessel = []
        vessel_schedule = []

        for vessel in vessels:

            # Vessel Alongside
            if vessel["atb"] or vessel["atd"]:

                vessel_alongside.append({
                    "vesselName":
                        vessel["vesselName"],
                    "voyage":
                        vessel["voyage"],
                    "atb":
                        vessel["atb"],
                    "etd":
                        vessel["etd"],
                })

            # Vessel yang sudah punya Open Stack
            if vessel["openStack"]:

                open_stack_vessel.append({
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
                        vessel["actual"],
                })

            # Confirmed Vessel
            if vessel["etb"]:

                confirmed_vessel.append({
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
                        vessel["actual"],
                })

            # Vessel Schedule
            if vessel["etb"]:

                vessel_schedule.append({
                    "vesselName":
                        vessel["vesselName"],
                    "voyage":
                        vessel["voyage"],
                    "etb":
                        vessel["etb"],
                })

        # ==========================================
        # OUTPUT
        # ==========================================

        data = {
            "lastUpdated":
                datetime.now().strftime(
                    "%d/%m/%Y %H:%M"
                ),

            "source": URL,

            "vesselAlongside":
                vessel_alongside,

            "confirmedVessel":
                confirmed_vessel,

            "openStack":
                open_stack_vessel,

            "vesselSchedule":
                vessel_schedule,

            "allVessels":
                vessels,
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
            len(vessel_alongside)
        )

        print(
            "Confirmed:",
            len(confirmed_vessel)
        )

        print(
            "Open Stack:",
            len(open_stack_vessel)
        )

        print(
            "Schedule:",
            len(vessel_schedule)
        )

        await browser.close()

        print("")
        print("=== SCRAPER SELESAI ===")


if __name__ == "__main__":
    asyncio.run(main())
