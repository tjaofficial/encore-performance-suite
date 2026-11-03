document.addEventListener("DOMContentLoaded", () => {
    const dropInToggle = document.getElementById("id_allow_drop_ins");
    const dropInPrice = document.getElementById("id_drop_in_price");

    if (dropInToggle && dropInPrice) {
        const syncDropInPrice = () => {
            dropInPrice.disabled = !dropInToggle.checked;

            if (!dropInToggle.checked) {
                dropInPrice.value = "";
            }
        };

        dropInToggle.addEventListener("change", syncDropInPrice);
        syncDropInPrice();
    }

    const parseScriptJson = (id, fallback) => {
        const node = document.getElementById(id);
        if (!node) return fallback;

        try {
            return JSON.parse(node.textContent);
        } catch (_) {
            return fallback;
        }
    };

    const bulkBar = document.querySelector("[data-class-bulk-bar]");
    const selectedCountNodes = document.querySelectorAll("[data-selected-count]");
    const modalSelectedCountNodes = document.querySelectorAll("[data-modal-selected-count]");
    const selectedIdsInput = document.querySelector("[data-selected-class-ids]");
    const selectAll = document.querySelector("[data-select-all-classes]");
    const classCheckboxes = Array.from(document.querySelectorAll("[data-class-select]"));

    const selectedClassIds = () => (
        classCheckboxes
            .filter((checkbox) => checkbox.checked)
            .map((checkbox) => checkbox.value)
    );

    const syncSelection = () => {
        const ids = selectedClassIds();
        const count = ids.length;

        selectedCountNodes.forEach((node) => {
            node.textContent = count;
        });

        modalSelectedCountNodes.forEach((node) => {
            node.textContent = count;
        });

        if (selectedIdsInput) {
            selectedIdsInput.value = JSON.stringify(ids);
        }

        if (bulkBar) {
            bulkBar.hidden = count === 0;
        }

        if (selectAll) {
            selectAll.checked = (
                classCheckboxes.length > 0
                && count === classCheckboxes.length
            );
            selectAll.indeterminate = (
                count > 0
                && count < classCheckboxes.length
            );
        }
    };

    classCheckboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", syncSelection);
    });

    if (selectAll) {
        selectAll.addEventListener("change", () => {
            classCheckboxes.forEach((checkbox) => {
                checkbox.checked = selectAll.checked;
            });
            syncSelection();
        });
    }

    const clearSelection = document.querySelector("[data-clear-class-selection]");
    if (clearSelection) {
        clearSelection.addEventListener("click", () => {
            classCheckboxes.forEach((checkbox) => {
                checkbox.checked = false;
            });
            syncSelection();
        });
    }

    const bulkModal = document.querySelector("[data-class-bulk-modal]");
    const openBulk = document.querySelector("[data-open-class-bulk-edit]");

    const setModalOpen = (modal, open) => {
        if (!modal) return;
        modal.hidden = !open;
        document.body.classList.toggle(
            "class-manager-modal-open",
            open
        );
    };

    if (openBulk && bulkModal) {
        openBulk.addEventListener("click", () => {
            if (!selectedClassIds().length) return;
            syncSelection();
            setModalOpen(bulkModal, true);
        });

        bulkModal.querySelectorAll("[data-close-class-bulk-edit]").forEach((button) => {
            button.addEventListener("click", () => {
                setModalOpen(bulkModal, false);
            });
        });
    }

    const bulkFields = parseScriptJson("class-bulk-edit-fields", []);
    const bulkFieldSelect = document.querySelector("[data-bulk-field]");
    const bulkValueControl = document.querySelector("[data-bulk-value-control]");

    const buildBulkValueControl = () => {
        if (!bulkFieldSelect || !bulkValueControl) return;

        const config = bulkFields.find(
            (item) => item.key === bulkFieldSelect.value
        );

        bulkValueControl.innerHTML = "";

        if (!config) {
            bulkValueControl.innerHTML = "<small>Choose a field first.</small>";
            return;
        }

        let input;

        if (config.input === "select") {
            input = document.createElement("select");
            input.name = "value";
            input.required = true;

            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "Choose a value…";
            input.appendChild(placeholder);

            (config.choices || []).forEach((choice) => {
                const option = document.createElement("option");
                option.value = choice.value;
                option.textContent = choice.label;
                input.appendChild(option);
            });
        } else {
            input = document.createElement("input");
            input.name = "value";

            if (config.input === "text") {
                input.type = "text";
                input.required = true;
                input.placeholder = "Enter the new class name";
            } else if (config.input === "date_or_blank") {
                input.type = "date";
                input.required = false;
            } else {
                input.type = "number";
                input.required = config.input !== "number_or_blank";

                if (config.min !== undefined) {
                    input.min = config.min;
                }
                if (config.step !== undefined) {
                    input.step = config.step;
                }

                if (config.input === "number_or_blank") {
                    input.placeholder = "Leave blank to clear this field";
                }
            }
        }

        input.classList.add("encore-input");
        bulkValueControl.appendChild(input);
    };

    const standardNameOption = document.querySelector(
        "[data-standard-name-option]"
    );

    const syncStandardNameOption = () => {
        if (!standardNameOption || !bulkFieldSelect) return;

        const show = ["class_type", "level"].includes(
            bulkFieldSelect.value
        );
        standardNameOption.hidden = !show;

        if (!show) {
            const checkbox = standardNameOption.querySelector(
                'input[name="standardize_name"]'
            );
            if (checkbox) checkbox.checked = false;
        }
    };

    if (bulkFieldSelect) {
        bulkFieldSelect.addEventListener("change", () => {
            buildBulkValueControl();
            syncStandardNameOption();
        });
    }

    if (bulkModal) {
        bulkModal.addEventListener("submit", () => {
            const fieldConfig = bulkFields.find(
                (item) => item.key === (
                    bulkFieldSelect
                    ? bulkFieldSelect.value
                    : ""
                )
            );

            const valueInput = bulkModal.querySelector('[name="value"]');

            if (
                fieldConfig
                && ["number_or_blank", "date_or_blank"].includes(
                    fieldConfig.input
                )
                && valueInput
                && valueInput.value === ""
            ) {
                valueInput.value = "__blank__";
            }

            syncSelection();
        });
    }

    const deleteModal = document.querySelector("[data-class-delete-modal]");
    const deleteSelectedButton = document.querySelector("[data-open-class-delete-selected]");
    const deleteInput = document.querySelector("[data-delete-class-ids]");
    const deletePreview = document.querySelector("[data-delete-preview]");
    const deleteCount = document.querySelector("[data-delete-count]");
    const deleteDescription = document.querySelector("[data-delete-description]");
    const deleteAcknowledgment = document.querySelector("[data-confirm-class-delete]");
    const submitDelete = document.querySelector("[data-submit-class-delete]");

    const openDeleteConfirmation = (items) => {
        if (!deleteModal || !items.length) return;
        const deduped = [...new Map(items.map((item) => [String(item.id), item])).values()];
        if (deleteInput) deleteInput.value = JSON.stringify(deduped.map((item) => item.id));
        if (deleteCount) deleteCount.textContent = deduped.length;
        if (deleteDescription) deleteDescription.textContent =
            `You selected ${deduped.length} class${deduped.length === 1 ? "" : "es"}. Review before deleting.`;
        if (deletePreview) {
            deletePreview.replaceChildren();
            deduped.slice(0, 12).forEach((item) => {
                const entry = document.createElement("div");
                entry.textContent = `${item.name} · ${item.season}`;
                deletePreview.appendChild(entry);
            });
            if (deduped.length > 12) {
                const more = document.createElement("small");
                more.textContent = `And ${deduped.length - 12} more selected classes`;
                deletePreview.appendChild(more);
            }
        }
        if (deleteAcknowledgment) deleteAcknowledgment.checked = false;
        if (submitDelete) submitDelete.disabled = true;
        setModalOpen(deleteModal, true);
    };

    if (deleteSelectedButton) {
        deleteSelectedButton.addEventListener("click", () => {
            openDeleteConfirmation(classCheckboxes.filter((checkbox) => checkbox.checked).map((checkbox) => ({
                id: checkbox.value,
                name: checkbox.dataset.className || `Class ${checkbox.value}`,
                season: checkbox.dataset.classSeason || "",
            })));
        });
    }
    document.querySelectorAll("[data-delete-class-id]").forEach((button) => {
        button.addEventListener("click", () => openDeleteConfirmation([{
            id: button.dataset.deleteClassId,
            name: button.dataset.deleteClassName || "Class",
            season: button.dataset.deleteClassSeason || "",
        }]));
    });
    if (deleteModal) {
        deleteModal.querySelectorAll("[data-close-class-delete]").forEach((button) => {
            button.addEventListener("click", () => setModalOpen(deleteModal, false));
        });
        if (deleteAcknowledgment && submitDelete) {
            deleteAcknowledgment.addEventListener("change", () => {
                submitDelete.disabled = !deleteAcknowledgment.checked;
            });
        }
        deleteModal.addEventListener("submit", (event) => {
            if (!deleteAcknowledgment || !deleteAcknowledgment.checked) event.preventDefault();
        });
    }

    const displayModal = document.querySelector("[data-class-display-modal]");
    const openDisplay = document.querySelector("[data-open-class-display-settings]");
    const tableSettings = document.querySelector("[data-table-column-settings]");
    const cardSettings = document.querySelector("[data-card-field-settings]");
    const tableHidden = document.querySelector("[data-table-columns-json]");
    const cardHidden = document.querySelector("[data-card-fields-json]");

    const tableOptions = parseScriptJson("class-table-column-options", []);
    const cardOptions = parseScriptJson("class-card-field-options", []);
    const currentTableObjects = parseScriptJson("class-current-table-columns", []);
    const currentCardFields = parseScriptJson("class-current-card-fields", []);

    let tableOrder = currentTableObjects.map((item) => item.key);
    let enabledCardFields = [...currentCardFields];

    const renderTableSettings = () => {
        if (!tableSettings) return;
        tableSettings.innerHTML = "";

        const knownKeys = tableOptions.map((item) => item.key);

        knownKeys.forEach((key) => {
            if (!tableOrder.includes(key)) {
                tableOrder.push(key);
            }
        });

        tableOrder.forEach((key, index) => {
            const option = tableOptions.find((item) => item.key === key);
            if (!option) return;

            const enabled = currentTableObjects.some(
                (item) => item.key === key
            );

            const row = document.createElement("div");
            row.className = "class-display-setting-row";

            const label = document.createElement("label");
            label.className = "class-display-setting-check";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.dataset.columnKey = key;
            checkbox.checked = enabled;

            const text = document.createElement("span");
            text.textContent = option.label;

            label.appendChild(checkbox);
            label.appendChild(text);

            const controls = document.createElement("div");
            controls.className = "class-display-order-controls";

            const up = document.createElement("button");
            up.type = "button";
            up.textContent = "↑";
            up.title = "Move up";
            up.disabled = index === 0;
            up.addEventListener("click", () => {
                [tableOrder[index - 1], tableOrder[index]] = [
                    tableOrder[index],
                    tableOrder[index - 1],
                ];
                renderTableSettings();
            });

            const down = document.createElement("button");
            down.type = "button";
            down.textContent = "↓";
            down.title = "Move down";
            down.disabled = index === tableOrder.length - 1;
            down.addEventListener("click", () => {
                [tableOrder[index], tableOrder[index + 1]] = [
                    tableOrder[index + 1],
                    tableOrder[index],
                ];
                renderTableSettings();
            });

            controls.appendChild(up);
            controls.appendChild(down);

            row.appendChild(label);
            row.appendChild(controls);
            tableSettings.appendChild(row);
        });
    };

    const renderCardSettings = () => {
        if (!cardSettings) return;
        cardSettings.innerHTML = "";

        cardOptions.forEach((option) => {
            const row = document.createElement("label");
            row.className = "class-display-setting-check card-field-check";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.dataset.cardFieldKey = option.key;
            checkbox.checked = enabledCardFields.includes(option.key);

            const text = document.createElement("span");
            text.textContent = option.label;

            row.appendChild(checkbox);
            row.appendChild(text);
            cardSettings.appendChild(row);
        });
    };

    if (openDisplay && displayModal) {
        openDisplay.addEventListener("click", () => {
            renderTableSettings();
            renderCardSettings();
            setModalOpen(displayModal, true);
        });

        displayModal.querySelectorAll("[data-close-class-display-settings]").forEach((button) => {
            button.addEventListener("click", () => {
                setModalOpen(displayModal, false);
            });
        });

        displayModal.addEventListener("submit", () => {
            const selectedColumns = Array.from(
                displayModal.querySelectorAll("[data-column-key]:checked")
            ).map((checkbox) => checkbox.dataset.columnKey);

            const orderedSelected = tableOrder.filter(
                (key) => selectedColumns.includes(key)
            );

            const selectedCards = Array.from(
                displayModal.querySelectorAll("[data-card-field-key]:checked")
            ).map((checkbox) => checkbox.dataset.cardFieldKey);

            if (tableHidden) {
                tableHidden.value = JSON.stringify(orderedSelected);
            }
            if (cardHidden) {
                cardHidden.value = JSON.stringify(selectedCards);
            }
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;

        [bulkModal, displayModal, deleteModal].forEach((modal) => {
            if (modal && !modal.hidden) {
                setModalOpen(modal, false);
            }
        });
    });

    syncSelection();
});
