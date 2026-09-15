async def get_vessel_sections(page):

    cells = await page.locator(
        "td.vessel"
    ).evaluate_all("""
        els => els.map((el, index) => {

            const heading = el.querySelector(
                "span.images-v"
            );

            return {
                index: index,
                text: el.innerText || "",
                headingClass: heading
                    ? heading.className
                    : "",
                headingText: heading
                    ? heading.innerText
                    : ""
            };
        })
    """)

    sections = {}

    for cell in cells:

        raw_text = cell["text"]
        text = normalize_text(raw_text)

        heading_class = cell["headingClass"]
        heading_text = normalize_text(
            cell["headingText"]
        )

        # ----------------------------------------------------
        # VESSEL ALONGSIDE
        # ----------------------------------------------------

        if "images-v2" in heading_class:

            sections["alongside"] = text

        # ----------------------------------------------------
        # CONFIRMED VESSEL
        # ----------------------------------------------------

        elif "images-v3" in heading_class:

            sections["confirmed"] = text

        # ----------------------------------------------------
        # OPEN STACK
        # ----------------------------------------------------

        elif "images-v4" in heading_class:

            sections["openStack"] = text

        # ----------------------------------------------------
        # VESSEL SCHEDULE
        # ----------------------------------------------------

        elif "images-v5" in heading_class:

            sections["schedule"] = text

        # ----------------------------------------------------
        # FALLBACK BERDASARKAN TEXT
        # ----------------------------------------------------

        elif "Vessel Alongside" in text:

            sections["alongside"] = text

        elif "Confirmed Vessel" in text:

            sections["confirmed"] = text

        elif "Open Stack" in text:

            sections["openStack"] = text

        elif "Vessel Schedule" in text:

            sections["schedule"] = text

    return sections
