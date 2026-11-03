document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector(
        "#dashboard-layout-form"
    );

    const hidden = document.querySelector(
        "#quick-links-json"
    );

    if (!form || !hidden) {
        return;
    }

    const status = document.querySelector(
        "#layout-save-status"
    );

    const customRows = Array.from(
        document.querySelectorAll(
            "[data-custom-quick-link-row]"
        )
    );

    const addCustomLinkButton = document.querySelector(
        "[data-add-custom-quick-link]"
    );

    /*
     * Always begin with two custom shortcut slots visible.
     * Rows 3 and 4 remain visible only when they already contain
     * saved values. Otherwise the user reveals them with + Add Link.
     */
    customRows.forEach((row, index) => {
        if (index < 2) {
            row.hidden = false;
            return;
        }

        const labelInput = row.querySelector(
            "[data-custom-quick-link-label]"
        );
        const urlInput = row.querySelector(
            "[data-custom-quick-link-url]"
        );

        const hasSavedValue = Boolean(
            (labelInput && labelInput.value.trim())
            || (urlInput && urlInput.value.trim())
        );

        row.hidden = !hasSavedValue;
    });

    const updateShortcutPreview = (row) => {
        const label = row.querySelector("[data-custom-quick-link-label]")?.value.trim() || "New shortcut";
        const iconSelect = row.querySelector("[data-custom-quick-link-icon]");
        const iconLabel = iconSelect?.selectedOptions[0]?.textContent.trim() || "Link";
        const previewLabel = row.querySelector("[data-custom-quick-link-preview-label]");
        const previewIcon = row.querySelector("[data-custom-quick-link-preview-icon]");
        if (previewLabel) previewLabel.textContent = label;
        if (previewIcon) {
            const symbols = {"calendar-days":"▦","music-2":"♫","video":"▶","users":"♧","home":"⌂","star":"★","heart":"♥","clock-3":"◷","bell":"♧","key-round":"⚿","shirt":"♙","settings":"⚙"};
            previewIcon.textContent = symbols[iconSelect?.value] || "↗";
            previewIcon.title = iconLabel;
        }
    };

    customRows.forEach((row) => {
        updateShortcutPreview(row);
        row.querySelector("[data-custom-quick-link-clear]")?.addEventListener("click", () => {
            row.querySelector("[data-custom-quick-link-label]").value = "";
            row.querySelector("[data-custom-quick-link-url]").value = "";
            row.querySelector("[data-custom-quick-link-icon]").value = "external-link";
            updateShortcutPreview(row);
            serializeQuickLinks();
            markDirty();
        });
        row.querySelectorAll("input,select").forEach((field) => {
            field.addEventListener("input", () => updateShortcutPreview(row));
            field.addEventListener("change", () => updateShortcutPreview(row));
        });
    });

    const refreshCustomLinkButton = () => {
        if (!addCustomLinkButton) {
            return;
        }

        addCustomLinkButton.hidden = (
            customRows.every((row) => !row.hidden)
        );
    };

    const markDirty = () => {
        if (status) {
            status.textContent = (
                "You have unsaved layout changes."
            );
        }
    };

    const serializeQuickLinks = () => {
        const enabled = {};

        document.querySelectorAll(
            "[data-quick-link-enabled]"
        ).forEach((checkbox) => {
            enabled[
                checkbox.dataset.quickLinkEnabled
            ] = checkbox.checked;
        });

        const labels = Array.from(
            document.querySelectorAll(
                "[data-custom-quick-link-label]"
            )
        );

        const urls = Array.from(
            document.querySelectorAll(
                "[data-custom-quick-link-url]"
            )
        );

        const icons = Array.from(document.querySelectorAll("[data-custom-quick-link-icon]"));
        const custom = labels.map(
            (input, index) => ({
                label: input.value.trim(),
                icon: icons[index] ? icons[index].value : "external-link",
                url: (
                    urls[index]
                    ? urls[index].value.trim()
                    : ""
                ),
            })
        );

        hidden.value = JSON.stringify({
            enabled,
            custom,
        });
    };

    document.querySelectorAll(
        "[data-quick-link-enabled], "
        + "[data-custom-quick-link-label], "
        + "[data-custom-quick-link-url], "
        + "[data-custom-quick-link-icon]"
    ).forEach((field) => {
        field.addEventListener(
            "change",
            () => {
                serializeQuickLinks();
                markDirty();
            }
        );

        field.addEventListener(
            "input",
            () => {
                serializeQuickLinks();
                markDirty();
            }
        );
    });

    if (addCustomLinkButton) {
        addCustomLinkButton.addEventListener(
            "click",
            () => {
                const nextHiddenRow = customRows.find(
                    (row) => row.hidden
                );

                if (!nextHiddenRow) {
                    refreshCustomLinkButton();
                    return;
                }

                nextHiddenRow.hidden = false;

                const firstInput = nextHiddenRow.querySelector(
                    "input"
                );

                if (firstInput) {
                    firstInput.focus();
                }

                serializeQuickLinks();
                markDirty();
                refreshCustomLinkButton();
            }
        );
    }

    form.addEventListener(
        "submit",
        (event) => {
            if (
                !event.submitter
                || event.submitter.value !== "reset"
            ) {
                serializeQuickLinks();
            }
        }
    );

    serializeQuickLinks();
    refreshCustomLinkButton();
});
