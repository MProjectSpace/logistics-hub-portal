#!/usr/bin/env python3

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================
# CONFIGURATION
# ============================================================

URL = "https://ibstpks.pelindo.co.id/webaccess/"

OUTPUT_FILE = Path("data.json")
DEBUG_HTML = Path("debug_pelindo.html")

NAVIGATION_TIMEOUT = 120_000
WA_BOARD_TIMEOUT = 120_000
WAIT_AFTER_LOAD = 3_000

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("pelindo-scraper")


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    """
    Membersihkan nilai agar aman dimasukkan ke JSON.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()

    return str(value).strip()


def first_nonempty(*values):
    """
    Mengambil nilai pertama yang tidak kosong.
    """
    for value in values:
        value = clean_text(value)
        if value:
            return value

    return ""


def make_voyage(voyage_in, voyage_out):
    """
    Menghasilkan format:
        VOYAGE_IN / VOYAGE_OUT

    Jika salah satu kosong, tetap aman.
    """
    voyage_in = clean_text(voyage_in)
    voyage_out = clean_text(voyage_out)

    if voyage_in and voyage_out:
        return f"{voyage_in} / {voyage_out}"

    if voyage_in:
        return voyage_in

    if voyage_out:
        return voyage_out

    return "-"


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_record(raw, category):
    """
    Mengubah record WA_BOARD Pelindo menjadi format data.json
    yang kompatibel dengan frontend lama.

    category:
        alongside
        anchorage
        confirmed
        openStack
        schedule
        history
    """

    if not isinstance(raw, dict):
        return None

    vessel_name = clean_text(raw.get("name"))
    vessel_code = clean_text(raw.get("id"))

    voyage_in = clean_text(raw.get("voyageIn"))
    voyage_out = clean_text(raw.get("voyageOut"))

    # --------------------------------------------------------
    # Skip record yang benar-benar tidak mempunyai identitas
    # --------------------------------------------------------

    if not vessel_name and not vessel_code:
        return None

    # --------------------------------------------------------
    # Shipping line / customer
    # --------------------------------------------------------

    shipping_line = first_nonempty(
        raw.get("customer"),
        raw.get("agentName"),
        raw.get("principal"),
        raw.get("agent"),
    )

    # --------------------------------------------------------
    # Time fields
    # --------------------------------------------------------

    eta = first_nonempty(
        raw.get("timeArrival"),
        raw.get("eta"),
    )

    etb = clean_text(raw.get("estBerthTs"))
    atb = clean_text(raw.get("actBerthTs"))
    etd = clean_text(raw.get("estDepTs"))
    atd = clean_text(raw.get("actDepTs"))

    # --------------------------------------------------------
    # Booking / stack fields
    # --------------------------------------------------------

    booking = first_nonempty(
        raw.get("bkgExport"),
        raw.get("bkgBoxes"),
    )

    open_value = clean_text(raw.get("bkgOpen"))

    actual = clean_text(raw.get("joExport"))

    open_stack = clean_text(raw.get("availableTs"))

    closing_time = clean_text(raw.get("recvCtrCutoffTs"))

    # --------------------------------------------------------
    # History cargo
    # --------------------------------------------------------

    export_box = clean_text(raw.get("exportBox"))
    export_teus = clean_text(raw.get("exportTeus"))
    import_box = clean_text(raw.get("importBox"))
    import_teus = clean_text(raw.get("importTeus"))

    # --------------------------------------------------------
    # Main normalized record
    # --------------------------------------------------------

    record = {
        # Existing frontend-compatible fields
        "vesselName": vessel_name,
        "vesselCode": vessel_code,
        "voyage": make_voyage(voyage_in, voyage_out),
        "shippingLine": shipping_line,
        "type": clean_text(raw.get("oi")),

        "eta": eta,
        "etb": etb,
        "atb": atb,
        "etd": etd,
        "atd": atd,

        "openStack": open_stack,
        "closingTime": closing_time,

        "booking": booking,
        "open": open_value,
        "actual": actual,

        "export": export_box,
        "exportTeus": export_teus,
        "import": import_box,
        "importTeus": import_teus,

        "vesId": vessel_code,

        # Kept empty intentionally.
        # The new Pelindo page loads details through POST
        # rather than exposing these as normal URLs.
        "detailUrl": "",
        "historyUrl": "",

        # ----------------------------------------------------
        # Original Pelindo fields
        # ----------------------------------------------------

        "name": vessel_name,
        "id": vessel_code,
        "voyageIn": voyage_in,
        "voyageOut": voyage_out,

        "oi": clean_text(raw.get("oi")),
        "mvSts": clean_text(raw.get("mvSts")),

        "customer": clean_text(raw.get("customer")),
        "agentName": clean_text(raw.get("agentName")),
        "principal": clean_text(raw.get("principal")),
        "agent": clean_text(raw.get("agent")),

        "actBerthTs": clean_text(raw.get("actBerthTs")),
        "actBerthingTsISO": clean_text(
            raw.get("actBerthingTsISO")
        ),

        "estDepTs": clean_text(raw.get("estDepTs")),
        "estDepartureTsISO": clean_text(
            raw.get("estDepartureTsISO")
        ),

        "anchorageTs": clean_text(raw.get("anchorageTs")),

        "estBerthTs": clean_text(raw.get("estBerthTs")),
        "estBerthingTsISO": clean_text(
            raw.get("estBerthingTsISO")
        ),

        "timeArrival": clean_text(raw.get("timeArrival")),
        "availableTs": clean_text(raw.get("availableTs")),
        "availableTsISO": clean_text(
            raw.get("availableTsISO")
        ),

        "recvCtrCutoffTs": clean_text(
            raw.get("recvCtrCutoffTs")
        ),

        "cutoffCtr": clean_text(raw.get("cutoffCtr")),

        "bkgExport": clean_text(raw.get("bkgExport")),
        "bkgOpen": clean_text(raw.get("bkgOpen")),
        "joExport": clean_text(raw.get("joExport")),

        "actDepTs": clean_text(raw.get("actDepTs")),

        "exportBox": export_box,
        "exportTeus": export_teus,
        "importBox": import_box,
        "importTeus": import_teus,

        # ----------------------------------------------------
        # Schedule-specific fields
        # ----------------------------------------------------

        "callSign": clean_text(raw.get("callSign")),
        "etaRaw": clean_text(raw.get("eta")),
        "feederDirect": clean_text(raw.get("feederDirect")),
        "onWindowsFlag": clean_text(
            raw.get("onWindowsFlag")
        ),
        "bkgBoxes": clean_text(raw.get("bkgBoxes")),
        "bkgTeus": clean_text(raw.get("bkgTeus")),

        # ----------------------------------------------------
        # History-specific fields
        # ----------------------------------------------------

        "actDepartureTsISO": clean_text(
            raw.get("actDepartureTsISO")
        ),

        "actStartWorkTs": clean_text(
            raw.get("actStartWorkTs")
        ),

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        "category": category,
    }

    return record


# ============================================================
# DEDUPLICATION
# ============================================================

def record_key(record):
    """
    Unique key untuk satu voyage.

    Sangat penting:
        SINAR BINTAN / SIBI093 / 951S / 951N
    berbeda dengan:
        SINAR BINTAN / SIBI094 / 952S / 952N

    Dan voyage berbeda dalam section yang berbeda
    juga tidak boleh saling menghapus.
    """

    return (
        clean_text(record.get("vesselName")).upper(),
        clean_text(record.get("vesselCode")).upper(),
        clean_text(record.get("voyageIn")).upper(),
        clean_text(record.get("voyageOut")).upper(),
    )


def deduplicate_records(records):
    """
    Deduplikasi hanya di dalam section yang sama.
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
# SECTION PROCESSING
# ============================================================

def process_section(raw_records, category):
    """
    Memproses satu array WA_BOARD.
    """

    if not isinstance(raw_records, list):
        logger.warning(
            "Section '%s' bukan array. Menggunakan []",
            category,
        )
        return []

    normalized = []

    for raw in raw_records:
        record = normalize_record(raw, category)

        if record is not None:
            normalized.append(record)

    return deduplicate_records(normalized)


# ============================================================
# VALIDATION
# ============================================================

def validate_board(board):
    """
    Memastikan struktur WA_BOARD sesuai dengan halaman Pelindo
    terbaru.
    """

    if not isinstance(board, dict):
        raise RuntimeError(
            "window.WA_BOARD bukan object yang valid."
        )

    required = [
        "alongside",
        "confirmed",
        "openStack",
        "schedule",
        "history",
    ]

    missing = [
        key
        for key in required
        if key not in board
    ]

    if missing:
        raise RuntimeError(
            "WA_BOARD kehilangan key: "
            + ", ".join(missing)
        )

    for key in required:
        if not isinstance(board[key], list):
            raise RuntimeError(
                f"WA_BOARD['{key}'] bukan array."
            )

    # Anchorage optional karena pada halaman saat ini
    # bisa saja kosong atau tidak digunakan.
    if "anchorage" not in board:
        board["anchorage"] = []

    if not isinstance(board["anchorage"], list):
        board["anchorage"] = []

    return True


def validate_status(records, expected_status, section_name):
    """
    Memastikan record tidak salah masuk section.

    Contoh:
        Schedule tidak boleh berisi HISTORY.
    """

    wrong = []

    for record in records:
        status = clean_text(
            record.get("mvSts")
        ).upper()

        if status and status != expected_status:
            wrong.append(
                (
                    record.get("vesselName"),
                    status,
                )
            )

    if wrong:
        logger.warning(
            "%s memiliki %d record dengan status berbeda.",
            section_name,
            len(wrong),
        )

        for vessel_name, status in wrong[:10]:
            logger.warning(
                "  %s -> %s",
                vessel_name,
                status,
            )


# ============================================================
# PLAYWRIGHT
# ============================================================

async def get_wa_board(page):
    """
    Mengambil window.WA_BOARD langsung dari browser.

    Ini adalah sumber data utama scraper.
    """

    logger.info(
        "Menunggu window.WA_BOARD..."
    )

    await page.wait_for_function(
        """
        () => {
            const b = window.WA_BOARD;

            return b &&
                   Array.isArray(b.alongside) &&
                   Array.isArray(b.confirmed) &&
                   Array.isArray(b.openStack) &&
                   Array.isArray(b.schedule) &&
                   Array.isArray(b.history);
        }
        """,
        timeout=WA_BOARD_TIMEOUT,
    )

    # Tunggu sebentar agar halaman benar-benar selesai
    # menjalankan script/rendering.
    await page.wait_for_timeout(
        WAIT_AFTER_LOAD
    )

    board = await page.evaluate(
        """
        () => {
            const b = window.WA_BOARD;

            return JSON.parse(
                JSON.stringify(b)
            );
        }
        """
    )

    return board


async def save_debug_html(page):
    """
    Menyimpan HTML halaman jika terjadi error.
    """

    try:
        html = await page.content()

        DEBUG_HTML.write_text(
            html,
            encoding="utf-8",
        )

        logger.info(
            "Debug HTML disimpan: %s",
            DEBUG_HTML,
        )

    except Exception as exc:
        logger.warning(
            "Gagal menyimpan debug HTML: %s",
            exc,
        )


# ============================================================
# JSON OUTPUT
# ============================================================

def write_json_atomic(payload):
    """
    Menulis data.json secara atomic.
    """

    temp_file = OUTPUT_FILE.with_suffix(
        ".json.tmp"
    )

    with temp_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    temp_file.replace(OUTPUT_FILE)


# ============================================================
# MAIN SCRAPER
# ============================================================

async def scrape():
    logger.info("======================================")
    logger.info("PELINDO TPKS SCRAPER")
    logger.info("======================================")
    logger.info("URL: %s", URL)

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True,
        )

        context = await browser.new_context(
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            viewport={
                "width": 1920,
                "height": 1080,
            },
        )

        page = await context.new_page()

        page.set_default_timeout(
            NAVIGATION_TIMEOUT
        )

        try:
            # ------------------------------------------------
            # LOAD PAGE
            # ------------------------------------------------

            logger.info(
                "Membuka halaman Pelindo..."
            )

            response = await page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT,
            )

            if response is not None:
                logger.info(
                    "HTTP status: %s",
                    response.status,
                )

                if response.status >= 400:
                    raise RuntimeError(
                        f"Pelindo mengembalikan HTTP "
                        f"{response.status}"
                    )

            await page.wait_for_selector(
                "body",
                timeout=NAVIGATION_TIMEOUT,
            )

            # ------------------------------------------------
            # GET WA_BOARD
            # ------------------------------------------------

            board = await get_wa_board(page)

            validate_board(board)

            logger.info(
                "window.WA_BOARD berhasil ditemukan."
            )

            # ------------------------------------------------
            # PROCESS EACH SECTION SEPARATELY
            # ------------------------------------------------

            vessel_alongside = process_section(
                board.get("alongside", []),
                "alongside",
            )

            anchorage_vessel = process_section(
                board.get("anchorage", []),
                "anchorage",
            )

            confirmed_vessel = process_section(
                board.get("confirmed", []),
                "confirmed",
            )

            open_stack = process_section(
                board.get("openStack", []),
                "openStack",
            )

            vessel_schedule = process_section(
                board.get("schedule", []),
                "schedule",
            )

            vessel_history = process_section(
                board.get("history", []),
                "history",
            )

            # ------------------------------------------------
            # VALIDATE SECTIONS
            # ------------------------------------------------

            validate_status(
                vessel_alongside,
                "ALONGSIDE",
                "Vessel Alongside",
            )

            validate_status(
                anchorage_vessel,
                "ANCHORAGE",
                "Anchorage",
            )

            validate_status(
                confirmed_vessel,
                "CONFIRMED",
                "Confirmed Vessel",
            )

            validate_status(
                open_stack,
                "OPEN_STACK",
                "Open Stack",
            )

            validate_status(
                vessel_schedule,
                "SCHEDULE",
                "Vessel Schedule",
            )

            validate_status(
                vessel_history,
                "HISTORY",
                "Vessel History",
            )

            # ------------------------------------------------
            # ALL VESSELS
            # ------------------------------------------------
            #
            # IMPORTANT:
            # Jangan deduplicate lintas kategori.
            #
            # SINAR BAJO:
            #   Confirmed = 135S / 135N
            #   Schedule  = 136S / 136N
            #
            # Keduanya harus tetap muncul.
            # ------------------------------------------------

            all_vessels = (
                vessel_alongside
                + anchorage_vessel
                + confirmed_vessel
                + open_stack
                + vessel_schedule
                + vessel_history
            )

            # ------------------------------------------------
            # TIMESTAMP
            # ------------------------------------------------

            now = datetime.now(
                JAKARTA_TZ
            )

            last_updated = now.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            updated_at = now.isoformat(
                timespec="seconds"
            )

            # ------------------------------------------------
            # OUTPUT
            # ------------------------------------------------

            payload = {
                "lastUpdated": last_updated,
                "updatedAt": updated_at,
                "source": URL,

                # Compatibility with existing frontend
                "allVessels": all_vessels,

                # Main dashboard sections
                "vesselAlongside": vessel_alongside,
                "confirmedVessel": confirmed_vessel,
                "openStack": open_stack,
                "vesselSchedule": vessel_schedule,
                "vesselHistory": vessel_history,

                # Kept separately so Anchorage is never
                # incorrectly classified as Alongside.
                "anchorageVessel": anchorage_vessel,

                # Counts
                "counts": {
                    "allVessels": len(all_vessels),

                    "vesselAlongside": len(
                        vessel_alongside
                    ),

                    "anchorageVessel": len(
                        anchorage_vessel
                    ),

                    "confirmedVessel": len(
                        confirmed_vessel
                    ),

                    "openStack": len(
                        open_stack
                    ),

                    "vesselSchedule": len(
                        vessel_schedule
                    ),

                    "vesselHistory": len(
                        vessel_history
                    ),
                },
            }

            # ------------------------------------------------
            # WRITE JSON
            # ------------------------------------------------

            write_json_atomic(
                payload
            )

            # ------------------------------------------------
            # SUMMARY
            # ------------------------------------------------

            logger.info("")
            logger.info(
                "========== SCRAPE RESULT =========="
            )

            logger.info(
                "Vessel Alongside : %d",
                len(vessel_alongside),
            )

            logger.info(
                "Anchorage        : %d",
                len(anchorage_vessel),
            )

            logger.info(
                "Confirmed Vessel : %d",
                len(confirmed_vessel),
            )

            logger.info(
                "Open Stack       : %d",
                len(open_stack),
            )

            logger.info(
                "Vessel Schedule  : %d",
                len(vessel_schedule),
            )

            logger.info(
                "Vessel History   : %d",
                len(vessel_history),
            )

            logger.info(
                "All Vessels      : %d",
                len(all_vessels),
            )

            logger.info(
                "===================================="
            )

            logger.info(
                "data.json berhasil dibuat."
            )

            logger.info(
                "======================================"
            )

            return payload

        except PlaywrightTimeoutError as exc:

            logger.error(
                "TIMEOUT saat mengambil data Pelindo."
            )

            logger.error(
                "Detail: %s",
                exc,
            )

            await save_debug_html(page)

            raise RuntimeError(
                "Timeout saat menunggu halaman "
                "Pelindo atau window.WA_BOARD."
            ) from exc

        except Exception as exc:

            logger.error(
                "Scraper gagal: %s",
                exc,
            )

            await save_debug_html(page)

            raise

        finally:

            await context.close()
            await browser.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        asyncio.run(
            scrape()
        )

    except KeyboardInterrupt:

        logger.warning(
            "Scraper dihentikan oleh user."
        )

        raise SystemExit(130)

    except Exception as exc:

        logger.error(
            "======================================"
        )

        logger.error(
            "SCRAPER FAILED"
        )

        logger.error(
            "%s",
            exc,
        )

        logger.error(
            "======================================"
        )

        # Exit code 1 hanya digunakan jika scraper
        # benar-benar gagal, bukan karena validasi
        # allVessels lama.
        raise SystemExit(1)
