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

# ============================================================

# BASIC HELPERS

# ============================================================

def normalize_text(text):
if not text:
return ""

```
return (
    text.replace("\xa0", " ")
    .replace("\r", "")
    .strip()
)
```

def clean_lines(text):
return [
normalize_text(line)
for line in text.splitlines()
if normalize_text(line)
]

def is_footer_name(name):
name_lower = name.lower()

```
footer_keywords = [
    "wa hotline",
    "telpon/wa",
    "support",
    "contact",
    "planner",
    "customer service",
]

return any(
    keyword in name_lower
    for keyword in footer_keywords
)
```

# ============================================================

# VESSEL BLOCK VALIDATION

# ============================================================

def extract_voyage(block):
for line in block[:8]:

```
    line = normalize_text(line)

    if not line:
        continue

    if DATE_PATTERN.search(line):
        continue

    excluded = [
        "DOMESTIC",
        "INTERNATIONAL",
        "ETA :",
        "ETB :",
        "ETD :",
        "ATB :",
        "ATD :",
        "Open Stack :",
        "Closing Time :",
        "Booking / Open / Actual :",
        "Export Box / Teus :",
        "Import Box / Teus :",
        "Vessel Name",
        "Periode",
    ]

    if any(
        x.lower() in line.lower()
        for x in excluded
    ):
        continue

    if "/" in line:
        return line

return ""
```

def is_valid_vessel_block(block):

```
voyage = extract_voyage(block)

if not voyage:
    return False

keywords = [
    "DOMESTIC",
    "INTERNATIONAL",
    "ETA :",
    "ETB :",
    "ETD :",
    "ATB :",
    "ATD :",
    "Open Stack :",
    "Closing Time :",
    "Booking / Open / Actual :",
    "Export Box / Teus :",
    "Import Box / Teus :",
]

joined = " ".join(block).lower()

return any(
    keyword.lower() in joined
    for keyword in keywords
)
```

# ============================================================

# PARSE STANDARD VESSEL

# ============================================================

def parse_vessel_block(
vessel_name,
vessel_code,
block
):

```
data = {
    "vesselName": vessel_name,
    "vesselCode": vessel_code,
    "voyage": extract_voyage(block),

    "eta": "",
    "etb": "",
    "etd": "",
    "atb": "",
    "atd": "",

    "openStack": "",
    "closingTime": "",

    "booking": "",
    "open": "",
    "actual": "",

    "exportBox": "",
    "exportTeus": "",
    "importBox": "",
    "importTeus": "",
}

for line in block:

    line = normalize_text(line)

    if line.startswith("ETA :"):

        data["eta"] = line.replace(
            "ETA :",
            "",
            1
        ).strip()

    elif line.startswith("ETB :"):

        data["etb"] = line.replace(
            "ETB :",
            "",
            1
        ).strip()

    elif line.startswith("ETD :"):

        data["etd"] = line.replace(
            "ETD :",
            "",
            1
        ).strip()

    elif line.startswith("ATB :"):

        data["atb"] = line.replace(
            "ATB :",
            "",
            1
        ).strip()

    elif line.startswith("ATD :"):

        data["atd"] = line.replace(
            "ATD :",
            "",
            1
        ).strip()

    elif line.startswith("Open Stack :"):

        data["openStack"] = line.replace(
            "Open Stack :",
            "",
            1
        ).strip()

    elif line.startswith("Closing Time :"):

        data["closingTime"] = line.replace(
            "Closing Time :",
            "",
            1
        ).strip()

    elif line.startswith(
        "Booking / Open / Actual :"
    ):

        value = line.replace(
            "Booking / Open / Actual :",
            "",
            1
        ).strip()

        parts = [
            x.strip()
            for x in value.split("/")
        ]

        if len(parts) >= 3:

            data["booking"] = parts[0]
            data["open"] = parts[1]
            data["actual"] = parts[2]

    elif line.startswith(
        "Export Box / Teus :"
    ):

        value = line.replace(
            "Export Box / Teus :",
            "",
            1
        ).strip()

        parts = [
            x.strip()
            for x in value.split("/")
        ]

        if len(parts) >= 2:

            data["exportBox"] = parts[0]
            data["exportTeus"] = parts[1]

    elif line.startswith(
        "Import Box / Teus :"
    ):

        value = line.replace(
            "Import Box / Teus :",
            "",
            1
        ).strip()

        parts = [
            x.strip()
            for x in value.split("/")
        ]

        if len(parts) >= 2:

            data["importBox"] = parts[0]
            data["importTeus"] = parts[1]

return data
```

# ============================================================

# PARSE VESSELS FROM A SPECIFIC TD.VESSEL

# ============================================================

def parse_vessel_cell(text):

```
lines = clean_lines(text)

vessels = []

vessel_positions = []

for i, line in enumerate(lines):

    match = VESSEL_PATTERN.match(line)

    if not match:
        continue

    vessel_name = match.group(1).strip()

    if is_footer_name(vessel_name):
        continue

    vessel_positions.append(i)

for position_index, start in enumerate(
    vessel_positions
):

    line = lines[start]

    match = VESSEL_PATTERN.match(line)

    if not match:
        continue

    vessel_name = match.group(1).strip()
    vessel_code = match.group(2).strip()

    if position_index + 1 < len(
        vessel_positions
    ):

        end = vessel_positions[
            position_index + 1
        ]

    else:

        end = len(lines)

    block = lines[
        start + 1:end
    ]

    if not is_valid_vessel_block(block):
        continue

    vessel = parse_vessel_block(
        vessel_name,
        vessel_code,
        block
    )

    vessels.append(vessel)

return vessels
```

# ============================================================

# FIND THE 4 MAIN VESSEL SECTIONS

# ============================================================

async def get_vessel_sections(page):

```
cells = await page.locator(
    "td.vessel"
).evaluate_all("""
    els => els.map((el, index) => ({
        index: index,
        text: el.innerText || ""
    }))
""")

sections = {}

for cell in cells:

    raw_text = cell["text"]
    text = normalize_text(raw_text)

    if "Vessel Schedule" in text:

        sections["schedule"] = text

    elif "Confirmed Vessel" in text:

        sections["confirmed"] = text

    elif "Open Stack" in text:

        sections["openStack"] = text

    elif (
        "Vessel Alongside" in text
        or "Vessel\\u00a0Alongside" in raw_text
    ):

        sections["alongside"] = text

return sections
```

# ============================================================

# LOAD VESSEL HISTORY

# ============================================================

async def load_history_section(page):

```
print()
print(
    "[HISTORY] Mencari tombol History..."
)

history_links = page.locator(
    'td.vessel a[data-url*="vessel_audit"]'
)

count = await history_links.count()

print(
    f"[HISTORY] Jumlah tombol History: {count}"
)

if count == 0:

    print(
        "[HISTORY] Tombol History tidak ditemukan."
    )

    return ""

first_link = history_links.first

title = await first_link.get_attribute(
    "title"
)

data_url = await first_link.get_attribute(
    "data-url"
)

print(
    f"[HISTORY] Klik History: {title}"
)

print(
    f"[HISTORY] Audit URL: {data_url}"
)

try:

    await first_link.click(
        timeout=10000
    )

except Exception as e:

    print(
        f"[HISTORY] Click error: {e}"
    )

    try:

        await first_link.evaluate(
            "el => el.click()"
        )

    except Exception as e2:

        print(
            f"[HISTORY] JavaScript click error: {e2}"
        )

        return ""

await page.wait_for_timeout(2500)

close_button = page.locator(
    "#TB_closeWindowButton"
)

if await close_button.count() > 0:

    try:

        await close_button.click(
            timeout=5000
        )

        print(
            "[HISTORY] Modal audit ditutup."
        )

    except Exception as e:

        print(
            f"[HISTORY] Gagal menutup modal: {e}"
        )

await page.wait_for_timeout(1000)

cells_after = await page.locator(
    "td.vessel"
).evaluate_all("""
    els => els.map((el, index) => ({
        index: index,
        text: el.innerText || ""
    }))
""")

print(
    f"[HISTORY] Jumlah td.vessel setelah History: "
    f"{len(cells_after)}"
)

for cell in cells_after:

    text = normalize_text(
        cell["text"]
    )

    if "Vessel History" in text:

        print(
            f"[HISTORY] Section ditemukan di "
            f"td.vessel index {cell['index']}"
        )

        return text

print(
    "[HISTORY] Section Vessel History tidak ditemukan."
)

return ""
```

# ============================================================

# PARSE VESSEL SCHEDULE

#

# Schedule berbeda dengan section vessel lainnya:

# formatnya hanya:

#

# Vessel Name

# Periode

#

# NAME (CODE)

# VOYAGE

# ETB : DATE

#

# NAME (CODE)

# VOYAGE

# ETB : DATE

#

# Kita menggunakan vessel berikutnya sebagai batas

# setiap record, bukan batas jumlah baris.

# ============================================================

def parse_schedule(text):

```
lines = clean_lines(text)

schedules = []

vessel_positions = []

for i, line in enumerate(lines):

    match = VESSEL_PATTERN.match(line)

    if not match:
        continue

    vessel_name = match.group(1).strip()

    if is_footer_name(vessel_name):
        continue

    vessel_positions.append(i)

for position_index, start in enumerate(
    vessel_positions
):

    line = lines[start]

    match = VESSEL_PATTERN.match(line)

    if not match:
        continue

    vessel_name = match.group(1).strip()
    vessel_code = match.group(2).strip()

    if position_index + 1 < len(
        vessel_positions
    ):

        end = vessel_positions[
            position_index + 1
        ]

    else:

        end = len(lines)

    block = lines[
        start + 1:end
    ]

    voyage = ""
    etb = ""

    # Cari voyage
    for block_line in block:

        if DATE_PATTERN.search(block_line):
            continue

        if block_line.startswith("ETB :"):
            continue

        if block_line in (
            "Detail",
            "[ Detail ]"
        ):
            continue

        if "/" in block_line:

            voyage = block_line
            break

    # Cari ETB
    for block_line in block:

        if block_line.startswith("ETB :"):

            etb = block_line.replace(
                "ETB :",
                "",
                1
            ).strip()

            break

    # Record Schedule dianggap valid
    # jika memiliki voyage dan ETB.
    if not voyage or not etb:
        continue

    schedules.append({
        "vesselName": vessel_name,
        "vesselCode": vessel_code,
        "voyage": voyage,
        "etb": etb
    })

return schedules
```

# ============================================================

# BUILD DATA

# ============================================================

def build_data(
alongside,
confirmed,
open_stack,
schedule,
history
):

```
return {

    "lastUpdated": datetime.now().strftime(
        "%d/%m/%Y %H:%M"
    ),

    "source": URL,

    "vesselAlongside": alongside,

    "confirmedVessel": confirmed,

    "openStack": open_stack,

    "vesselSchedule": schedule,

    "vesselHistory": history,

    "allVessels": (
        alongside
        + confirmed
        + open_stack
        + history
    ),
}
```

# ============================================================

# OPEN PELINDO

# ============================================================

async def open_pelindo(page):

```
for attempt in range(
    1,
    MAX_RETRIES + 1
):

    try:

        print(
            f"[CONNECT] Percobaan "
            f"{attempt}/{MAX_RETRIES}"
        )

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
            "[CONNECT] Navigation timeout."
        )

        try:

            body_text = await page.locator(
                "body"
            ).inner_text(
                timeout=5000
            )

            if body_text.strip():

                print(
                    "[CONNECT] Body tetap tersedia "
                    "setelah timeout."
                )

                return True

        except Exception:
            pass

    except Exception as e:

        print(
            f"[CONNECT] Error: {e}"
        )

    if attempt < MAX_RETRIES:

        print(
            "[CONNECT] Menunggu sebelum retry..."
        )

        await page.wait_for_timeout(
            5000
        )

return False
```

# ============================================================

# MAIN

# ============================================================

async def main():

```
print()
print("=" * 70)
print("PELINDO VESSEL SCRAPER")
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

    page.set_default_timeout(
        15000
    )

    # ----------------------------------------------------
    # CONNECT
    # ----------------------------------------------------

    print()
    print("[1] Membuka Pelindo...")

    success = await open_pelindo(
        page
    )

    if not success:

        print(
            "[ERROR] Gagal membuka Pelindo."
        )

        await browser.close()
        return

    # ----------------------------------------------------
    # WAIT
    # ----------------------------------------------------

    print()
    print(
        "[2] Menunggu data vessel..."
    )

    await page.wait_for_timeout(
        WAIT_AFTER_LOAD
    )

    # ----------------------------------------------------
    # MAIN SECTIONS
    # ----------------------------------------------------

    print()
    print(
        "[3] Mengambil 4 section utama..."
    )

    sections = await get_vessel_sections(
        page
    )

    print()
    print(
        "[SECTION] Alongside :",
        "OK"
        if "alongside" in sections
        else "TIDAK ADA"
    )

    print(
        "[SECTION] Confirmed :",
        "OK"
        if "confirmed" in sections
        else "TIDAK ADA"
    )

    print(
        "[SECTION] Open Stack:",
        "OK"
        if "openStack" in sections
        else "TIDAK ADA"
    )

    print(
        "[SECTION] Schedule  :",
        "OK"
        if "schedule" in sections
        else "TIDAK ADA"
    )

    # ----------------------------------------------------
    # PARSE MAIN SECTIONS
    # ----------------------------------------------------

    alongside = parse_vessel_cell(
        sections.get(
            "alongside",
            ""
        )
    )

    confirmed = parse_vessel_cell(
        sections.get(
            "confirmed",
            ""
        )
    )

    open_stack = parse_vessel_cell(
        sections.get(
            "openStack",
            ""
        )
    )

    # ----------------------------------------------------
    # PARSE SCHEDULE
    # ----------------------------------------------------

    schedule = parse_schedule(
        sections.get(
            "schedule",
            ""
        )
    )

    # ----------------------------------------------------
    # HISTORY
    # ----------------------------------------------------

    print()
    print(
        "[4] Memuat Vessel History..."
    )

    history_text = await load_history_section(
        page
    )

    history = parse_vessel_cell(
        history_text
    )

    # ----------------------------------------------------
    # RESULT
    # ----------------------------------------------------

    print()
    print("=" * 70)
    print("HASIL SCRAPING")
    print("=" * 70)

    print(
        "Alongside:",
        len(alongside)
    )

    print(
        "Confirmed:",
        len(confirmed)
    )

    print(
        "Open Stack:",
        len(open_stack)
    )

    print(
        "Schedule:",
        len(schedule)
    )

    print(
        "History:",
        len(history)
    )

    # ----------------------------------------------------
    # SHOW SCHEDULE
    # ----------------------------------------------------

    print()
    print("SCHEDULE DATA:")

    for vessel in schedule:

        print(
            f"- {vessel['vesselName']} "
            f"| {vessel['voyage']} "
            f"| ETB: {vessel['etb']}"
        )

    # ----------------------------------------------------
    # SHOW HISTORY
    # ----------------------------------------------------

    print()
    print("HISTORY DATA:")

    for vessel in history:

        print(
            f"- {vessel['vesselName']} "
            f"| {vessel['voyage']}"
        )

    # ----------------------------------------------------
    # BUILD JSON
    # ----------------------------------------------------

    data = build_data(
        alongside=alongside,
        confirmed=confirmed,
        open_stack=open_stack,
        schedule=schedule,
        history=history
    )

    # ----------------------------------------------------
    # WRITE JSON
    # ----------------------------------------------------

    with open(
        "data.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        "DATA.JSON BERHASIL DIBUAT"
    )

    print()
    print("=" * 70)
    print("SCRAPER SELESAI")
    print("=" * 70)

    await browser.close()
```

if **name** == "**main**":
asyncio.run(main())

````

### Perubahan yang benar-benar dilakukan

**Hanya parser Schedule yang diperbaiki secara fungsional.**

Sebelumnya:

```python
block = schedule_lines[i + 1:i + 8]
````

Sekarang:

```python
vessel_positions = []
```

Kemudian setiap vessel dianggap sebagai awal record baru, sehingga:

```text
WAN HAI 311
↓
EVER OASIS
```

menjadi batas record pertama.

Dengan demikian parser **tidak peduli berapa jumlah baris di antara dua vessel**.

Target dari data yang sudah kita lihat adalah:

```text
SCHEDULE DATA:
- WAN HAI 311 | S259 / N260 | ETB: 24/09/2026 10:00
- EVER OASIS | 0493-092S / 0493-092N | ETB: 23/09/2026 22:00
- SINAR BINTAN | 952S / 952N | ETB: 24/09/2026 21:00
- MMSS 2711 | 261016N / 261016N | ETB: 16/09/2026 10:00
- EVER OPTIMA | 0494-050S / 0494-050N | ETB: 24/09/2026 18:00
- SITC BATANGAS | 2618S / 2619N | ETB: 01/10/2026 16:00
- MAERSK VIGO | 637S / 638N | ETB: 21/09/2026 15:00
```

Jadi jalankan:

```text
python scraper.py
```

Lalu **cukup kirim bagian `HASIL SCRAPING` dan `SCHEDULE DATA`**. Kalau Schedule sudah **7**, kita anggap scraper sudah beres dan baru lanjut ke `index.html`.
