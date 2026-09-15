import asyncio
from playwright.async_api import async_playwright

URL = "https://ibstpks.pelindo.co.id/webaccess/"


async def main():
    print("=== SCRAPER TEST BARU ===")

    async with async_playwright() as p:
        print("[1] Playwright OK")

        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        print("[2] Chromium OK")

        page = await browser.new_page()

        print("[3] Membuka Pelindo...")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("[4] Pelindo berhasil dibuka")
        print("[5] Menunggu 10 detik...")

        await page.wait_for_timeout(10000)

        print("[6] TITLE:")
        print(await page.title())

        print("[7] URL:")
        print(page.url)

        print("[8] VISIBLE TEXT:")
        text = await page.locator("body").inner_text()
        print(text[:5000])

        print("=== TEST SELESAI ===")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
