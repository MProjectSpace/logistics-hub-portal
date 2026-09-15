```python
import asyncio
from playwright.async_api import async_playwright

URL = "https://ibstpks.pelindo.co.id/webaccess/"


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        page = await browser.new_page()

        print("Membuka Pelindo...")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=120000
        )

        print("Pelindo berhasil dibuka.")
        print("Menunggu data...")

        await page.wait_for_timeout(10000)

        text = await page.locator("body").inner_text()

        print("\n" + "=" * 70)
        print("DATA HALAMAN PELINDO")
        print("=" * 70)

        print(text)

        print("\n" + "=" * 70)
        print("SELESAI")
        print("=" * 70)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
```
