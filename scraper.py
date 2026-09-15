async def get_vessel_sections(page):

    # Ambil hanya td.vessel dari tabel utama Pelindo.
    # Berdasarkan DOM yang sudah kita verifikasi:
    # [0] Alongside
    # [1] Confirmed
    # [2] Open Stack
    # [3] Vessel Schedule

    main_table = page.locator("table").first

    cells = main_table.locator("td.vessel")

    count = await cells.count()

    print()
    print("=" * 70)
    print("MAIN VESSEL TABLE")
    print("=" * 70)
    print("Jumlah section:", count)

    sections = {}

    if count < 4:
        raise RuntimeError(
            f"Section vessel tidak lengkap. "
            f"Ditemukan {count} td.vessel, seharusnya minimal 4."
        )

    # --------------------------------------------------------
    # SECTION 0 = VESSEL ALONGSIDE
    # --------------------------------------------------------

    sections["alongside"] = normalize_text(
        await cells.nth(0).inner_text()
    )

    # --------------------------------------------------------
    # SECTION 1 = CONFIRMED VESSEL
    # --------------------------------------------------------

    sections["confirmed"] = normalize_text(
        await cells.nth(1).inner_text()
    )

    # --------------------------------------------------------
    # SECTION 2 = OPEN STACK
    # --------------------------------------------------------

    sections["openStack"] = normalize_text(
        await cells.nth(2).inner_text()
    )

    # --------------------------------------------------------
    # SECTION 3 = VESSEL SCHEDULE
    # --------------------------------------------------------

    sections["schedule"] = normalize_text(
        await cells.nth(3).inner_text()
    )

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    print()
    print("[0] ALONGSIDE")
    print(sections["alongside"][:500])

    print()
    print("[1] CONFIRMED")
    print(sections["confirmed"][:500])

    print()
    print("[2] OPEN STACK")
    print(sections["openStack"][:500])

    print()
    print("[3] SCHEDULE")
    print(sections["schedule"][:1500])

    print("=" * 70)

    return sections
