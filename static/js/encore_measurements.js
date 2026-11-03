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

    const renderConversions = (card, conversions) => {
        const host = card.querySelector("[data-conversion-results]");
        if (!host) return;
        if (!conversions || !conversions.length) {
            host.innerHTML = '<p class="muted-copy">Enter measurements to see vendor chart conversions.</p>';
            return;
        }
        host.innerHTML = conversions.map((item) => {
            const chips = item.charts && item.charts.length
                ? item.charts.map((chart) => `<span class="conversion-chip"><b>${chart.chart}</b> ${chart.size}</span>`).join("")
                : '<span class="conversion-none">No matching chart size</span>';
            return `<div class="conversion-measurement-row" data-conversion-field="${item.field}"><strong>${item.label}</strong><span>${item.value}</span><div>${chips}</div></div>`;
        }).join("");
    };

    const applyValues = (card, values) => {
        if (!values) return;
        card.querySelectorAll("[data-measurement-field]").forEach((input) => {
            const key = input.dataset.measurementField;
            if (Object.prototype.hasOwnProperty.call(values, key)) input.value = values[key] ?? "";
        });
    };

    const updateCurrentSummary = (card, values) => {
        if (!values) return;

        card.querySelectorAll("[data-current-value]").forEach((output) => {
            const key = output.dataset.currentValue;
            if (!Object.prototype.hasOwnProperty.call(values, key)) return;

            const value = values[key];
            output.textContent = (value === null || value === undefined || value === "")
                ? "—"
                : value;
        });

        const startButton = card.querySelector("[data-start-new-measurements]");
        if (startButton) {
            startButton.textContent = "Update Measurements";
        }
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
        const cancelButton = card.querySelector("[data-cancel-measurements]");

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
                    const result = await post(
                        card.dataset.saveUrl,
                        {
                            field: input.dataset.measurementField,
                            value: input.value,
                            vendor_id: card.dataset.vendorId || "",
                        }
                    );
                    renderConversions(card, result.conversions);

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
                        const result = await post(card.dataset.newUrl);
                        applyValues(card, result.values);

                        if (currentSummary) {
                            currentSummary.hidden = true;
                        }

                        if (editPanel) {
                            editPanel.hidden = false;
                        }

                        setState(card, "in_progress", "Updating Measurements · Autosaved");

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

        if (cancelButton) {
            cancelButton.addEventListener("click", async () => {
                cancelButton.disabled = true;
                try {
                    const result = await post(card.dataset.cancelUrl);
                    applyValues(card, result.values);
                    if (editPanel) editPanel.hidden = true;
                    if (currentSummary) currentSummary.hidden = false;
                    const label = result.has_current ? "Complete" : "Not Started";
                    setState(card, result.state || (result.has_current ? "complete" : "not_started"), label);
                } catch (error) { window.alert(error.message); }
                finally { cancelButton.disabled = false; }
            });
        }

        if (completeButton) {
            completeButton.addEventListener(
                "click",
                async () => {
                    completeButton.disabled = true;

                    try {
                        const result = await post(
                            card.dataset.completeUrl,
                            {
                                vendor_id: card.dataset.vendorId || "",
                            }
                        );

                        applyValues(card, result.values);
                        updateCurrentSummary(card, result.values);
                        renderConversions(card, result.conversions);

                        if (editPanel) {
                            editPanel.hidden = true;
                        }

                        if (currentSummary) {
                            currentSummary.hidden = false;
                        }

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
