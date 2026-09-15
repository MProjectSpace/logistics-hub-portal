import json
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

async def scrape_dynamic_pelindo_data():
    print("🚀 Memulai live scraper dinamis untuk Pelindo...")
    
    TARGET_URL = "https://ibstpks.pelindo.co.id/webaccess/"

    vessel_alongside = []
    confirmed_vessel = []
    open_stack = []
    vessel_schedule = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"🌐 Mengakses URL: {TARGET_URL}")
        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000) # Tunggu render JavaScript selesai
        except Exception as e:
            print(f"⚠️ Warning saat load halaman: {e}")

        # Ambil semua elemen teks atau baris tabel dari halaman web asli
        rows = await page.query_selector_all("table tr, .row, li, .card")
        print(f"📊 Menemukan {len(rows)} elemen baris/kartu di halaman.")

        for index, row in enumerate(rows):
            text = await row.inner_text()
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            if len(lines) < 2:
                continue

            full_text_lower = " ".join(lines).lower()
            
            item = {
                "id": index + 1,
                "vessel": lines[0],
                "voyage": lines[1] if len(lines) > 1 else "-",
                "atb": "-",
                "etd": "-",
                "eta": "-",
                "etb": "-",
                "openStack": "-",
                "closingTime": "-",
                "statusInfo": "Live Data"
            }

            # Parsing dinamis berdasarkan kata kunci di teks baris
            for line in lines:
                l_lower = line.lower()
                if "atb" in l_lower or "alongside" in l_lower:
                    item["atb"] = line.replace("ATB", "").strip(" :")
                elif "etd" in l_lower or "departure" in l_lower:
                    item["etd"] = line.replace("ETD", "").strip(" :")
                    item["estDeparture"] = item["etd"]
                elif "eta" in l_lower:
                    item["eta"] = line.replace("ETA", "").strip(" :")
                elif "etb" in l_lower:
                    item["etb"] = line.replace("ETB", "").strip(" :")
                elif "open" in l_lower or "stack" in l_lower:
                    item["openStack"] = line.replace("Open Stack", "").strip(" :")
                elif "closing" in l_lower or "clt" in l_lower:
                    item["closingTime"] = line.replace("Closing Time", "").strip(" :")

            # Klasifikasi otomatis ke 4 tabel berdasarkan status teks asli
            if "alongside" in full_text_lower or item["atb"] != "-":
                vessel_alongside.append(item)
            elif "confirmed" in full_text_lower:
                confirmed_vessel.append(item)
            elif "open stack" in full_text_lower or item["openStack"] != "-":
                open_stack.append(item)
            else:
                vessel_schedule.append(item)

        await browser.close()

    # Struktur JSON akhir untuk 4 tabel
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
    
    print(f"✅ Berhasil menyedot total {final_output['totalScraped']} data dinamis dari web Pelindo!")

if __name__ == "__main__":
    asyncio.run(scrape_dynamic_pelindo_data())
