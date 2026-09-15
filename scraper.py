import asyncio
import json
import re
from datetime import datetime

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError
)


URL = "https://ibstpks.pelindo.co.id/webaccess/"

MAX_RETRIES = 3
NAVIGATION_TIMEOUT = 120000
WAIT_AFTER_LOAD = 10000


VESSEL_PATTERN = re.compile(
    r"^(.+?)\s*\(([^()]+)\)$"
)

DATE_PATTERN = re.compile(
    r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}"
)


def is_valid_vessel_block(block):
    """
    Memastikan kandidat merupakan blok vessel,
    bukan footer/contact information.
    """

    has_voyage = False

    for line in block[:6]:

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if line.startswith("Booking / Open / Actual"):
            continue

        if line.startswith("Open Stack"):
            continue

        if line.startswith("Closing Time"):
            continue

        has_voyage = True
        break

    if not has_voyage:
        return False

    operational_keywords = [
        "DOMESTIC",
        "INTERNATIONAL",
        "ETA :",
        "ETB :",
        "ETD :",
        "ATB :",
        "ATD :",
        "Open Stack :",
        "Closing Time :",
        "Booking / Open / Actual :"
    ]

    for line in block:

        for keyword in operational_keywords:

            if keyword in line:
                return True

    return False


def extract_voyage(block):

    for line in block[:6]:

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if line.startswith("Booking / Open / Actual"):
            continue

        if line.startswith("Open Stack"):
            continue

        if line.startswith("Closing Time"):
            continue

        return line

    return ""


def parse_vessels(lines):

    vessels = []

    for i, line in enumerate(lines):

        match = VESSEL_PATTERN.match(line)

        if not match:
            continue

        vessel_name = match.group(1).strip()
        vessel_code = match.group(2).strip()

        blocked_words = [
            "WA Hotline",
            "Telpon/Wa",
            "Support",
            "Contact",
            "Planner",
            "Customer Service"
        ]

        if any(
            word.lower() in vessel_name.lower()
            for word in blocked_words
        ):
            continue

        block = lines[i + 1:i + 25]

        if not is_valid_vessel_block(block):
            continue

        voyage = extract_voyage(block)

        if not voyage:
            continue

        eta = ""
        etb = ""
        etd = ""
        atb = ""
        atd = ""

        open_stack = ""
        closing_time = ""

        booking = ""
        open_qty = ""
        actual = ""

        for item in block:

            if item.startswith("ETA :"):

                eta = item.replace(
                    "ETA :",
                    ""
                ).strip()

            elif item.startswith("ETB :"):

                etb = item.replace(
                    "ETB :",
                    ""
                ).strip()

            elif item.startswith("ETD :"):

                etd = item.replace(
                    "ETD :",
                    ""
                ).strip()

            elif item.startswith("ATB :"):

                atb = item.replace(
                    "ATB :",
                    ""
                ).strip()

            elif item.startswith("ATD :"):

                atd = item.replace(
                    "ATD :",
                    ""
                ).strip()

            elif item.startswith("Open Stack :"):

                open_stack = item.replace(
                    "Open Stack :",
                    ""
                ).strip()

            elif item.startswith("Closing Time :"):

                closing_time = item.replace(
                    "Closing Time :",
                    ""
                ).strip()

            elif item.startswith(
                "Booking / Open / Actual :"
            ):

                raw = item.replace(
                    "Booking / Open / Actual :",
                    ""
                ).strip()

                values = raw.split("/")

                if len(values) >= 3:

                    booking = values[0].strip()
                    open_qty = values[1].strip()
                    actual = values[2].strip()

        vessel = {
            "vesselName": vessel_name,
            "vesselCode": vessel_code,
            "voyage": voyage,
            "eta": eta,
            "etb": etb,
            "etd": etd,
            "atb": atb,
            "atd": atd,
            "openStack": open_stack,
            "closingTime": closing_time,
            "booking": booking,
            "open": open_qty,
            "actual": actual
        }

        vessels.append(vessel)

        print(
            f"[FOUND] {vessel_name} | {voyage}"
        )

    return vessels


async def diagnose_dom(page):
    """
    Menganalisis struktur DOM Pelindo untuk menemukan
    section Vessel Alongside, Confirmed Vessel,
    Open Stack, Vessel Schedule, dan Vessel History.
    """

    print("")
    print("======================================")
    print("PELINDO DOM DIAGNOSTIC")
    print("======================================")

    section_names = [
        "Vessel Alongside",
        "Confirmed Vessel",
        "Open Stack",
        "Vessel Schedule",
        "Vessel History"
    ]

    for section_name in section_names:

        print("")
        print("--------------------------------------")
        print(f"SECTION: {section_name}")
        print("--------------------------------------")

        result = await page.evaluate(
            """
            (sectionName) => {

                const elements = [];

                const all = document.querySelectorAll("*");

                for (const el of all) {

                    const text = (el.innerText || "").trim();

                    if (!text) {
                        continue;
                    }

                    if (
                        text.toLowerCase().includes(
                            sectionName.toLowerCase()
                        )
                    ) {

                        const rect = el.getBoundingClientRect();

                        elements.push({
                            tag: el.tagName,
                            id: el.id || "",
                            className:
                                typeof el.className === "string"
                                    ? el.className
                                    : "",
                            text:
                                text.substring(0, 500),
                            childCount:
                                el.children.length,
                            width:
                                Math.round(rect.width),
                            height:
                                Math.round(rect.height)
                        });
                    }
                }

                return elements.slice(0, 20);
            }
            """,
            section_name
        )

        if not result:

            print(
                "[DOM] Tidak ditemukan elemen."
            )

            continue

        print(
            f"[DOM] Ditemukan {len(result)} kandidat elemen."
        )

        for index, item in enumerate(result, 1):

            print("")
            print(
                f"[{index}] TAG = {item['tag']}"
            )

            print(
                f"    ID = {item['id']}"
            )

            print(
                f"    CLASS = {item['className']}"
            )

            print(
                f"    CHILDREN = {item['childCount']}"
            )

            print(
                f"    SIZE = "
                f"{item['width']}x{item['height']}"
            )

            text_preview = (
                item["text"]
                .replace("\n", " | ")
            )

            print(
                f"    TEXT = {text_preview[:500]}"
            )

    # ==========================================
    # CARI TABLE
    # ==========================================

    print("")
    print("======================================")
    print("SEMUA TABLE DI HALAMAN")
    print("======================================")

    tables = await page.evaluate(
        """
        () => {

            return Array.from(
                document.querySelectorAll("table")
            ).map((table, index) => {

                const rect =
                    table.getBoundingClientRect();

                return {
                    index: index + 1,

                    id:
                        table.id || "",

                    className:
                        typeof table.className === "string"
                            ? table.className
                            : "",

                    rows:
                        table.querySelectorAll("tr").length,

                    columns:
                        table.querySelectorAll("tr:first-child th").length
                        ||
                        table.querySelectorAll("tr:first-child td").length,

                    text:
                        (table.innerText || "")
                            .trim()
                            .substring(0, 1000),

                    width:
                        Math.round(rect.width),

                    height:
                        Math.round(rect.height)
                };

            });

        }
        """
    )

    print(
        f"Jumlah TABLE: {len(tables)}"
    )

    for table in tables:

        print("")
        print(
            f"[TABLE {table['index']}]"
        )

        print(
            f"TAG = TABLE"
        )

        print(
            f"ID = {table['id']}"
        )

        print(
            f"CLASS = {table['className']}"
        )

        print(
            f"ROWS = {table['rows']}"
        )

        print(
            f"COLUMNS = {table['columns']}"
        )

        print(
            f"SIZE = "
            f"{table['width']}x{table['height']}"
        )

        text_preview = (
            table["text"]
            .replace("\n", " | ")
        )

        print(
            f"TEXT = {text_preview[:1000]}"
        )

    # ==========================================
    # CARI TEXT SECTION SECARA LEBIH SPESIFIK
    # ==========================================

    print("")
    print("======================================")
    print("SECTION TEXT MATCH")
    print("======================================")

    matches = await page.evaluate(
        """
        (sectionNames) => {

            const result = [];

            const walker =
                document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT
                );

            let node;

            while (
                node = walker.nextNode()
            ) {

                const value =
                    node.textContent.trim();

                if (!value) {
                    continue;
                }

                for (const name of sectionNames) {

                    if (
                        value.toLowerCase()
                            === name.toLowerCase()
                    ) {

                        const parent =
                            node.parentElement;

                        result.push({

                            section: name,

                            tag:
                                parent
                                    ? parent.tagName
                                    : "",

                            id:
                                parent
                                    ? parent.id || ""
                                    : "",

                            className:
                                parent &&
                                typeof parent.className === "string"
                                    ? parent.className
                                    : "",

                            parentHTML:
                                parent
                                    ? parent.outerHTML
                                        .substring(0, 2000)
                                    : ""
                        });
                    }
                }
            }

            return result;
        }
        """,
        section_names
    )

    if not matches:

        print(
            "[MATCH] Tidak ada exact text match."
        )

    else:

        for index, item in enumerate(
            matches,
            1
        ):

            print("")
            print(
                f"[MATCH {index}] "
                f"{item['section']}"
            )

            print(
                f"TAG = {item['tag']}"
            )

            print(
                f"ID = {item['id']}"
            )

            print(
                f"CLASS = {item['className']}"
            )

            print(
                "PARENT HTML:"
            )

            print(
                item["parentHTML"]
            )


async def open_pelindo(page):

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"[CONNECT] Percobaan "
            f"{attempt}/{MAX_RETRIES}"
        )

        try:

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT
            )

            print(
                "[CONNECT] Pelindo berhasil dibuka."
            )

            return True

        except PlaywrightTimeoutError:

            print(
                "[WARNING] Navigation timeout."
            )

            try:

                current_url = page.url

                print(
                    f"[CONNECT] URL saat ini: "
                    f"{current_url}"
                )

                body_count = await page.locator(
                    "body"
                ).count()

                if body_count > 0:

                    print(
                        "[CONNECT] Body halaman tersedia."
                    )

                    return True

            except Exception as check_error:

                print(
                    "[WARNING] Pemeriksaan halaman gagal:",
                    check_error
                )

            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 5

                print(
                    f"[CONNECT] Menunggu "
                    f"{wait_seconds} detik "
                    "sebelum retry..."
                )

                await page.wait_for_timeout(
                    wait_seconds * 1000
                )

        except Exception as error:

            print(
                f"[WARNING] Koneksi gagal: {error}"
            )

            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 5

                print(
                    f"[CONNECT] Retry dalam "
                    f"{wait_seconds} detik..."
                )

                await page.wait_for_timeout(
                    wait_seconds * 1000
                )

    return False


async def main():

    print("======================================")
    print("PELINDO LIVE SCRAPER - DOM DIAGNOSTIC")
    print("======================================")

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

        # ============================================
        # BUKA PELINDO
        # ============================================

        print("[1] Membuka Pelindo...")

        success = await open_pelindo(page)

        if not success:

            await browser.close()

            raise RuntimeError(
                "Pelindo tidak dapat diakses setelah "
                f"{MAX_RETRIES} percobaan."
            )

        # ============================================
        # TUNGGU DATA JAVASCRIPT
        # ============================================

        print(
            "[2] Menunggu data vessel..."
        )

        await page.wait_for_timeout(
            WAIT_AFTER_LOAD
        )

        # ============================================
        # BACA BODY
        # ============================================

        print(
            "[3] Membaca data halaman..."
        )

        text = await page.locator(
            "body"
        ).inner_text()

        if not text.strip():

            await browser.close()

            raise RuntimeError(
                "Halaman Pelindo terbuka tetapi "
                "tidak menghasilkan text."
            )

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        print(
            f"[4] Total baris halaman: "
            f"{len(lines)}"
        )

        # ============================================
        # DIAGNOSTIC DOM
        # ============================================

        await diagnose_dom(page)

        # ============================================
        # PARSER LAMA TETAP DIJALANKAN
        # ============================================

        print("")
        print("======================================")
        print("PARSER LAMA")
        print("======================================")

        vessels = parse_vessels(lines)

        print("")
        print("======================================")
        print("HASIL PARSER LAMA")
        print("======================================")

        print(
            "Jumlah vessel:",
            len(vessels)
        )

        if len(vessels) == 0:

            await browser.close()

            raise RuntimeError(
                "Pelindo berhasil dibuka tetapi "
                "tidak ada vessel valid ditemukan."
            )

        # ============================================
        # JANGAN UBAH DATA PRODUKSI
        # ============================================

        print("")
        print("======================================")
        print("DIAGNOSTIC SELESAI")
        print("======================================")

        print(
            "Parser lama berhasil membaca:",
            len(vessels),
            "vessel"
        )

        print("")
        print(
            "Belum membuat perubahan pada data.json."
        )

        print(
            "Kirimkan output bagian "
            "'PELINDO DOM DIAGNOSTIC' "
            "kepada saya."
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
