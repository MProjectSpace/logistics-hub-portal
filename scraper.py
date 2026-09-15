import json
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

async def scrape_pelindo_four_tables():
    print("🚀 Menjalankan live scraper untuk 4 tabel terminal Pelindo...")
    
    TARGET_URL = "https://ibstpks.pelindo.co.id/webaccess/"

    vessel_alongside = []
    confirmed_vessel = []
    open_stack = []
    vessel_schedule = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"🌐 Membuka portal: {TARGET_URL}")
        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(4000) # Tunggu render JavaScript halaman
        except Exception as e:
            print(f"⚠️ Peringatan saat memuat halaman: {e}")

        # Mengambil semua baris tabel atau elemen kontainer di halaman web
        rows = await page.query_selector_all("table tr, .schedule-item, .vessel-row, li")
        print(f"📊 Ditemukan {len(rows)} elemen baris pada halaman.")

        for index, row in enumerate(rows):
            text_content = await row.inner_text()
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            
            if len(lines) < 2:
                continue

            full_text = " ".join(lines).lower()
            
            # Struktur data dasar
            record = {
                "id": index + 1,
                "vessel": lines[0],
                "voyage": lines[1] if len(lines) > 1 else "-",
                "atb": "-",
                "etb": "-",
                "etd": "-",
                "eta": "-",
                "openStack": "-",
                "closingTime": "-",
                "statusInfo": "Live / Actual"
            }

            # Ekstraksi atribut berdasarkan teks baris
            for line in lines:
                l_lower = line.lower()
                if "atb" in l_lower:
                    record["atb"] = line.replace("ATB", "").strip(" :")
                elif "etb" in l_lower:
                    record["etb"] = line.replace("ETB", "").strip(" :")
                elif "etd" in l_lower:
                    record["etd"] = line.replace("ETD", "").strip(" :")
                elif "eta" in l_lower:
                    record["eta"] = line.replace("ETA", "").strip(" :")
                elif "open" in l_lower or "stack" in l_lower:
                    record["openStack"] = line.replace("Open Stack", "").strip(" :")
                elif "closing" in l_lower or "clt" in l_lower:
                    record["closingTime"] = line.replace("Closing Time", "").strip(" :")

            # Klasifikasi dinamis ke 4 Tabel spesifik
            if "alongside" in full_text or record["atb"] != "-":
                vessel_alongside.append({
                    "id": record["id"],
                    "vessel": record["vessel"],
                    "voyage": record["voyage"],
                    "atb": record["atb"] if record["atb"] != "-" else "Tersedia",
                    "etd": record["etd"] if record["etd"] != "-" else "-"
                })
            elif "confirmed" in full_text or ("etb" in full_text and "open" in full_text):
                confirmed_vessel.append({
                    "id": record["id"],
                    "vessel": record["vessel"],
                    "voyage": record["voyage"],
                    "etb": record["etb"],
                    "etd": record["etd"],
                    "openStack": record["openStack"],
                    "closingTime": record["closingTime"],
                    "statusInfo": "Confirmed / Open"
                })
            elif "open stack" in full_text or record["openStack"] != "-":
                open_stack.append({
                    "id": record["id"],
                    "vessel": record["vessel"],
                    "voyage": record["voyage"],
                    "eta": record["eta"],
                    "etb": record["etb"],
                    "etd": record["etd"],
                    "openStack": record["openStack"],
                    "closingTime": record["closingTime"],
                    "statusInfo": "Open / Actual"
                })
            else:
                vessel_schedule.append({
                    "id": record["id"],
                    "vessel": record["vessel"],
                    "voyage": record["voyage"],
                    "etb": record["etb"] if record["etb"] != "-" else "Scheduled"
                })

        await browser.close()

    final_output = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "totalScraped": len(vessel_alongside) + len(confirmed_vessel) + len(open_stack) + len(vessel_schedule),
        "vesselAlongside": vessel_alongside,
        "confirmedVessel": confirmed_vessel,
        "openStack": open_stack,
        "vesselSchedule": vessel_schedule
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=4)
    
    print(f"✅ Selesai! Berhasil menyedot dan memetakan {final_output['totalScraped']} data ke 4 tabel.")

if __name__ == "__main__":
    asyncio.run(scrape_pelindo_four_tables())
