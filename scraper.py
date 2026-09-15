import asyncio
import sys
import traceback
from pathlib import Path

from playwright.async_api import async_playwright


URL = "https://ibstpks.pelindo.co.id/webaccess/"


async def main():

    print("======================================")
    print("PELINDO SCRAPER TEST")
    print("======================================")

    browser = None

    try:

        # ==========================================
        # START PLAYWRIGHT
        # ==========================================

        print("")
        print("[1] Memulai Playwright...")

        async with async_playwright() as p:

            print("[OK] Playwright berhasil.")

            # ======================================
            # LAUNCH CHROMIUM
            # ======================================

            print("")
            print("[2] Menjalankan Chromium...")

            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            print("[OK] Chromium berhasil dijalankan.")

            # ======================================
            # CREATE PAGE
            # ======================================

            print("")
            print("[3] Membuat browser page...")

            page = await browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 900,
                }
            )

            print("[OK] Page berhasil dibuat.")

            # ======================================
            # OPEN WEBSITE
            # ======================================

            print("")
            print("[4] Membuka website Pelindo...")
            print(URL)

            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print("[OK] Website berhasil dibuka.")

            if response:
                print(
                    "HTTP STATUS:",
                    response.status
                )

            # ======================================
            # WAIT
            # ======================================

            print("")
            print("[5] Menunggu aplikasi Pelindo...")

            await page.wait_for_timeout(15000)

            print("[OK] Waktu tunggu selesai.")

            # ======================================
            # PAGE INFO
            # ======================================

            print("")
            print("======================================")
            print("PAGE INFORMATION")
            print("======================================")

            try:

                title = await page.title()

                print(
                    "TITLE:",
                    title
                )

            except Exception as e:

                print(
                    "Gagal membaca title:",
                    repr(e)
                )

            print(
                "URL:",
                page.url
            )

            # ======================================
            # BODY TEXT
            # ======================================

            print("")
            print("======================================")
            print("VISIBLE TEXT")
            print("======================================")

            try:

                body = page.locator("body")

                text = await body.inner_text()

                print(
                    text[:15000]
                )

            except Exception as e:

                print(
                    "Gagal membaca body:",
                    repr(e)
                )

            # ======================================
            # SECTION SEARCH
            # ======================================

            print("")
            print("======================================")
            print("SECTION SEARCH")
            print("======================================")

            keywords = [
                "Vessel Alongside",
                "Confirmed Vessel",
                "Open Stack",
                "Vessel Schedule",
                "Vessel History",
            ]

            for keyword in keywords:

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
                        min(count, 5)
                    ):

                        try:

                            element = locator.nth(i)

                            info = await element.evaluate(
                                """
                                el => ({
                                    tag: el.tagName,
                                    id: el.id,
                                    className: String(el.className),
                                    text: el.innerText || "",
                                    parentTag: el.parentElement
                                        ? el.parentElement.tagName
                                        : null,
                                    parentClass: el.parentElement
                                        ? String(el.parentElement.className)
                                        : null
                                })
                                """
                            )

                            print(
                                "ELEMENT:",
                                info
                            )

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

            # ======================================
            # TABLE
            # ======================================

            print("")
            print("======================================")
            print("TABLE INSPECTION")
            print("======================================")

            try:

                tables = page.locator("table")

                count = await tables.count()

                print(
                    "Jumlah table:",
                    count
                )

                for i in range(count):

                    print("")
                    print(
                        f"========== TABLE {i + 1} =========="
                    )

                    try:

                        text = await tables.nth(
                            i
                        ).inner_text()

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
                    "Table inspection gagal:",
                    repr(e)
                )

            # ======================================
            # BUTTON / LINK
            # ======================================

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

                        text = (
                            await elements.nth(i).inner_text()
                        ).strip()

                        if text:

                            print(
                                f"[{i}] {text[:300]}"
                            )

                    except Exception:
                        pass

            except Exception as e:

                print(
                    "Link/button inspection gagal:",
                    repr(e)
                )

            # ======================================
            # SAVE HTML
            # ======================================

            print("")
            print("======================================")
            print("SAVE HTML")
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
                    "[OK] debug.html berhasil dibuat."
                )

            except Exception as e:

                print(
                    "Gagal menyimpan HTML:",
                    repr(e)
                )

            # ======================================
            # SCREENSHOT
            # ======================================

            print("")
            print("======================================")
            print("SAVE SCREENSHOT")
            print("======================================")

            try:

                await page.screenshot(
                    path="pelindo.png",
                    full_page=True
                )

                print(
                    "[OK] pelindo.png berhasil dibuat."
                )

            except Exception as e:

                print(
                    "Gagal screenshot:",
                    repr(e)
                )

            print("")
            print("======================================")
            print("PELINDO TEST SELESAI")
            print("======================================")

    except Exception as e:

        print("")
        print("======================================")
        print("ERROR TERJADI")
        print("======================================")

        print(
            "TYPE:",
            type(e).__name__
        )

        print(
            "MESSAGE:",
            str(e)
        )

        print("")
        print("TRACEBACK:")
        traceback.print_exc()

        print("")
        print("======================================")
        print("SCRIPT TETAP SELESAI")
        print("======================================")

    finally:

        if browser:

            try:
                await browser.close()
                print("[OK] Browser ditutup.")
            except Exception:
                pass


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except Exception as e:

        print(
            "FATAL OUTER ERROR:",
            repr(e)
        )

    # Paksa exit code 0.
    # Kita sedang melakukan diagnostic,
    # bukan menjalankan scraper produksi.
    sys.exit(0)
