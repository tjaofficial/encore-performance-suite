document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("#dashboard-layout-form");
    const preview = document.querySelector("#dashboard-layout-preview");
    const hiddenInput = document.querySelector("#layout-json");
    const quickActionsInput = document.querySelector(
        "#quick-actions-json"
    );

    if (!form || !preview || !hiddenInput) {
        return;
    }

    const controls = document.querySelector("[data-active-controls]");
    const placeholder = document.querySelector(".layout-controls-placeholder");
    const selectedName = document.querySelector("[data-selected-card-name]");
    const status = document.querySelector("#layout-save-status");

    const labels = {};

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

    const cardIsLocked = (card) => (
        Boolean(card)
        && card.dataset.locked === "true"
    );

    const enabledCards = () => cardElements().filter(
        (card) => !card.hidden
    );

    const markDirty = () => {
        if (status) {
            status.textContent = "You have unsaved layout changes.";
        }
    };

    const serialize = () => {
        const cards = cardElements().map((card, index) => ({
            key: card.dataset.layoutCard,
            enabled: !card.hidden,
            order: index + 1,
            width: card.dataset.width,
            height: Number(card.dataset.height),
        }));

        hiddenInput.value = JSON.stringify({
            version: 1,
            cards,
        });
    };

    const serializeQuickActions = () => {
        if (!quickActionsInput) {
            return;
        }

        const actions = {};

        document.querySelectorAll(
            "[data-quick-action-enabled]"
        ).forEach((checkbox) => {
            actions[
                checkbox.dataset.quickActionEnabled
            ] = checkbox.checked;
        });

        quickActionsInput.value = JSON.stringify(
            actions
        );
    };

    const updateCardSizeLabel = (card) => {
        const label = card.querySelector(".preview-card-size");

        if (!label) {
            return;
        }

        label.textContent = (
            `${card.dataset.width} · `
            + `${card.dataset.height === "2" ? "2 rows" : "1 row"}`
        );
    };

    const refreshControls = () => {
        const locked = cardIsLocked(selectedCard);
        const fixedNote = document.querySelector(
            "[data-fixed-size-note]"
        );

        document.querySelectorAll(
            "[data-size-setting]"
        ).forEach((section) => {
            section.hidden = locked;
        });

        if (fixedNote) {
            fixedNote.hidden = !locked;
        }

        document.querySelectorAll("[data-width-choice]").forEach((button) => {
            button.classList.toggle(
                "active",
                Boolean(
                    selectedCard
                    && button.dataset.widthChoice === selectedCard.dataset.width
                )
            );
        });

        document.querySelectorAll("[data-height-choice]").forEach((button) => {
            button.classList.toggle(
                "active",
                Boolean(
                    selectedCard
                    && button.dataset.heightChoice === selectedCard.dataset.height
                )
            );
            button.disabled = Boolean(selectedCard && Number(button.dataset.heightChoice) < Number(selectedCard.dataset.minHeight || "1"));
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
            || cardIsLocked(selectedCard)
            || !["quarter", "half", "three_quarter", "full"].includes(width)
        ) {
            return;
        }

        const widthRank = {
            quarter: 1,
            half: 2,
            three_quarter: 3,
            full: 4,
        };

        const minWidth = (
            selectedCard.dataset.minWidth
            || "quarter"
        );

        if (
            widthRank[width]
            < widthRank[minWidth]
        ) {
            return;
        }

        selectedCard.classList.remove(
            "width-quarter",
            "width-half",
            "width-three_quarter",
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
            || cardIsLocked(selectedCard)
            || !["1", "2"].includes(height)
        ) {
            return;
        }

        const minHeight = Number(
            selectedCard.dataset.minHeight
            || "1"
        );

        if (Number(height) < minHeight) {
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

        let placeBefore;

        if (sameVisualRow) {
            placeBefore = (
                event.clientX
                < bounds.left + (bounds.width / 2)
            );
        } else {
            placeBefore = (
                event.clientY
                < bounds.top + (bounds.height / 2)
            );
        }

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

            card.classList.add(
                "is-dragging"
            );

            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = "move";

                try {
                    event.dataTransfer.setData(
                        "text/plain",
                        card.dataset.layoutCard
                    );
                } catch (error) {
                    // Some browsers do not require transferable text.
                }
            }
        });

        card.addEventListener("dragend", () => {
            card.classList.remove(
                "is-dragging"
            );

            draggedCard = null;

            serialize();
            markDirty();
        });

        card.querySelectorAll("[data-move]").forEach((button) => {
            button.addEventListener("click", () => {
                selectCard(card);

                moveCard(
                    card,
                    button.dataset.move
                );
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

        const target = event.target.closest(
            "[data-layout-card]"
        );

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

        draggedCard.classList.remove(
            "is-dragging"
        );

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

            if (!card) {
                return;
            }

            if (checkbox.checked) {
                card.hidden = false;
                card.removeAttribute("hidden");
            } else {
                card.hidden = true;
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

    document.querySelectorAll("[data-width-choice]").forEach((button) => {
        button.addEventListener("click", () => {
            setWidth(
                button.dataset.widthChoice
            );
        });
    });

    document.querySelectorAll("[data-height-choice]").forEach((button) => {
        button.addEventListener("click", () => {
            setHeight(
                button.dataset.heightChoice
            );
        });
    });

    document.querySelectorAll(
        "[data-quick-action-enabled]"
    ).forEach((checkbox) => {
        checkbox.addEventListener(
            "change",
            () => {
                serializeQuickActions();
                markDirty();
            }
        );
    });

    form.addEventListener("submit", (event) => {
        if (
            !event.submitter
            || event.submitter.value !== "reset"
        ) {
            serialize();
            serializeQuickActions();
        }
    });

    serialize();
    serializeQuickActions();
});
