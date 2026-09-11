document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("#dashboard-layout-form");
    const preview = document.querySelector("#dashboard-layout-preview");
    const hiddenInput = document.querySelector("#layout-json");

    if (!form || !preview || !hiddenInput) {
        return;
    }

    const controls = document.querySelector("[data-active-controls]");
    const placeholder = document.querySelector(".layout-controls-placeholder");
    const selectedName = document.querySelector("[data-selected-card-name]");
    const lockedNote = document.querySelector("[data-locked-card-note]");
    const sizeSettings = Array.from(
        document.querySelectorAll("[data-size-setting]")
    );
    const status = document.querySelector("#layout-save-status");
    const snapshotCount = document.querySelector("#snapshot-selection-count");
    const snapshotError = document.querySelector("#snapshot-selection-error");

    const labels = {
        studio_snapshot: "Studio Snapshot",
    };

    document.querySelectorAll("[data-card-choice]").forEach((choice) => {
        const key = choice.dataset.cardChoice;
        const strong = choice.querySelector("strong");

        labels[key] = strong
            ? strong.textContent.trim()
            : key;
    });

    let selectedCard = null;
    let draggedCard = null;

    const cardElements = () => Array.from(
        preview.querySelectorAll("[data-layout-card]")
    );

    const enabledCards = () => cardElements().filter(
        (card) => !card.hidden
    );

    const snapshotCheckboxes = () => Array.from(
        document.querySelectorAll("[data-snapshot-metric]")
    );

    const selectedSnapshotMetrics = () => snapshotCheckboxes()
        .filter((checkbox) => checkbox.checked)
        .map((checkbox) => checkbox.dataset.snapshotMetric);


    const selectedQuickLinks = () => Array.from(
        document.querySelectorAll("[data-admin-quick-link]")
    )
        .filter((checkbox) => checkbox.checked)
        .map((checkbox) => checkbox.dataset.adminQuickLink);

    const customQuickLinks = () => {
        const labels = Array.from(
            document.querySelectorAll("[data-custom-link-label]")
        );
        const urls = Array.from(
            document.querySelectorAll("[data-custom-link-url]")
        );

        return labels.map((input, index) => ({
            label: input.value.trim(),
            url: urls[index] ? urls[index].value.trim() : "",
        })).filter((item) => item.label && item.url);
    };

    const markDirty = () => {
        if (status) {
            status.textContent = "You have unsaved layout changes.";
        }
    };

    const updateSnapshotCount = () => {
        const count = selectedSnapshotMetrics().length;

        if (snapshotCount) {
            snapshotCount.textContent = `${count} / 6 selected`;
        }

        if (snapshotError) {
            snapshotError.hidden = count > 0;
        }
    };

    const serialize = () => {
        const cards = cardElements().map((card, index) => ({
            key: card.dataset.layoutCard,
            enabled: (
                card.dataset.locked === "true"
                    ? true
                    : !card.hidden
            ),
            order: index + 1,
            width: (
                card.dataset.locked === "true"
                    ? "full"
                    : card.dataset.width
            ),
            height: (
                card.dataset.locked === "true"
                    ? 1
                    : Number(card.dataset.height)
            ),
        }));

        hiddenInput.value = JSON.stringify({
            version: 3,
            snapshot_metrics: selectedSnapshotMetrics(),
            quick_links: selectedQuickLinks(),
            custom_quick_links: customQuickLinks(),
            cards,
        });
    };

    const updateCardSizeLabel = (card) => {
        const label = card.querySelector(".preview-card-size");

        if (!label) {
            return;
        }

        if (card.dataset.locked === "true") {
            label.textContent = "Fixed · Full · 1 row";
            return;
        }

        label.textContent = (
            `${card.dataset.width} · `
            + `${card.dataset.height === "2" ? "2 rows" : "1 row"}`
        );
    };

    const refreshControls = () => {
        const locked = Boolean(
            selectedCard
            && selectedCard.dataset.locked === "true"
        );

        if (lockedNote) {
            lockedNote.hidden = !locked;
        }

        sizeSettings.forEach((setting) => {
            setting.hidden = locked;
        });

        document.querySelectorAll("[data-admin-quick-link]").forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            serialize();
            markDirty();
        });
    });

    document.querySelectorAll(
        "[data-custom-link-label], [data-custom-link-url]"
    ).forEach((input) => {
        input.addEventListener("input", () => {
            serialize();
            markDirty();
        });
    });

    document.querySelectorAll("[data-width-choice]").forEach((button) => {
            button.classList.toggle(
                "active",
                Boolean(
                    selectedCard
                    && !locked
                    && button.dataset.widthChoice === selectedCard.dataset.width
                )
            );
        });

        document.querySelectorAll("[data-height-choice]").forEach((button) => {
            button.classList.toggle(
                "active",
                Boolean(
                    selectedCard
                    && !locked
                    && button.dataset.heightChoice === selectedCard.dataset.height
                )
            );
        });
    };

    const selectCard = (card) => {
        cardElements().forEach((item) => {
            item.classList.toggle(
                "is-selected",
                item === card
            );
        });

        selectedCard = card;

        if (!selectedCard) {
            if (controls) {
                controls.hidden = true;
            }

            if (placeholder) {
                placeholder.hidden = false;
            }

            return;
        }

        if (controls) {
            controls.hidden = false;
        }

        if (placeholder) {
            placeholder.hidden = true;
        }

        if (selectedName) {
            selectedName.textContent = (
                labels[selectedCard.dataset.layoutCard]
                || selectedCard.dataset.layoutCard
            );
        }

        refreshControls();
    };

    const setWidth = (width) => {
        if (
            !selectedCard
            || selectedCard.dataset.locked === "true"
            || !["quarter", "half", "full"].includes(width)
        ) {
            return;
        }

        selectedCard.classList.remove(
            "width-quarter",
            "width-half",
            "width-full"
        );

        selectedCard.classList.add(
            `width-${width}`
        );

        selectedCard.dataset.width = width;

        updateCardSizeLabel(selectedCard);
        refreshControls();
        serialize();
        markDirty();
    };

    const setHeight = (height) => {
        if (
            !selectedCard
            || selectedCard.dataset.locked === "true"
            || !["1", "2"].includes(height)
        ) {
            return;
        }

        selectedCard.classList.remove(
            "height-1",
            "height-2"
        );

        selectedCard.classList.add(
            `height-${height}`
        );

        selectedCard.dataset.height = height;

        updateCardSizeLabel(selectedCard);
        refreshControls();
        serialize();
        markDirty();
    };

    const moveCard = (card, direction) => {
        const visible = enabledCards();
        const index = visible.indexOf(card);

        if (index < 0) {
            return;
        }

        if (
            direction === "up"
            && index > 0
        ) {
            preview.insertBefore(
                card,
                visible[index - 1]
            );
        }

        if (
            direction === "down"
            && index < visible.length - 1
        ) {
            const next = visible[index + 1];

            preview.insertBefore(
                card,
                next.nextSibling
            );
        }

        serialize();
        markDirty();
    };

    const insertDraggedRelativeTo = (
        dragged,
        target,
        event
    ) => {
        const bounds = target.getBoundingClientRect();

        const sameVisualRow = (
            event.clientY >= bounds.top
            && event.clientY <= bounds.bottom
        );

        const placeBefore = sameVisualRow
            ? event.clientX < bounds.left + (bounds.width / 2)
            : event.clientY < bounds.top + (bounds.height / 2);

        if (placeBefore) {
            if (target.previousElementSibling !== dragged) {
                preview.insertBefore(
                    dragged,
                    target
                );
            }
        } else if (target.nextElementSibling !== dragged) {
            preview.insertBefore(
                dragged,
                target.nextSibling
            );
        }
    };

    cardElements().forEach((card) => {
        card.addEventListener("click", (event) => {
            if (event.target.closest("button")) {
                return;
            }

            selectCard(card);
        });

        card.addEventListener("focus", () => {
            selectCard(card);
        });

        card.addEventListener("dragstart", (event) => {
            draggedCard = card;
            card.classList.add("is-dragging");

            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = "move";

                try {
                    event.dataTransfer.setData(
                        "text/plain",
                        card.dataset.layoutCard
                    );
                } catch {}
            }
        });

        card.addEventListener("dragend", () => {
            card.classList.remove("is-dragging");
            draggedCard = null;
            serialize();
            markDirty();
        });

        card.querySelectorAll("[data-move]").forEach((button) => {
            button.addEventListener("click", () => {
                selectCard(card);
                moveCard(card, button.dataset.move);
            });
        });
    });

    preview.addEventListener("dragover", (event) => {
        event.preventDefault();

        if (!draggedCard) {
            return;
        }

        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = "move";
        }

        const target = event.target.closest("[data-layout-card]");

        if (
            !target
            || target === draggedCard
            || target.hidden
        ) {
            return;
        }

        insertDraggedRelativeTo(
            draggedCard,
            target,
            event
        );
    });

    preview.addEventListener("drop", (event) => {
        event.preventDefault();

        if (!draggedCard) {
            return;
        }

        draggedCard.classList.remove("is-dragging");
        selectCard(draggedCard);
        serialize();
        markDirty();
    });

    document.querySelectorAll("[data-card-enabled]").forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            const key = checkbox.dataset.cardEnabled;
            const card = preview.querySelector(
                `[data-layout-card="${key}"]`
            );

            if (!card || card.dataset.locked === "true") {
                return;
            }

            card.hidden = !checkbox.checked;

            if (checkbox.checked) {
                card.removeAttribute("hidden");
            } else {
                card.setAttribute("hidden", "");
            }

            if (
                selectedCard === card
                && card.hidden
            ) {
                selectCard(null);
            }

            serialize();
            markDirty();
        });
    });

    snapshotCheckboxes().forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
            const selected = selectedSnapshotMetrics();

            if (selected.length === 0) {
                checkbox.checked = true;
            }

            updateSnapshotCount();
            serialize();
            markDirty();
        });
    });

    document.querySelectorAll("[data-width-choice]").forEach((button) => {
        button.addEventListener("click", () => {
            setWidth(button.dataset.widthChoice);
        });
    });

    document.querySelectorAll("[data-height-choice]").forEach((button) => {
        button.addEventListener("click", () => {
            setHeight(button.dataset.heightChoice);
        });
    });

    form.addEventListener("submit", (event) => {
        if (
            !event.submitter
            || event.submitter.value !== "reset"
        ) {
            if (selectedSnapshotMetrics().length === 0) {
                event.preventDefault();

                if (snapshotError) {
                    snapshotError.hidden = false;
                }

                return;
            }

            serialize();
        }
    });

    updateSnapshotCount();
    serialize();
});
