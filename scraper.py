import asyncio

from playwright.async_api import async_playwright


URL = "https://ibstpks.pelindo.co.id/webaccess/"


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = await browser.new_page(
            viewport={
                "width": 1440,
                "height": 900,
            }
        )

        # ==========================================
        # MONITOR NETWORK
        # ==========================================

        async def response_handler(response):

            try:

                resource_type = response.request.resource_type

                content_type = (
                    response.headers
                    .get("content-type", "")
                    .lower()
                )

                if (
                    resource_type in ["xhr", "fetch"]
                    or "json" in content_type
                ):

                    print(
                        "[API/REQUEST]",
                        response.status,
                        response.url
                    )

            except Exception:
                pass

        page.on("response", response_handler)

        # ==========================================
        # OPEN PELINDO
        # ==========================================

        print("")
        print("======================================")
        print("MEMBUKA WEBSITE PELINDO")
        print("======================================")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print("Website berhasil dibuka.")

        # ==========================================
        # WAIT APPLICATION
        # ==========================================

        print("")
        print("Menunggu aplikasi Pelindo...")

        await page.wait_for_timeout(15000)

        try:

            await page.wait_for_load_state(
                "networkidle",
                timeout=15000
            )

        except Exception:

            print(
                "Network idle timeout."
                " Tetap melanjutkan proses."
            )

        await page.wait_for_timeout(5000)

        # ==========================================
        # PAGE INFORMATION
        # ==========================================

        print("")
        print("======================================")
        print("PAGE TITLE")
        print("======================================")

        print(await page.title())

        print("")
        print("======================================")
        print("CURRENT URL")
        print("======================================")

        print(page.url)

        # ==========================================
        # BODY TEXT
        # ==========================================

        print("")
        print("======================================")
        print("VISIBLE TEXT")
        print("======================================")

        text = await page.locator("body").inner_text()

        print(text[:30000])

        # ==========================================
        # SCREENSHOT
        # ==========================================

        print("")
        print("Menyimpan screenshot...")

        await page.screenshot(
            path="pelindo.png",
            full_page=True
        )

        # ==========================================
        # HTML
        # ==========================================

        print("Menyimpan HTML...")

        with open(
            "debug.html",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                await page.content()
            )

        print("")
        print("======================================")
        print("DIAGNOSTIC SELESAI")
        print("======================================")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
