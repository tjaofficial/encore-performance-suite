document.addEventListener("DOMContentLoaded", () => {
    const roster = document.querySelector("[data-measurement-roster]");

    if (!roster) {
        return;
    }

    const cards = Array.from(
        roster.querySelectorAll("[data-measurement-card]")
    );

    const search = document.querySelector("[data-measurement-search]");
    const filterButtons = Array.from(
        document.querySelectorAll("[data-filter]")
    );

    let activeFilter = new URLSearchParams(
        window.location.search
    ).get("filter") || "all";

    const csrf = () => {
        const item = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith("csrftoken="));

        return item
            ? decodeURIComponent(item.split("=")[1])
            : "";
    };

    const post = async (url, values = {}) => {
        const body = new URLSearchParams(values);

        const response = await fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrf(),
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body,
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Unable to save."
            );
        }

        return data;
    };

    const cardName = (card) => (
        card.dataset.studentName || ""
    );

    const refreshVisibility = () => {
        const query = (
            search ? search.value.trim().toLowerCase() : ""
        );

        cards.forEach((card) => {
            const matchesSearch = (
                !query
                || cardName(card).includes(query)
            );

            const matchesFilter = (
                activeFilter === "all"
                || card.dataset.state === activeFilter
            );

            card.hidden = !(
                matchesSearch
                && matchesFilter
            );
        });

        filterButtons.forEach((button) => {
            button.classList.toggle(
                "active",
                button.dataset.filter === activeFilter
            );
        });
    };

    const setState = (
        card,
        state,
        label,
    ) => {
        [
            "not_started",
            "in_progress",
            "complete",
            "needs_remeasurement",
        ].forEach((item) => {
            card.classList.remove(
                `state-${item}`
            );
        });

        card.dataset.state = state;
        card.classList.add(
            `state-${state}`
        );

        const labelEl = card.querySelector(
            "[data-state-label]"
        );

        if (labelEl) {
            labelEl.textContent = label;
        }

        const icon = card.querySelector(
            ".measurement-status-icon"
        );

        if (icon) {
            icon.textContent = (
                state === "complete"
                    ? "✓"
                    : state === "needs_remeasurement"
                        ? "!"
                        : state === "in_progress"
                            ? "…"
                            : "○"
            );
        }
    };

    const nextVisibleCard = (card) => {
        const index = cards.indexOf(card);

        for (
            let i = index + 1;
            i < cards.length;
            i += 1
        ) {
            if (!cards[i].hidden) {
                return cards[i];
            }
        }

        return null;
    };

    const openCard = (card) => {
        const body = card.querySelector(
            "[data-measurement-body]"
        );

        if (body) {
            body.hidden = false;
            card.classList.add("expanded");
        }
    };

    const closeCard = (card) => {
        const body = card.querySelector(
            "[data-measurement-body]"
        );

        if (body) {
            body.hidden = true;
            card.classList.remove("expanded");
        }
    };

    const wireCard = (card) => {
        const toggle = card.querySelector(
            "[data-measurement-toggle]"
        );

        const saveState = card.querySelector(
            "[data-save-state]"
        );

        const editPanel = card.querySelector(
            "[data-edit-panel]"
        );

        const currentSummary = card.querySelector(
            "[data-current-summary]"
        );

        const completeButton = card.querySelector(
            "[data-complete-measurements]"
        );

        const startNewButton = card.querySelector(
            "[data-start-new-measurements]"
        );

        const timers = new Map();

        if (toggle) {
            toggle.addEventListener("click", () => {
                const body = card.querySelector(
                    "[data-measurement-body]"
                );

                if (!body) {
                    return;
                }

                body.hidden
                    ? openCard(card)
                    : closeCard(card);
            });
        }

        card.querySelectorAll(
            "[data-measurement-field]"
        ).forEach((input) => {
            const saveField = async () => {
                if (saveState) {
                    saveState.textContent = "Saving…";
                }

                try {
                    await post(
                        card.dataset.saveUrl,
                        {
                            field: input.dataset.measurementField,
                            value: input.value,
                        }
                    );

                    setState(
                        card,
                        "in_progress",
                        "In Progress · Autosaved"
                    );

                    if (saveState) {
                        saveState.textContent = "Saved";
                    }
                } catch (error) {
                    if (saveState) {
                        saveState.textContent = error.message;
                        saveState.classList.add("error");
                    }
                }
            };

            input.addEventListener("input", () => {
                const existing = timers.get(input);

                if (existing) {
                    window.clearTimeout(existing);
                }

                timers.set(
                    input,
                    window.setTimeout(
                        saveField,
                        450
                    )
                );
            });

            input.addEventListener(
                "change",
                saveField
            );
        });

        if (startNewButton) {
            startNewButton.addEventListener(
                "click",
                async () => {
                    startNewButton.disabled = true;

                    try {
                        await post(
                            card.dataset.newUrl
                        );

                        card.querySelectorAll(
                            "[data-measurement-field]"
                        ).forEach((input) => {
                            input.value = "";
                        });

                        if (currentSummary) {
                            currentSummary.hidden = true;
                        }

                        if (editPanel) {
                            editPanel.hidden = false;
                        }

                        setState(
                            card,
                            "not_started",
                            "New Measurement Set"
                        );

                        const firstInput = card.querySelector(
                            "[data-measurement-field]"
                        );

                        if (firstInput) {
                            firstInput.focus();
                        }
                    } catch (error) {
                        window.alert(error.message);
                    } finally {
                        startNewButton.disabled = false;
                    }
                }
            );
        }

        if (completeButton) {
            completeButton.addEventListener(
                "click",
                async () => {
                    completeButton.disabled = true;

                    try {
                        await post(
                            card.dataset.completeUrl
                        );

                        setState(
                            card,
                            "complete",
                            "Complete · Just measured"
                        );

                        closeCard(card);

                        const count = document.querySelector(
                            "[data-complete-count]"
                        );

                        if (count) {
                            count.textContent = String(
                                Number.parseInt(
                                    count.textContent,
                                    10
                                ) + 1
                            );
                        }

                        const next = nextVisibleCard(card);

                        if (next) {
                            openCard(next);

                            next.scrollIntoView({
                                behavior: "smooth",
                                block: "center",
                            });

                            const firstInput = next.querySelector(
                                "[data-measurement-field]"
                            );

                            if (firstInput) {
                                window.setTimeout(
                                    () => firstInput.focus(),
                                    350
                                );
                            }
                        }
                    } catch (error) {
                        if (saveState) {
                            saveState.textContent = error.message;
                            saveState.classList.add("error");
                        }
                    } finally {
                        completeButton.disabled = false;
                    }
                }
            );
        }
    };

    cards.forEach(wireCard);

    if (search) {
        search.addEventListener(
            "input",
            refreshVisibility
        );
    }

    filterButtons.forEach((button) => {
        button.addEventListener("click", () => {
            activeFilter = button.dataset.filter;
            refreshVisibility();
        });
    });

    refreshVisibility();
});
