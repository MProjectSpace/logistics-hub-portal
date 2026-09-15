import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


URL = "https://ibstpks.pelindo.co.id/webaccess/"


KEYWORDS = [
    "Vessel Alongside",
    "Confirmed Vessel",
    "Open Stack",
    "Vessel Schedule",
    "Vessel History",
]


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

        print("======================================")
        print("MEMBUKA WEBSITE PELINDO")
        print("======================================")

        await page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        print("Website berhasil dibuka.")

        print("")
        print("Menunggu aplikasi Pelindo...")

        await page.wait_for_timeout(15000)

        # ==========================================
        # BASIC INFORMATION
        # ==========================================

        print("")
        print("======================================")
        print("PAGE INFORMATION")
        print("======================================")

        print("TITLE :", await page.title())
        print("URL   :", page.url)

        # ==========================================
        # SEARCH EACH SECTION
        # ==========================================

        print("")
        print("======================================")
        print("SECTION SEARCH")
        print("======================================")

        for keyword in KEYWORDS:

            print("")
            print("--------------------------------------")
            print(keyword)
            print("--------------------------------------")

            locator = page.get_by_text(
                keyword,
                exact=False
            )

            count = await locator.count()

            print("Element ditemukan:", count)

            for i in range(count):

                element = locator.nth(i)

                try:

                    info = await element.evaluate(
                        """
                        el => {
                            let parent = el.parentElement;

                            return {
                                tag: el.tagName,
                                id: el.id,
                                className: el.className,
                                text: el.innerText,
                                parentTag: parent ? parent.tagName : null,
                                parentId: parent ? parent.id : null,
                                parentClass: parent ? parent.className : null,
                                parentText: parent ? parent.innerText : null
                            };
                        }
                        """
                    )

                    print("")
                    print("ELEMENT:", info)

                except Exception as e:

                    print(
                        "Gagal inspect:",
                        e
                    )

        # ==========================================
        # ALL TABLES
        # ==========================================

        print("")
        print("======================================")
        print("TABLE INSPECTION")
        print("======================================")

        tables = page.locator("table")

        table_count = await tables.count()

        print(
            "Jumlah table:",
            table_count
        )

        for i in range(table_count):

            table = tables.nth(i)

            try:

                print("")
                print(
                    f"========== TABLE {i + 1} =========="
                )

                print(
                    await table.inner_text()
                )

            except Exception as e:

                print(
                    "Gagal membaca table:",
                    e
                )

        # ==========================================
        # CARDS
        # ==========================================

        print("")
        print("======================================")
        print("POSSIBLE CARDS")
        print("======================================")

        selectors = [
            ".card",
            "[class*='card']",
            "[class*='vessel']",
            "[class*='Vessel']",
            "article",
        ]

        for selector in selectors:

            try:

                locator = page.locator(selector)

                count = await locator.count()

                print("")
                print(
                    selector,
                    "=>",
                    count
                )

                for i in range(
                    min(count, 20)
                ):

                    element = locator.nth(i)

                    try:

                        text = await element.inner_text()

                        if text.strip():

                            print("")
                            print(
                                f"[{selector} #{i}]"
                            )

                            print(
                                text[:3000]
                            )

                    except Exception:
                        pass

            except Exception:
                pass

        # ==========================================
        # SAVE FULL HTML
        # ==========================================

        html = await page.content()

        Path(
            "debug.html"
        ).write_text(
            html,
            encoding="utf-8"
        )

        print("")
        print(
            "HTML disimpan: debug.html"
        )

        # ==========================================
        # SCREENSHOT
        # ==========================================

        await page.screenshot(
            path="pelindo.png",
            full_page=True
        )

        print(
            "Screenshot disimpan: pelindo.png"
        )

        print("")
        print("======================================")
        print("DIAGNOSTIC SELESAI")
        print("======================================")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
