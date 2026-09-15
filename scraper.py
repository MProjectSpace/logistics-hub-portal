import asyncio
import json
import re
from datetime import datetime

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError
)


# ============================================================
# CONFIG
# ============================================================

URL = "https://ibstpks.pelindo.co.id/webaccess/"

MAX_RETRIES = 3
NAVIGATION_TIMEOUT = 120000
WAIT_AFTER_LOAD = 10000


# ============================================================
# PATTERN
# ============================================================

VESSEL_PATTERN = re.compile(
    r"^(.+?)\s*\(([^()]+)\)$"
)

DATE_PATTERN = re.compile(
    r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}"
)


# ============================================================
# SECTION
# ============================================================

SECTION_NAMES = [
    "Vessel Alongside",
    "Confirmed Vessel",
    "Open Stack",
    "Vessel Schedule",
    "Vessel History"
]


SECTION_KEYS = {
    "Vessel Alongside": "vesselAlongside",
    "Confirmed Vessel": "confirmedVessel",
    "Open Stack": "openStack",
    "Vessel Schedule": "vesselSchedule",
    "Vessel History": "vesselHistory"
}


# Prioritas jika EXACT voyage yang sama
# ditemukan di lebih dari satu section.
SECTION_PRIORITY = {
    "Vessel Alongside": 1,
    "Confirmed Vessel": 2,
    "Open Stack": 3,
    "Vessel Schedule": 4,
    "Vessel History": 5
}


# ============================================================
# NORMALIZE
# ============================================================

def normalize(value):
    """
    Normalisasi text untuk kebutuhan perbandingan.

    Contoh:

    'SINAR BINTAN'
    'Sinar   Bintan'

    menjadi:

    'SINAR BINTAN'
    """

    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip().upper()


def vessel_key(vessel):
    """
    IDENTITAS UNIQUE VESSEL.

    Nama vessel SAJA tidak cukup.

    Contoh:

    SINAR BINTAN + 951S / 951N
    SINAR BINTAN + 952S / 952N

    adalah dua voyage berbeda.
    """

    name = normalize(
        vessel.get("vesselName")
    )

    voyage = normalize(
        vessel.get("voyage")
    )

    return f"{name}|{voyage}"


# ============================================================
# SECTION DETECTION
# ============================================================

def detect_sections(lines):
    """
    Mendeteksi batas masing-masing section berdasarkan
    heading asli halaman.

    Hasil:

    {
        "Vessel Alongside": [...],
        "Confirmed Vessel": [...],
        "Open Stack": [...],
        "Vessel Schedule": [...],
        "Vessel History": [...]
    }
    """

    sections = {
        section: []
        for section in SECTION_NAMES
    }

    current_section = None

    for line in lines:

        clean = line.strip()

        # --------------------------------------------
        # Apakah line merupakan heading section?
        # --------------------------------------------

        if clean in SECTION_NAMES:

            current_section = clean

            continue

        # --------------------------------------------
        # Simpan hanya jika sedang berada
        # di dalam section yang dikenal
        # --------------------------------------------

        if current_section:

            sections[current_section].append(
                clean
            )

    return sections


# ============================================================
# VALID VESSEL BLOCK
# ============================================================

def is_valid_vessel_block(block):
    """
    Memastikan blok benar-benar merupakan vessel.
    """

    if not block:
        return False

    # --------------------------------------------
    # Harus punya voyage
    # --------------------------------------------

    has_voyage = False

    for line in block[:8]:

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if line.startswith(
            "Booking / Open / Actual"
        ):
            continue

        if line.startswith(
            "Open Stack"
        ):
            continue

        if line.startswith(
            "Closing Time"
        ):
            continue

        has_voyage = True
        break

    if not has_voyage:
        return False

    # --------------------------------------------
    # Indikator operational
    # --------------------------------------------

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


# ============================================================
# VOYAGE
# ============================================================

def extract_voyage(block):
    """
    Mencari voyage dari bagian awal block.
    """

    for line in block[:8]:

        if "/" not in line:
            continue

        if DATE_PATTERN.search(line):
            continue

        if line.startswith(
            "Booking / Open / Actual"
        ):
            continue

        if line.startswith(
            "Open Stack"
        ):
            continue

        if line.startswith(
            "Closing Time"
        ):
            continue

        return line.strip()

    return ""


# ============================================================
# FIELD PARSER
# ============================================================

def parse_vessel_block(
    vessel_name,
    vessel_code,
    block,
    section
):
    """
    Mengubah satu block vessel menjadi object.
    """

    if not is_valid_vessel_block(block):
        return None

    voyage = extract_voyage(block)

    if not voyage:
        return None

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

    # ========================================================
    # FIELD
    # ========================================================

    for item in block:

        item = item.strip()

        if item.startswith("ETA :"):

            eta = item.replace(
                "ETA :",
                "",
                1
            ).strip()

        elif item.startswith("ETB :"):

            etb = item.replace(
                "ETB :",
                "",
                1
            ).strip()

        elif item.startswith("ETD :"):

            etd = item.replace(
                "ETD :",
                "",
                1
            ).strip()

        elif item.startswith("ATB :"):

            atb = item.replace(
                "ATB :",
                "",
                1
            ).strip()

        elif item.startswith("ATD :"):

            atd = item.replace(
                "ATD :",
                "",
                1
            ).strip()

        elif item.startswith("Open Stack :"):

            open_stack = item.replace(
                "Open Stack :",
                "",
                1
            ).strip()

        elif item.startswith("Closing Time :"):

            closing_time = item.replace(
                "Closing Time :",
                "",
                1
            ).strip()

        elif item.startswith(
            "Booking / Open / Actual :"
        ):

            raw = item.replace(
                "Booking / Open / Actual :",
                "",
                1
            ).strip()

            values = [
                x.strip()
                for x in raw.split("/")
            ]

            if len(values) >= 3:

                booking = values[0]
                open_qty = values[1]
                actual = values[2]

    # ========================================================
    # RESULT
    # ========================================================

    vessel = {

        # Identitas
        "vesselName": vessel_name,
        "vesselCode": vessel_code,
        "voyage": voyage,

        # SOURCE SECTION
        "section": section,

        # Schedule / operation
        "eta": eta,
        "etb": etb,
        "etd": etd,
        "atb": atb,
        "atd": atd,

        # Open stack
        "openStack": open_stack,
        "closingTime": closing_time,

        # Quantity
        "booking": booking,
        "open": open_qty,
        "actual": actual
    }

    return vessel


# ============================================================
# PARSE SECTION
# ============================================================

def parse_section(lines, section):
    """
    Parse vessel hanya dari SATU section.

    Tidak ada lagi classification berdasarkan ATB/ETB/Open Stack.
    """

    vessels = []

    i = 0

    while i < len(lines):

        line = lines[i].strip()

        match = VESSEL_PATTERN.match(line)

        if not match:

            i += 1
            continue

        vessel_name = match.group(1).strip()
        vessel_code = match.group(2).strip()

        # ====================================================
        # FILTER NON-VESSEL
        # ====================================================

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

            i += 1

            continue

        # ====================================================
        # CARI END BLOCK
        #
        # Block berhenti ketika menemukan vessel berikutnya.
        # ====================================================

        j = i + 1

        while j < len(lines):

            next_line = lines[j].strip()

            next_match = VESSEL_PATTERN.match(
                next_line
            )

            if next_match:

                break

            j += 1

        block = lines[i + 1:j]

        # ====================================================
        # PARSE
        # ====================================================

        vessel = parse_vessel_block(
            vessel_name=vessel_name,
            vessel_code=vessel_code,
            block=block,
            section=section
        )

        if vessel:

            vessels.append(vessel)

            print(
                f"[FOUND] "
                f"[{section}] "
                f"{vessel_name} | "
                f"{voyage if (voyage := vessel['voyage']) else '-'}"
            )

        i = j

    return vessels


# ============================================================
# DEDUPLICATE WITHIN SECTION
# ============================================================

def deduplicate_section(vessels):
    """
    Menghilangkan duplicate EXACT voyage
    dalam satu section.

    IDENTITAS:

        vesselName + voyage

    BUKAN:

        vesselName saja
    """

    result = []
    seen = set()

    for vessel in vessels:

        key = vessel_key(vessel)

        if key in seen:

            print(
                f"[DUPLICATE] "
                f"{vessel['vesselName']} | "
                f"{vessel['voyage']}"
            )

            continue

        seen.add(key)

        result.append(vessel)

    return result


# ============================================================
# DEDUPLICATE ACROSS SECTION
# ============================================================

def deduplicate_across_sections(
    section_data
):
    """
    Jika EXACT voyage yang sama muncul di lebih dari
    satu section, hanya pertahankan section dengan
    prioritas lebih tinggi.

    Contoh:

        SINAR BINTAN | 951S / 951N
        SINAR BINTAN | 952S / 952N

    tetap dua record.

    Tetapi:

        SINAR BINTAN | 951S / 951N
        SINAR BINTAN | 951S / 951N

    hanya satu record.
    """

    selected = {}

    for section in SECTION_NAMES:

        vessels = section_data.get(
            section,
            []
        )

        for vessel in vessels:

            key = vessel_key(vessel)

            current = selected.get(key)

            if current is None:

                selected[key] = vessel

                continue

            current_priority = SECTION_PRIORITY.get(
                current["section"],
                999
            )

            new_priority = SECTION_PRIORITY.get(
                vessel["section"],
                999
            )

            if new_priority < current_priority:

                print(
                    f"[CROSS SECTION DUPLICATE] "
                    f"{vessel['vesselName']} | "
                    f"{vessel['voyage']} "
                    f"-> {current['section']} "
                    f"replaced by {vessel['section']}"
                )

                selected[key] = vessel

            else:

                print(
                    f"[CROSS SECTION DUPLICATE] "
                    f"{vessel['vesselName']} | "
                    f"{vessel['voyage']} "
                    f"-> keep {current['section']}"
                )

    # ========================================================
    # KEMBALIKAN KE SECTION ASLI
    # ========================================================

    result = {
        section: []
        for section in SECTION_NAMES
    }

    for vessel in selected.values():

        result[
            vessel["section"]
        ].append(vessel)

    return result


# ============================================================
# BUILD DATA
# ============================================================

def build_data_from_sections(
    section_data
):
    """
    Membentuk JSON final.

    Tidak ada lagi:

        if ATB -> Alongside
        if ETB -> Confirmed
        if OpenStack -> Open Stack

    Karena section sudah ditentukan dari halaman.
    """

    # ========================================================
    # DEDUP DALAM SECTION
    # ========================================================

    cleaned = {}

    for section in SECTION_NAMES:

        cleaned[section] = deduplicate_section(
            section_data.get(
                section,
                []
            )
        )

    # ========================================================
    # DEDUP ANTAR SECTION
    # ========================================================

    cleaned = deduplicate_across_sections(
        cleaned
    )

    # ========================================================
    # REMOVE INTERNAL SECTION FIELD
    # ========================================================

    def clean_vessel(vessel):

        result = dict(vessel)

        result.pop(
            "section",
            None
        )

        return result

    # ========================================================
    # FINAL
    # ========================================================

    return {

        "lastUpdated":
            datetime.now().strftime(
                "%d/%m/%Y %H:%M"
            ),

        "source":
            URL,

        "vesselAlongside": [
            clean_vessel(v)
            for v in cleaned[
                "Vessel Alongside"
            ]
        ],

        "confirmedVessel": [
            clean_vessel(v)
            for v in cleaned[
                "Confirmed Vessel"
            ]
        ],

        "openStack": [
            clean_vessel(v)
            for v in cleaned[
                "Open Stack"
            ]
        ],

        "vesselSchedule": [
            clean_vessel(v)
            for v in cleaned[
                "Vessel Schedule"
            ]
        ],

        "vesselHistory": [
            clean_vessel(v)
            for v in cleaned[
                "Vessel History"
            ]
        ],

        # ----------------------------------------------------
        # ALL VESSELS
        #
        # Ini tetap disediakan untuk debugging / kebutuhan
        # lain. Berisi seluruh voyage UNIQUE.
        # ----------------------------------------------------

        "allVessels": [
            clean_vessel(v)
            for section in SECTION_NAMES
            for v in cleaned[section]
        ]
    }


# ============================================================
# OPEN PELINDO
# ============================================================

async def open_pelindo(page):

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"[CONNECT] "
            f"Percobaan {attempt}/{MAX_RETRIES}"
        )

        try:

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT
            )

            print(
                "[CONNECT] "
                "Pelindo berhasil dibuka."
            )

            return True

        except PlaywrightTimeoutError:

            print(
                "[WARNING] "
                "Navigation timeout."
            )

            try:

                current_url = page.url

                print(
                    f"[CONNECT] "
                    f"URL saat ini: {current_url}"
                )

                body_count = await page.locator(
                    "body"
                ).count()

                if body_count > 0:

                    print(
                        "[CONNECT] "
                        "Body halaman tersedia."
                    )

                    return True

            except Exception as check_error:

                print(
                    "[WARNING] "
                    "Pemeriksaan halaman gagal:",
                    check_error
                )

            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 5

                print(
                    f"[CONNECT] "
                    f"Menunggu {wait_seconds} detik "
                    "sebelum retry..."
                )

                await page.wait_for_timeout(
                    wait_seconds * 1000
                )

        except Exception as error:

            print(
                f"[WARNING] "
                f"Koneksi gagal: {error}"
            )

            if attempt < MAX_RETRIES:

                wait_seconds = attempt * 5

                print(
                    f"[CONNECT] "
                    f"Retry dalam {wait_seconds} detik..."
                )

                await page.wait_for_timeout(
                    wait_seconds * 1000
                )

    return False


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "======================================"
    )

    print(
        "PELINDO LIVE SCRAPER"
    )

    print(
        "SECTION BASED VERSION"
    )

    print(
        "======================================"
    )

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

        # ====================================================
        # OPEN
        # ====================================================

        print(
            "[1] Membuka Pelindo..."
        )

        success = await open_pelindo(
            page
        )

        if not success:

            await browser.close()

            raise RuntimeError(
                "Pelindo tidak dapat diakses "
                "setelah beberapa percobaan."
            )

        # ====================================================
        # WAIT
        # ====================================================

        print(
            "[2] Menunggu data vessel..."
        )

        await page.wait_for_timeout(
            WAIT_AFTER_LOAD
        )

        # ====================================================
        # READ BODY
        # ====================================================

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

        # ====================================================
        # DETECT SECTION
        # ====================================================

        print(
            "[5] Mendeteksi section..."
        )

        sections = detect_sections(
            lines
        )

        print("")

        for section in SECTION_NAMES:

            print(
                f"[SECTION] "
                f"{section}: "
                f"{len(sections[section])} lines"
            )

        # ====================================================
        # PARSE EACH SECTION
        # ====================================================

        print("")
        print(
            "[6] Parsing vessel berdasarkan section..."
        )

        section_data = {}

        for section in SECTION_NAMES:

            print("")
            print(
                f"========== {section} =========="
            )

            section_data[section] = parse_section(
                sections[section],
                section
            )

        # ====================================================
        # VALIDATION
        # ====================================================

        total_found = sum(
            len(vessels)
            for vessels in section_data.values()
        )

        print("")
        print(
            "======================================"
        )

        print(
            "HASIL PARSING PER SECTION"
        )

        print(
            "======================================"
        )

        for section in SECTION_NAMES:

            print(
                f"{section}: "
                f"{len(section_data[section])}"
            )

        print(
            f"TOTAL: {total_found}"
        )

        if total_found == 0:

            await browser.close()

            raise RuntimeError(
                "Tidak ada vessel valid ditemukan."
            )

        # ====================================================
        # BUILD FINAL DATA
        # ====================================================

        print("")
        print(
            "[7] Deduplicate + membuat data JSON..."
        )

        data = build_data_from_sections(
            section_data
        )

        # ====================================================
        # SAVE
        # ====================================================

        with open(
            "data.json",
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        # ====================================================
        # FINAL REPORT
        # ====================================================

        print("")
        print(
            "======================================"
        )

        print(
            "DATA.JSON BERHASIL DIBUAT"
        )

        print(
            "======================================"
        )

        print(
            "Vessel Alongside:",
            len(
                data["vesselAlongside"]
            )
        )

        print(
            "Confirmed Vessel:",
            len(
                data["confirmedVessel"]
            )
        )

        print(
            "Open Stack:",
            len(
                data["openStack"]
            )
        )

        print(
            "Vessel Schedule:",
            len(
                data["vesselSchedule"]
            )
        )

        print(
            "Vessel History:",
            len(
                data["vesselHistory"]
            )
        )

        print(
            "All Unique Voyages:",
            len(
                data["allVessels"]
            )
        )

        print("")
        print(
            "=== SCRAPER SELESAI ==="
        )

        await browser.close()


if __name__ == "__main__":

    asyncio.run(main())
