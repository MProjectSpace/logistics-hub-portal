import json
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

async def scrape_all_pelindo_data():
    print("🚀 Memulai scraper untuk mengambil SEMUA data dari Pelindo...")
    
    # URL target portal Webaccess Pelindo / Terminal terkait
    TARGET_URL = "https://ibstpks.pelindo.co.id/webaccess/"

    all_open_stack = []
    all_estimated_berth = []

    async with async_playwright() as p:
        # Menjalankan browser Chromium otomatis di latar belakang
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"🌐 Membuka halaman: {TARGET_URL}")
        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"⚠️ Peringatan saat memuat halaman: {e}")

        # Auto-scroll & cek pagination untuk memastikan semua data termuat
        print("📜 Memeriksa halaman dan melakukan scroll otomatis...")
        previous_height = 0
        while True:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)

            # Cek tombol halaman berikutnya (Next) jika ada
            next_button = page.locator("a:has-text('Next'), button:has-text('Next'), .next-page")
            if await next_button.count() > 0 and await next_button.is_visible():
                await next_button.click()
                await page.wait_for_timeout(2000)
            
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break
            previous_height = current_height

        # Mengekstrak baris data tabel
        print("🔍 Mengekstrak data tabel kapal...")
        rows = await page.query_selector_all("table tbody tr, .schedule-row, .vessel-card")
        print(f"📊 Ditemukan {len(rows)} baris data.")

        for index, row in enumerate(rows):
            text_content = await row.inner_text()
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            
            if not lines or len(lines) < 2:
                continue

            full_text_lower = " ".join(lines).lower()
            
            row_data = {
                "id": index + 1,
                "vessel": lines[0],
                "voyage": lines[1] if len(lines) > 1 else "-",
                "startOpen": "-",
                "closingTime": "-",
                "eta": "-",
                "etb": "-",
                "estDeparture": "-"
            }

            for line in lines:
                line_lower = line.lower()
                if "open stack" in line_lower or "open:" in line_lower:
                    row_data["startOpen"] = line.replace("Open Stack :", "").replace("Open :", "").strip()
                elif "closing" in line_lower or "clt" in line_lower:
                    row_data["closingTime"] = line.replace("Closing Time :", "").strip()
                elif "etb" in line_lower or "sandar" in line_lower:
                    row_data["etb"] = line.replace("ETB :", "").strip()
                elif "eta" in line_lower or "tiba" in line_lower:
                    row_data["eta"] = line.replace("ETA :", "").strip()
                elif "etd" in line_lower or "berangkat" in line_lower:
                    row_data["estDeparture"] = line.replace("ETD :", "").strip()

            if "open stack" in full_text_lower or row_data["startOpen"] != "-":
                all_open_stack.append(row_data)
            else:
                all_estimated_berth.append(row_data)

        await browser.close()

    # Struktur data hasil akhir
    final_output = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "totalRecordsScraped": len(all_open_stack) + len(all_estimated_berth),
        "openStack": all_open_stack,
        "estimatedBerth": all_estimated_berth
    }

    # Menyimpan ke file data.json
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(final_output, f, ensure_ascii=False, indent=4)
    
    print("✅ Berhasil menyimpan data ke data.json!")

if __name__ == "__main__":
    asyncio.run(scrape_all_pelindo_data())
