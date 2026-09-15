import asyncio
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError
)


URL = "https://ibstpks.pelindo.co.id/webaccess/"

MAX_RETRIES = 3
NAVIGATION_TIMEOUT = 120000
WAIT_AFTER_LOAD = 10000


async def open_pelindo(page):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[CONNECT] Percobaan {attempt}/{MAX_RETRIES}")

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT
            )

            print("[CONNECT] Pelindo berhasil dibuka.")
            return True

        except PlaywrightTimeoutError:
            print("[CONNECT] Navigation timeout.")

            try:
                body_text = await page.locator("body").inner_text(timeout=5000)

                if body_text.strip():
                    print("[CONNECT] Body tetap tersedia setelah timeout.")
                    return True
            except Exception:
                pass

        except Exception as e:
            print(f"[CONNECT] Error: {e}")

        if attempt < MAX_RETRIES:
            print("[CONNECT] Menunggu sebelum retry...")
            await page.wait_for_timeout(5000)

    return False


async def diagnose_history_popup(page):
    print()
    print("=" * 70)
    print("HISTORY POPUP CONTENT DIAGNOSTIC")
    print("=" * 70)

    # Cari History pertama pada td.vessel pertama
    history_url = await page.locator(
        "td.vessel a"
    ).evaluate_all("""
        els => els
            .map(a => ({
                text: (a.innerText || "").trim(),
                title: a.getAttribute("title"),
                dataUrl: a.getAttribute("data-url")
            }))
            .filter(x => x.text.includes("History"))
            .slice(0, 1)
    """)

    if not history_url:
        print("[ERROR] History button tidak ditemukan.")
        return

    item = history_url[0]

    print()
    print("[HISTORY TARGET]")
    print("TITLE   =", item["title"])
    print("DATA URL =", item["dataUrl"])

    # Cari link History berdasarkan title
    history_link = page.locator(
        f'td.vessel a[title="{item["title"]}"]'
    ).filter(has_text="History").first

    print()
    print("[1] Klik History...")

    try:
        await history_link.click(timeout=10000)
    except Exception as e:
        print("[CLICK ERROR]", e)

        # fallback: jalankan javascript klik
        try:
            await history_link.evaluate("el => el.click()")
            print("[CLICK] JavaScript click berhasil.")
        except Exception as e2:
            print("[CLICK ERROR 2]", e2)
            return

    await page.wait_for_timeout(3000)

    print()
    print("=" * 70)
    print("SETELAH HISTORY DIKLIK")
    print("=" * 70)

    print("[URL]", page.url)

    # ---------------------------------------------------------
    # 1. Cari iframe
    # ---------------------------------------------------------
    print()
    print("[2] CEK IFRAME")

    iframes = await page.locator("iframe").evaluate_all("""
        els => els.map((el, i) => ({
            index: i,
            id: el.id,
            name: el.name,
            src: el.getAttribute("src"),
            className: el.className,
            width: el.getAttribute("width"),
            height: el.getAttribute("height")
        }))
    """)

    print("Jumlah iframe:", len(iframes))

    for iframe in iframes:
        print()
        print("[IFRAME]", iframe)

    # ---------------------------------------------------------
    # 2. Cari elemen modal / thickbox
    # ---------------------------------------------------------
    print()
    print("[3] CEK MODAL / THICKBOX")

    modal_candidates = await page.locator(
        "#TB_window, #TB_ajaxContent, #TB_iframeContent, "
        ".thickbox, .modal, [role='dialog']"
    ).evaluate_all("""
        els => els.map((el, i) => ({
            index: i,
            tag: el.tagName,
            id: el.id,
            className: el.className,
            text: (el.innerText || "").trim().slice(0, 500),
            html: el.outerHTML.slice(0, 2000)
        }))
    """)

    print("Jumlah kandidat modal:", len(modal_candidates))

    for modal in modal_candidates:
        print()
        print("[MODAL]", modal["index"])
        print("TAG   =", modal["tag"])
        print("ID    =", modal["id"])
        print("CLASS =", modal["className"])
        print("TEXT  =", modal["text"])
        print("HTML  =", modal["html"])

    # ---------------------------------------------------------
    # 3. Ambil seluruh text halaman setelah popup
    # ---------------------------------------------------------
    print()
    print("[4] BODY TEXT SETELAH HISTORY")

    body_text = await page.locator("body").inner_text()

    print("-" * 70)
    print(body_text[-10000:])
    print("-" * 70)

    # ---------------------------------------------------------
    # 4. Inspect semua table yang muncul
    # ---------------------------------------------------------
    print()
    print("[5] CEK TABLE SETELAH HISTORY")

    tables = await page.locator("table").evaluate_all("""
        tables => tables.map((table, i) => ({
            index: i,
            id: table.id,
            className: table.className,
            rows: table.rows.length,
            text: (table.innerText || "").trim().slice(0, 5000),
            html: table.outerHTML.slice(0, 5000)
        }))
    """)

    print("Jumlah table:", len(tables))

    for table in tables:
        print()
        print("=" * 70)
        print("TABLE", table["index"])
        print("ID:", table["id"])
        print("CLASS:", table["className"])
        print("ROWS:", table["rows"])

        print()
        print("TEXT:")
        print(table["text"])

        print()
        print("HTML:")
        print(table["html"])

    # ---------------------------------------------------------
    # 5. Jika ada iframe, baca isi iframe
    # ---------------------------------------------------------
    print()
    print("[6] BACA ISI IFRAME")

    frames = page.frames

    print("Jumlah frame:", len(frames))

    for index, frame in enumerate(frames):
        print()
        print("=" * 70)
        print("FRAME", index)
        print("URL:", frame.url)
        print("=" * 70)

        try:
            text = await frame.locator("body").inner_text(timeout=5000)

            print(text[:10000])

        except Exception as e:
            print("[FRAME ERROR]", e)

        try:
            frame_tables = await frame.locator("table").evaluate_all("""
                tables => tables.map((table, i) => ({
                    index: i,
                    id: table.id,
                    className: table.className,
                    rows: table.rows.length,
                    text: (table.innerText || "").trim().slice(0, 5000)
                }))
            """)

            print()
            print("TABLE DI FRAME:", len(frame_tables))

            for table in frame_tables:
                print()
                print("[FRAME TABLE]", table)

        except Exception as e:
            print("[FRAME TABLE ERROR]", e)


async def main():
    print()
    print("=" * 70)
    print("PELINDO HISTORY POPUP DIAGNOSTIC")
    print("=" * 70)

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        page = await browser.new_page(
            viewport={
                "width": 1440,
                "height": 900
            }
        )

        page.set_default_timeout(15000)

        print()
        print("[1] Membuka Pelindo...")

        success = await open_pelindo(page)

        if not success:
            print("[ERROR] Gagal membuka Pelindo.")
            await browser.close()
            return

        print()
        print("[2] Menunggu data vessel...")

        await page.wait_for_timeout(WAIT_AFTER_LOAD)

        print()
        print("[3] Menjalankan diagnostic...")

        await diagnose_history_popup(page)

        await browser.close()

    print()
    print("=" * 70)
    print("DIAGNOSTIC SELESAI")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
