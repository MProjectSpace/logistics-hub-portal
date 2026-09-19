# ============================================================
# EXTRACT CARD DIRECTLY FROM DOM
# ============================================================

async def extract_card_data(card):
    """
    Membaca satu .vcard dari HTML baru.

    Struktur yang dibaca:

    .nm-txt          -> Vessel Name
    .vid             -> Vessel Code
    .vtag            -> Type
    .vmeta           -> Voyage
    .vmeta-agent     -> Shipping Line / Agent
    .vt-lab/.vt-val  -> ETB, ATB, ATD, EXP, IMP
    .vacts            -> Detail ID / History ID
    """

    try:

        return await card.evaluate(
            """
            (card) => {

                const clean = (value) => {

                    if (
                        value === null ||
                        value === undefined
                    ) {
                        return "";
                    }

                    return String(value)
                        .replace(/\\u00a0/g, " ")
                        .replace(/\\s+/g, " ")
                        .trim();
                };


                // =========================================
                // VESSEL NAME
                // =========================================

                const nameEl =
                    card.querySelector(".vname .nm-txt");

                const vesselName =
                    clean(
                        nameEl
                            ? nameEl.textContent
                            : ""
                    );


                // =========================================
                // VESSEL CODE
                // =========================================

                const codeEl =
                    card.querySelector(".vsub .vid");

                let vesselCode =
                    clean(
                        codeEl
                            ? codeEl.textContent
                            : ""
                    );

                vesselCode =
                    vesselCode
                        .replace(/^\\(/, "")
                        .replace(/\\)$/, "")
                        .trim();


                // =========================================
                // TYPE
                // =========================================

                const typeEl =
                    card.querySelector(".vsub .vtag");

                const type =
                    clean(
                        typeEl
                            ? typeEl.textContent
                            : ""
                    );


                // =========================================
                // VOYAGE
                // =========================================
                //
                // .vmeta pertama = voyage
                // .vmeta-agent = shipping line
                //
                // Jadi agent tidak ikut masuk voyage.
                // =========================================

                const voyageEl =
                    card.querySelector(
                        ".vmeta:not(.vmeta-agent)"
                    );

                const voyage =
                    clean(
                        voyageEl
                            ? voyageEl.textContent
                            : ""
                    );


                // =========================================
                // AGENT / SHIPPING LINE
                // =========================================

                const agentEl =
                    card.querySelector(
                        ".vmeta-agent span"
                    );

                const agent =
                    clean(
                        agentEl
                            ? agentEl.textContent
                            : ""
                    );


                // =========================================
                // TIMES
                // =========================================

                const timeLabels = [
                    ...card.querySelectorAll(
                        ".vtimes .vt-lab"
                    )
                ].map(
                    el => clean(el.textContent)
                );


                const timeValues = [
                    ...card.querySelectorAll(
                        ".vtimes .vt-val"
                    )
                ].map(
                    el => clean(el.textContent)
                );


                // =========================================
                // PROGRESS
                // =========================================

                const progressEl =
                    card.querySelector(
                        ".vprog .pnum"
                    );

                const progress =
                    clean(
                        progressEl
                            ? progressEl.textContent
                            : ""
                    );


                // =========================================
                // DETAIL ID
                // =========================================

                let detailId = "";

                const detailLinks = [
                    ...card.querySelectorAll(".vacts a")
                ];

                const detailLink =
                    detailLinks.find(
                        a => {

                            const onclick =
                                a.getAttribute(
                                    "onclick"
                                ) || "";

                            return onclick.includes(
                                "waCardDetail"
                            );
                        }
                    );


                if (detailLink) {

                    const onclick =
                        detailLink.getAttribute(
                            "onclick"
                        ) || "";

                    const match =
                        onclick.match(
                            /waCardDetail\\s*\\(\\s*['"]([^'"]+)['"]\\s*\\)/
                        );

                    if (match) {

                        detailId =
                            clean(
                                match[1]
                            );
                    }
                }


                // =========================================
                // HISTORY ID
                // =========================================

                let historyId = "";

                const historyLink =
                    detailLinks.find(
                        a => {

                            const onclick =
                                a.getAttribute(
                                    "onclick"
                                ) || "";

                            return onclick.includes(
                                "waCardHistory"
                            );
                        }
                    );


                if (historyLink) {

                    const onclick =
                        historyLink.getAttribute(
                            "onclick"
                        ) || "";

                    const match =
                        onclick.match(
                            /waCardHistory\\s*\\(\\s*['"]([^'"]+)['"]\\s*\\)/
                        );

                    if (match) {

                        historyId =
                            clean(
                                match[1]
                            );
                    }
                }


                // =========================================
                // RETURN DATA
                // =========================================

                return {

                    vesselName,
                    vesselCode,
                    type,
                    voyage,
                    agent,

                    timeLabels,
                    timeValues,

                    progress,

                    detailId,
                    historyId
                };
            }
            """
        )

    except Exception as e:

        logging.warning(
            "Gagal membaca vessel card: %s",
            e,
        )

        return None
