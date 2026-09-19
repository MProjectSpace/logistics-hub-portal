#!/usr/bin/env python3

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================
# CONFIG
# ============================================================

URL = "https://ibstpks.pelindo.co.id/webaccess/"
OUTPUT_FILE = Path("data.json")

NAVIGATION_TIMEOUT = 120000
WAIT_AFTER_LOAD = 5000

TZ = ZoneInfo("Asia/Jakarta")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


# ============================================================
# UTILITY
# ============================================================

def clean_text(value):
    """
    Membersihkan whitespace berlebih.
    """
    if value is None:
        return ""

    return " ".join(str(value).split())


def clean_record(record):
    """
    Membersihkan string-string dari object WA_BOARD
    tanpa menghilangkan field asli.
    """
    if not isinstance(record, dict):
        return {}

    result = {}

    for key, value in record.items():
        if isinstance(value, str):
            result[key] = clean_text(value)
        else:
            result[key] = value

    return result


def now_jakarta():
    return datetime.now(TZ)


def iso_now():
    return now_jakarta().isoformat(timespec="seconds")


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_record(record, category):
    """
    Mengubah object WA_BOARD menjadi struktur JSON yang
    kompatibel dengan dashboard lama.

    Field asli WA_BOARD tetap dipertahankan.
    """

    record = clean_record(record)

    name = clean_text(record.get("name"))
    vessel_id = clean_text(record.get("id"))

    voyage_in = clean_text(record.get("voyageIn"))
    voyage_out = clean_text(record.get("voyageOut"))

    agent = clean_text(record.get("agent"))
    customer = clean_text(record.get("customer"))
    principal = clean_text(record.get("principal"))

    oi = clean_text(record.get("oi"))
    mv_status = clean_text(record.get("mvSts"))

    # --------------------------------------------------------
    # Agent / shipping line
    # --------------------------------------------------------

    shipping_line = (
        customer
        or principal
        or agent
        or ""
    )

    # --------------------------------------------------------
    # Common time fields
    # --------------------------------------------------------

    eta = clean_text(
        record.get("eta")
        or record.get("timeArrival")
    )

    etb = clean_text(
        record.get("estBerthTs")
    )

    etd = clean_text(
        record.get("estDepTs")
    )

    atb = clean_text(
        record.get("actBerthTs")
    )

    atd = clean_text(
        record.get("actDepTs")
    )

    # --------------------------------------------------------
    # Schedule has ETA explicitly.
    # --------------------------------------------------------

    if category == "schedule":
        eta = clean_text(record.get("eta"))
        etb = clean_text(record.get("estBerthTs"))
        etd = clean_text(record.get("estDepTs"))

    # --------------------------------------------------------
    # Alongside
    # --------------------------------------------------------

    if category == "alongside":
        atb = clean_text(record.get("actBerthTs"))
        etd = clean_text(record.get("estDepTs"))

    # --------------------------------------------------------
    # Confirmed / Open Stack
    # --------------------------------------------------------

    if category in ("confirmed", "openStack"):
        eta = clean_text(record.get("timeArrival"))
        etb = clean_text(record.get("estBerthTs"))
        etd = clean_text(record.get("estDepTs"))

    # --------------------------------------------------------
    # History
    # --------------------------------------------------------

    if category == "history":
        etb = clean_text(record.get("estBerthTs"))
        atb = clean_text(record.get("actBerthTs"))
        atd = clean_text(record.get("actDepTs"))

    normalized = {
        # ----------------------------------------------------
        # Existing dashboard-compatible fields
        # ----------------------------------------------------

        "vesselName": name,
        "vesselCode": vessel_id,

        "voyage": (
            f"{voyage_in} / {voyage_out}"
            if voyage_in or voyage_out
            else ""
        ),

        "voyageIn": voyage_in,
        "voyageOut": voyage_out,

        "shippingLine": shipping_line,
        "agent": agent,
        "customer": customer,
        "principal": principal,

        "type": oi,

        "eta": eta,
        "etb": etb,
        "atb": atb,
        "etd": etd,
        "atd": atd,

        "openStack": clean_text(
            record.get("availableTs")
        ),

        "closingTime": clean_text(
            record.get("recvCtrCutoffTs")
        ),

        "booking": record.get("bkgExport", 0) or 0,
        "open": record.get("bkgOpen", 0) or 0,
        "actual": record.get("joExport", 0) or 0,

        "export": record.get("exportBox", 0) or 0,
        "exportTeus": record.get("exportTeus", 0) or 0,

        "import": record.get("importBox", 0) or 0,
        "importTeus": record.get("importTeus", 0) or 0,

        "vesId": vessel_id,

        "detailUrl": (
            f"LandingData?do=load_detail&mode=public&vesId={vessel_id}"
            if vessel_id
            else ""
        ),

        "historyUrl": (
            f"LandingData?do=load_sched_audit&mode=public&vesId={vessel_id}"
            if vessel_id
            else ""
        ),

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        "category": category,
        "status": mv_status,

        # ----------------------------------------------------
        # Additional useful fields
        # ----------------------------------------------------

        "serviceName": clean_text(
            record.get("serviceName")
        ),

        "berthNo": clean_text(
            record.get("berthNo")
        ),

        "callSign": clean_text(
            record.get("callSign")
        ),

        "arrival": clean_text(
            record.get("arrival")
        ),

        "timeArrival": clean_text(
            record.get("timeArrival")
        ),

        "availableTs": clean_text(
            record.get("availableTs")
        ),

        "recvCtrCutoffTs": clean_text(
            record.get("recvCtrCutoffTs")
        ),

        "cutoffCtr": clean_text(
            record.get("cutoffCtr")
        ),

        "openStackYn": clean_text(
            record.get("openStackYn")
        ),

        "onWindowsFlag": clean_text(
            record.get("onWindowsFlag")
        ),

        # ISO timestamps
        "estBerthingTsISO": record.get(
            "estBerthingTsISO"
        ),

        "estDepartureTsISO": record.get(
            "estDepartureTsISO"
        ),

        "actBerthingTsISO": record.get(
            "actBerthingTsISO"
        ),

        "actDepartureTsISO": record.get(
            "actDepartureTsISO"
        ),

        # Schedule-specific
        "feederDirect": clean_text(
            record.get("feederDirect")
        ),

        "bkgBoxes": record.get("bkgBoxes", 0) or 0,
        "bkgTeus": record.get("bkgTeus", 0) or 0,

        # Raw status
        "mvSts": mv_status,
    }

    # --------------------------------------------------------
    # Keep original WA_BOARD fields too.
    #
    # This makes future dashboard changes easier because
    # we don't need to modify scraper just to expose a field.
    # --------------------------------------------------------

    normalized["raw"] = record

    return normalized


# ============================================================
# DEDUPLICATION
# ============================================================

def record_key(record):
    """
    Identitas vessel call.

    Jangan hanya menggunakan vessel ID karena:
    1. Schedule tidak memiliki ID.
    2. Vessel yang sama bisa mempunyai voyage berbeda.

    Contoh:
        SINAR BINTAN | 951S | 951N
        SINAR BINTAN | 952S | 952N

    harus dianggap berbeda.
    """

    name = clean_text(
        record.get("vesselName")
        or record.get("name")
    ).upper()

    vessel_id = clean_text(
        record.get("vesselCode")
        or record.get("id")
    ).upper()

    voyage_in = clean_text(
        record.get("voyageIn")
    ).upper()

    voyage_out = clean_text(
        record.get("voyageOut")
    ).upper()

    return (
        name,
        vessel_id,
        voyage_in,
        voyage_out,
    )


def deduplicate(records):
    """
    Deduplicate tanpa mencampur voyage.
    """

    result = []
    seen = set()

    for record in records:
        key = record_key(record)

        if key in seen:
            continue

        seen.add(key)
        result.append(record)

    return result


# ============================================================
# BOARD EXTRACTION
# ============================================================

async def extract_wa_board(page):
    """
    Mengambil window.WA_BOARD langsung dari browser.

    Ini adalah sumber data utama halaman Pelindo baru.
    """

    logging.info("Reading window.WA_BOARD...")

    board = await page.evaluate(
        """
        () => {
            if (!window.WA_BOARD) {
                return null;
            }

            return window.WA_BOARD;
        }
        """
    )

    if not board:
        raise RuntimeError(
            "window.WA_BOARD tidak ditemukan."
        )

    if not isinstance(board, dict):
        raise RuntimeError(
            "window.WA_BOARD bukan object/dictionary."
        )

    return board


# ============================================================
# VALIDATION
# ============================================================

def validate_board(board):
    """
    Validasi supaya scraper tidak menghasilkan data kosong
    ketika struktur Pelindo berubah atau gagal load.
    """

    required_sections = [
        "alongside",
        "confirmed",
        "openStack",
        "schedule",
        "history",
    ]

    missing = [
        key
        for key in required_sections
        if key not in board
    ]

    if missing:
        raise RuntimeError(
            "WA_BOARD kehilangan section: "
            + ", ".join(missing)
        )

    for key in required_sections:
        if not isinstance(board[key], list):
            raise RuntimeError(
                f"WA_BOARD.{key} bukan array."
            )


# ============================================================
# BUILD DATA
# ============================================================

def build_output(board):
    """
    Menghasilkan struktur data.json final.
    """

    alongside = [
        normalize_record(x, "alongside")
        for x in board.get("alongside", [])
    ]

    anchorage = [
        normalize_record(x, "anchorage")
        for x in board.get("anchorage", [])
    ]

    confirmed = [
        normalize_record(x, "confirmed")
        for x in board.get("confirmed", [])
    ]

    open_stack = [
        normalize_record(x, "openStack")
        for x in board.get("openStack", [])
    ]

    schedule = [
        normalize_record(x, "schedule")
        for x in board.get("schedule", [])
    ]

    history = [
        normalize_record(x, "history")
        for x in board.get("history", [])
    ]

    # --------------------------------------------------------
    # Deduplicate each section independently.
    #
    # IMPORTANT:
    # Schedule and History are NEVER merged.
    # --------------------------------------------------------

    alongside = deduplicate(alongside)
    anchorage = deduplicate(anchorage)
    confirmed = deduplicate(confirmed)
    open_stack = deduplicate(open_stack)
    schedule = deduplicate(schedule)
    history = deduplicate(history)

    # --------------------------------------------------------
    # Safety validation
    # --------------------------------------------------------

    total_source = sum(
        len(board.get(key, []))
        for key in [
            "alongside",
            "anchorage",
            "confirmed",
            "openStack",
            "schedule",
            "history",
        ]
    )

    total_output = sum(
        len(x)
        for x in [
            alongside,
            anchorage,
            confirmed,
            open_stack,
            schedule,
            history,
        ]
    )

    if total_source > 0 and total_output == 0:
        raise RuntimeError(
            "WA_BOARD memiliki data tetapi hasil normalisasi kosong."
        )

    return {
        "lastUpdated": iso_now(),
        "updatedAt": iso_now(),

        "source": URL,

        # ----------------------------------------------------
        # Main sections
        # ----------------------------------------------------

        "vesselAlongside": alongside,
        "anchorage": anchorage,
        "confirmedVessel": confirmed,
        "openStack": open_stack,
        "vesselSchedule": schedule,
        "vesselHistory": history,

        # ----------------------------------------------------
        # Counts
        # ----------------------------------------------------

        "counts": {
            "alongside": len(alongside),
            "anchorage": len(anchorage),
            "confirmed": len(confirmed),
            "openStack": len(open_stack),
            "schedule": len(schedule),
            "history": len(history),

            "total": (
                len(alongside)
                + len(anchorage)
                + len(confirmed)
                + len(open_stack)
                + len(schedule)
                + len(history)
            ),
        },
    }


# ============================================================
# WRITE JSON
# ============================================================

def write_json(data):
    """
    Menulis data.json secara atomic.
    """

    temp_file = OUTPUT_FILE.with_suffix(".tmp")

    with temp_file.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    temp_file.replace(OUTPUT_FILE)

    logging.info(
        "Saved %s",
        OUTPUT_FILE.resolve(),
    )


# ============================================================
# SCRAPER
# ============================================================

async def scrape():
    logging.info("=" * 70)
    logging.info("Pelindo TPKS scraper started")
    logging.info("=" * 70)

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
        )

        page = await browser.new_page(
            viewport={
                "width": 1920,
                "height": 1080,
            }
        )

        page.set_default_timeout(
            NAVIGATION_TIMEOUT
        )

        try:

            logging.info(
                "Opening Pelindo Webaccess..."
            )

            await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT,
            )

            logging.info(
                "Page loaded."
            )

            # ------------------------------------------------
            # Give inline scripts / board rendering time.
            # ------------------------------------------------

            await page.wait_for_timeout(
                WAIT_AFTER_LOAD
            )

            # ------------------------------------------------
            # Wait specifically for WA_BOARD.
            # ------------------------------------------------

            try:
                await page.wait_for_function(
                    """
                    () => (
                        window.WA_BOARD &&
                        typeof window.WA_BOARD === 'object'
                    )
                    """,
                    timeout=30000,
                )

            except PlaywrightTimeoutError:
                # Save HTML for diagnostics.
                try:
                    html = await page.content()

                    Path(
                        "debug_pelindo.html"
                    ).write_text(
                        html,
                        encoding="utf-8",
                    )

                    logging.error(
                        "window.WA_BOARD tidak muncul. "
                        "Saved debug_pelindo.html"
                    )

                except Exception as debug_error:
                    logging.error(
                        "Failed to save debug HTML: %s",
                        debug_error,
                    )

                raise RuntimeError(
                    "Timeout menunggu window.WA_BOARD."
                )

            # ------------------------------------------------
            # Extract
            # ------------------------------------------------

            board = await extract_wa_board(
                page
            )

            # ------------------------------------------------
            # Validate
            # ------------------------------------------------

            validate_board(board)

            logging.info(
                "WA_BOARD sections:"
            )

            for key in [
                "alongside",
                "anchorage",
                "confirmed",
                "openStack",
                "schedule",
                "history",
            ]:
                logging.info(
                    "  %-12s : %d",
                    key,
                    len(board.get(key, [])),
                )

            # ------------------------------------------------
            # Build final JSON
            # ------------------------------------------------

            output = build_output(
                board
            )

            # ------------------------------------------------
            # Write
            # ------------------------------------------------

            write_json(
                output
            )

            logging.info("=" * 70)
            logging.info(
                "Scraper completed successfully."
            )
            logging.info(
                "Total records: %d",
                output["counts"]["total"],
            )
            logging.info("=" * 70)

        finally:

            await browser.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(
            scrape()
        )

    except Exception as exc:
        logging.exception(
            "SCRAPER FAILED: %s",
            exc,
        )
        raise
