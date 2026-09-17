# ============================================================
# PARSE SECTION CELL
# ============================================================

async def parse_section_cell(cell):

    records = []

    # --------------------------------------------------------
    # Determine whether this is the History container
    # --------------------------------------------------------

    is_history_container = False

    try:
        is_history_container = await cell.evaluate(
            """
            element => {
                return element.id === "div_ves_history"
                    || !!element.closest("#div_ves_history");
            }
            """
        )
    except Exception:
        pass

    # --------------------------------------------------------
    # Get cleaned HTML
    #
    # IMPORTANT:
    # For main sections, remove ALL History containers
    # before parsing.
    # --------------------------------------------------------

    html = await cell.evaluate(
        """
        (cell, isHistory) => {

            const clone = cell.cloneNode(true);

            /*
             * If this is not the History container itself,
             * remove every History container from the clone.
             */
            if (!isHistory) {

                clone.querySelectorAll(
                    "#div_ves_history"
                ).forEach(el => el.remove());

                /*
                 * Some Pelindo versions may use elements
                 * related to vessel history without the exact
                 * parent ID. Remove known audit/history links
                 * only when they are inside an explicit
                 * history container.
                 */
            }

            return clone.innerHTML;
        }
        """,
        is_history_container,
    )

    if not html.strip():
        return records

    # --------------------------------------------------------
    # Split vessel blocks by Pelindo HR separator
    # --------------------------------------------------------

    parts = re.split(
        r'<hr[^>]*class=["\'][^"\']*ves_along_sched_hr[^"\']*["\'][^>]*>',
        html,
        flags=re.IGNORECASE,
    )

    for part in parts:

        if not part.strip():
            continue

        # ----------------------------------------------------
        # Parse individual vessel block
        # ----------------------------------------------------

        data = await cell.evaluate(
            """
            (cell, html) => {

                const wrapper =
                    document.createElement("div");

                wrapper.innerHTML = html;

                /*
                 * Safety:
                 * Never parse vessel blocks that are inside
                 * a History container.
                 */
                const historyContainer =
                    wrapper.querySelector(
                        "#div_ves_history"
                    );

                if (historyContainer) {
                    historyContainer.remove();
                }

                const divs = [
                    ...wrapper.querySelectorAll(
                        "div.ves_along_sched"
                    )
                ];

                if (!divs.length)
                    return null;

                const lines = divs
                    .map(d => d.innerText.trim())
                    .filter(Boolean);

                const b = wrapper.querySelector(
                    "div.ves_along_sched b"
                );

                if (!b)
                    return null;

                const title = b.innerText.trim();

                const links = [
                    ...wrapper.querySelectorAll(
                        "a[data-url]"
                    )
                ].map(a => ({
                    url:
                        a.getAttribute("data-url") || "",

                    text:
                        a.innerText.trim(),

                    title:
                        a.getAttribute("title") || ""
                }));

                return {
                    lines,
                    title,
                    links
                };
            }
            """,
            part,
        )

        if not data:
            continue

        record = parse_vessel_data(data)

        if record:
            records.append(record)

    return records
