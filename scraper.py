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

        # ==========================================
        # OPEN WEBSITE
        # ==========================================

        print("======================================")
        print("MEMBUKA WEBSITE PELINDO")
        print("======================================")

        try:

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print("Website berhasil dibuka.")

        except Exception as e:

            print("GAGAL membuka website:")
            print(repr(e))

            await browser.close()
            return

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

        try:
            print("TITLE :", await page.title())
        except Exception as e:
            print("Gagal membaca title:", repr(e))

        try:
            print("URL   :", page.url)
        except Exception as e:
            print("Gagal membaca URL:", repr(e))

        # ==========================================
        # VISIBLE TEXT
        # ==========================================

        print("")
        print("======================================")
        print("VISIBLE TEXT CHECK")
        print("======================================")

        try:

            body_text = await page.locator("body").inner_text()

            print(
                body_text[:10000]
            )

        except Exception as e:

            print(
                "Gagal membaca body:",
                repr(e)
            )

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

            try:

                locator = page.get_by_text(
                    keyword,
                    exact=False
                )

                count = await locator.count()

                print(
                    "Element ditemukan:",
                    count
                )

                for i in range(
                    min(count, 10)
                ):

                    element = locator.nth(i)

                    try:

                        info = await element.evaluate(
                            """
                            el => {

                                const parent =
                                    el.parentElement;

                                return {

                                    tag:
                                        el.tagName,

                                    id:
                                        el.id,

                                    className:
                                        String(
                                            el.className
                                        ),

                                    text:
                                        el.innerText || "",

                                    parentTag:
                                        parent
                                            ? parent.tagName
                                            : null,

                                    parentId:
                                        parent
                                            ? parent.id
                                            : null,

                                    parentClass:
                                        parent
                                            ? String(
                                                parent.className
                                              )
                                            : null,

                                    parentText:
                                        parent
                                            ? (
                                                parent.innerText
                                                || ""
                                              )
                                            : null
                                };
                            }
                            """
                        )

                        print("")
                        print("ELEMENT:")
                        print(info)

                    except Exception as e:

                        print(
                            "Gagal inspect element:",
                            repr(e)
                        )

            except Exception as e:

                print(
                    "Gagal mencari keyword:",
                    repr(e)
                )

        # ==========================================
        # ALL TABLES
        # ==========================================

        print("")
        print("======================================")
        print("TABLE INSPECTION")
        print("======================================")

        try:

            tables = page.locator("table")

            table_count = await tables.count()

            print(
                "Jumlah table:",
                table_count
            )

            for i in range(table_count):

                print("")
                print(
                    f"========== TABLE {i + 1} =========="
                )

                try:

                    table = tables.nth(i)

                    text = await table.inner_text()

                    print(
                        text[:5000]
                    )

                except Exception as e:

                    print(
                        "Gagal membaca table:",
                        repr(e)
                    )

        except Exception as e:

            print(
                "Gagal melakukan table inspection:",
                repr(e)
            )

        # ==========================================
        # POSSIBLE CARDS
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

            print("")
            print(
                "--------------------------------------"
            )

            print(
                "SELECTOR:",
                selector
            )

            print(
                "--------------------------------------"
            )

            try:

                locator = page.locator(
                    selector
                )

                count = await locator.count()

                print(
                    "Jumlah:",
                    count
                )

                for i in range(
                    min(count, 20)
                ):

                    try:

                        element = locator.nth(i)

                        text = await element.inner_text()

                        if text.strip():

                            print("")
                            print(
                                f"[{selector} #{i}]"
                            )

                            print(
                                text[:3000]
                            )

                    except Exception as e:

                        print(
                            "Gagal membaca element:",
                            repr(e)
                        )

            except Exception as e:

                print(
                    "Gagal selector:",
                    repr(e)
                )

        # ==========================================
        # LINKS
        # ==========================================

        print("")
        print("======================================")
        print("LINK / BUTTON INSPECTION")
        print("======================================")

        try:

            elements = page.locator(
                "a, button"
            )

            count = await elements.count()

            print(
                "Jumlah link/button:",
                count
            )

            for i in range(
                min(count, 100)
            ):

                try:

                    element = elements.nth(i)

                    text = (
                        await element.inner_text()
                    ).strip()

                    if text:

                        print(
                            f"[{i}] {text[:300]}"
                        )

                except Exception:
                    pass

        except Exception as e:

            print(
                "Gagal membaca link/button:",
                repr(e)
            )

        # ==========================================
        # SAVE HTML
        # ==========================================

        print("")
        print("======================================")
        print("MENYIMPAN HTML")
        print("======================================")

        try:

            html = await page.content()

            Path(
                "debug.html"
            ).write_text(
                html,
                encoding="utf-8"
            )

            print(
                "HTML berhasil disimpan: debug.html"
            )

        except Exception as e:

            print(
                "Gagal menyimpan HTML:",
                repr(e)
            )

        # ==========================================
        # SCREENSHOT
        # ==========================================

        print("")
        print("======================================")
        print("MENYIMPAN SCREENSHOT")
        print("======================================")

        try:

            await page.screenshot(
                path="pelindo.png",
                full_page=True
            )

            print(
                "Screenshot berhasil disimpan."
            )

        except Exception as e:

            print(
                "Gagal screenshot:",
                repr(e)
            )

        # ==========================================
        # FINISHED
        # ==========================================

        print("")
        print("======================================")
        print("DIAGNOSTIC SELESAI")
        print("======================================")

        await browser.close()


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except Exception as e:

        print("")
        print("======================================")
        print("FATAL ERROR")
        print("======================================")

        print(
            repr(e)
        )

        # Jangan raise lagi.
        # Tujuannya agar log diagnostic tetap terbaca.
