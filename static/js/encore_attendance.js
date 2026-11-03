document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-row-href]").forEach((row) => {
        row.addEventListener("click", (event) => {
            if (event.target.closest("a, button, input, select, label, form")) {
                return;
            }
            window.location.href = row.dataset.rowHref;
        });

        row.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                window.location.href = row.dataset.rowHref;
            }
        });

        row.tabIndex = 0;
        row.setAttribute("role", "link");
    });


    const automationModal = document.querySelector("[data-automation-modal]");
    const automationForm = document.querySelector("[data-automation-form]");

    if (automationModal && automationForm) {
        const modalTitle = automationModal.querySelector("[data-automation-modal-title]");
        const actionInput = automationForm.querySelector("[data-automation-action]");
        const triggerIdInput = automationForm.querySelector("[data-automation-trigger-id]");
        const nameInput = automationForm.querySelector("[data-automation-name]");
        const thresholdInput = automationForm.querySelector("[data-automation-threshold]");
        const enabledInput = automationForm.querySelector("[data-automation-enabled]");
        const highlightInput = automationForm.querySelector("[data-automation-highlight]");
        const makeupsInput = automationForm.querySelector("[data-automation-makeups]");
        const sendEmailInput = automationForm.querySelector("[data-automation-send-email]");
        const parentTaskInput = automationForm.querySelector("[data-automation-parent-task]");
        const notifyTeacherInput = automationForm.querySelector("[data-automation-notify-teacher]");
        const emailField = automationForm.querySelector("[data-automation-email-field]");
        const emailTemplateSelect = automationForm.querySelector("[data-automation-email-template]");
        const submitButton = automationForm.querySelector("[data-automation-submit]");

        const setCheckbox = (input, value) => {
            if (input) input.checked = value === true || value === "1";
        };

        const syncEmailTemplateVisibility = () => {
            if (!emailField || !sendEmailInput) return;
            emailField.hidden = !sendEmailInput.checked;
            if (emailTemplateSelect) {
                emailTemplateSelect.disabled = !sendEmailInput.checked;
            }
        };

        const openAutomationModal = (button) => {
            const editMode = button.dataset.mode === "edit";

            actionInput.value = editMode ? "update_trigger" : "create_trigger";
            triggerIdInput.value = editMode ? (button.dataset.triggerId || "") : "";
            nameInput.value = editMode ? (button.dataset.name || "") : "Consecutive Absence Alert";
            thresholdInput.value = editMode ? (button.dataset.threshold || "3") : "3";

            setCheckbox(enabledInput, editMode ? button.dataset.enabled : true);
            setCheckbox(highlightInput, editMode ? button.dataset.highlight : true);
            setCheckbox(makeupsInput, editMode ? button.dataset.makeups : true);
            setCheckbox(sendEmailInput, editMode ? button.dataset.sendEmail : true);
            setCheckbox(parentTaskInput, editMode ? button.dataset.parentTask : true);
            setCheckbox(notifyTeacherInput, editMode ? button.dataset.notifyTeacher : true);

            if (emailTemplateSelect) {
                emailTemplateSelect.value = editMode
                    ? (button.dataset.emailTemplateId || "")
                    : "";
            }

            modalTitle.textContent = editMode ? "Edit Automation" : "Create Automation";
            submitButton.textContent = editMode ? "Save Changes" : "Create Automation";
            syncEmailTemplateVisibility();

            automationModal.hidden = false;
            document.body.classList.add("modal-open");
            window.setTimeout(() => nameInput.focus(), 0);
        };

        const closeAutomationModal = () => {
            automationModal.hidden = true;
            document.body.classList.remove("modal-open");
        };

        document.querySelectorAll("[data-open-automation-modal]").forEach((button) => {
            button.addEventListener("click", () => openAutomationModal(button));
        });

        automationModal.querySelectorAll("[data-close-automation-modal]").forEach((button) => {
            button.addEventListener("click", closeAutomationModal);
        });

        automationModal.addEventListener("click", (event) => {
            if (event.target === automationModal) closeAutomationModal();
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !automationModal.hidden) {
                closeAutomationModal();
            }
        });

        sendEmailInput?.addEventListener("change", syncEmailTemplateVisibility);
        syncEmailTemplateVisibility();
    }

    document.querySelectorAll("[data-delete-automation-form]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm("Delete this attendance automation? This cannot be undone.")) {
                event.preventDefault();
            }
        });
    });

    const updateWarning = (group) => {
        const row = group.closest("[data-student-row]");
        if (!row) return;

        const threshold = Number(row.dataset.warningThreshold || 0);
        if (!threshold) return;

        const prior = Number(row.dataset.priorAbsenceCount || 0);
        const selected = group.querySelector('input[type="radio"]:checked');
        const count = selected && selected.value === "absent" ? prior + 1 : 0;
        const warning = row.querySelector("[data-absence-warning]");
        const active = count >= threshold;

        row.classList.toggle("absence-warning-row", active);

        if (warning) {
            warning.hidden = !active;
            warning.textContent = active ? `${count} consecutive absences` : "";
        }
    };

    document.querySelectorAll("[data-attendance-group]").forEach((group) => {
        const choices = group.querySelectorAll(".attendance-choice");

        choices.forEach((choice) => {
            const input = choice.querySelector("input");
            input.addEventListener("change", () => {
                choices.forEach((item) => item.classList.remove("selected"));
                if (input.checked) choice.classList.add("selected");
                updateWarning(group);
            });
        });

        updateWarning(group);
    });

    const panel = document.querySelector("[data-makeup-search-panel]");
    const openButton = document.querySelector("[data-open-makeup-search]");
    const closeButton = document.querySelector("[data-close-makeup-search]");
    const input = document.querySelector("[data-makeup-search-input]");
    const results = document.querySelector("[data-makeup-search-results]");

    if (!panel || !openButton || !input || !results) return;

    const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
    let timer = null;

    const escapeHtml = (value) => {
        const node = document.createElement("div");
        node.textContent = value;
        return node.innerHTML;
    };

    openButton.addEventListener("click", () => {
        panel.hidden = false;
        input.focus();
    });

    closeButton?.addEventListener("click", () => {
        panel.hidden = true;
        input.value = "";
        results.innerHTML = "";
    });

    const renderResults = (items) => {
        results.innerHTML = "";

        if (!items.length) {
            results.innerHTML = '<div class="makeup-search-empty">No matching students.</div>';
            return;
        }

        items.forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "makeup-search-result";
            button.innerHTML = `
                <span>
                    <strong>${escapeHtml(item.name)}</strong>
                    <small>Age ${escapeHtml(String(item.age ?? "—"))} · ${escapeHtml(item.source_class)}</small>
                </span>
                <span class="makeup-owed-count">${item.makeups_owed} owed</span>
            `;

            button.addEventListener("click", async () => {
                button.disabled = true;
                const body = new URLSearchParams();
                body.set("student_id", item.id);

                const response = await fetch(panel.dataset.addUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    body: body.toString(),
                });

                const payload = await response.json();

                if (!response.ok || !payload.ok) {
                    button.disabled = false;
                    window.alert(payload.error || "Unable to add makeup student.");
                    return;
                }

                window.location.reload();
            });

            results.appendChild(button);
        });
    };

    input.addEventListener("input", () => {
        clearTimeout(timer);
        const query = input.value.trim();

        if (query.length < 2) {
            results.innerHTML = "";
            return;
        }

        timer = setTimeout(async () => {
            const url = new URL(panel.dataset.searchUrl, window.location.origin);
            url.searchParams.set("q", query);
            const response = await fetch(url);
            const payload = await response.json();
            renderResults(payload.results || []);
        }, 220);
    });
});


document.addEventListener("DOMContentLoaded", () => {
    const originalSearch = document.querySelector("[data-filter-original]");
    const originalSelect = document.querySelector("[data-original-class]");
    originalSearch?.addEventListener("input", () => {
        const term = originalSearch.value.trim().toLowerCase();
        Array.from(originalSelect.options).forEach((option) => {
            if (option.value) option.hidden = !option.textContent.toLowerCase().includes(term);
        });
    });

    const meetingForm = document.querySelector("[data-makeup-rule-form]");
    if (meetingForm) {
        const search = meetingForm.querySelector("[data-filter-meetings]");
        const typeSelect = meetingForm.querySelector("[data-filter-class-type]");
        const levelSelect = meetingForm.querySelector("[data-filter-class-level]");
        const rows = Array.from(meetingForm.querySelectorAll("[data-meeting-item]"));
        const selectVisible = meetingForm.querySelector("[data-select-visible-meetings]");
        const selectedCount = meetingForm.querySelector("[data-makeup-selected-count]");
        const visibleCount = meetingForm.querySelector("[data-makeup-visible-count]");
        const noResults = meetingForm.querySelector("[data-meeting-no-results]");
        const checkboxFor = (row) => row.querySelector('input[name="meeting_ids"]');
        const visibleRows = () => rows.filter((row) => !row.hidden);
        const updateSelection = () => {
            const showing = visibleRows();
            const checked = showing.filter((row) => checkboxFor(row).checked).length;
            selectedCount.textContent = `${rows.filter((row) => checkboxFor(row).checked).length} selected`;
            visibleCount.textContent = `${showing.length} sessions shown`;
            selectVisible.checked = showing.length > 0 && checked === showing.length;
            selectVisible.indeterminate = checked > 0 && checked < showing.length;
            selectVisible.disabled = showing.length === 0;
            if (noResults) noResults.hidden = showing.length !== 0;
        };
        const filterRows = () => {
            const q = (search?.value || "").trim().toLowerCase();
            const type = typeSelect?.value || "";
            const level = levelSelect?.value || "";
            rows.forEach((row) => {
                row.hidden = !!((q && !row.dataset.search.includes(q)) ||
                    (type && row.dataset.classType !== type) ||
                    (level && row.dataset.classLevel !== level));
            });
            updateSelection();
        };
        [search, typeSelect, levelSelect].forEach((control) => control?.addEventListener("input", filterRows));
        rows.forEach((row) => checkboxFor(row).addEventListener("change", updateSelection));
        selectVisible?.addEventListener("change", () => {
            visibleRows().forEach((row) => { checkboxFor(row).checked = selectVisible.checked; });
            updateSelection();
        });
        meetingForm.querySelector("[data-clear-meeting-selection]")?.addEventListener("click", () => {
            rows.forEach((row) => { checkboxFor(row).checked = false; });
            updateSelection();
        });
        meetingForm.querySelector("[data-clear-meeting-filters]")?.addEventListener("click", () => {
            search.value = "";
            typeSelect.value = "";
            levelSelect.value = "";
            filterRows();
        });
        meetingForm.querySelector("[data-match-original]")?.addEventListener("click", () => {
            const selected = originalSelect?.selectedOptions[0];
            if (!selected?.value) {
                originalSelect?.focus();
                return;
            }
            search.value = "";
            typeSelect.value = selected.dataset.type || "";
            levelSelect.value = selected.dataset.level || "";
            // Level may be blank; still match classes without an assigned level.
            filterRows();
            if (!selected.dataset.level) {
                rows.forEach((row) => { if (!row.hidden && row.dataset.classLevel !== "") row.hidden = true; });
                updateSelection();
            }
        });
        meetingForm.addEventListener("submit", (event) => {
            if (!rows.some((row) => checkboxFor(row).checked)) {
                event.preventDefault();
                window.alert("Choose at least one replacement session before saving.");
            }
        });
        filterRows();
    }
    const modal = document.querySelector("[data-assign-makeup-modal]");
    const form = document.querySelector("[data-assign-makeup-form]");
    if (!modal || !form) return;
    const requirementInput = form.querySelector("[data-makeup-requirement]");
    const meetingSelect = form.querySelector("[data-makeup-meeting]");
    const dateSelect = form.querySelector("[data-makeup-date]");
    const studentText = form.querySelector("[data-makeup-student-name]");
    const close = () => { modal.hidden = true; document.body.classList.remove("modal-open"); };
    const setDates = (dates, message="Choose an available session…") => {
        dateSelect.replaceChildren(new Option(message, ""));
        dates.forEach((day) => dateSelect.add(new Option(day, day)));
    };
    document.querySelectorAll("[data-open-assign-modal]").forEach((button) => {
        button.addEventListener("click", () => {
            requirementInput.value = button.dataset.requirementId;
            studentText.textContent = `${button.dataset.studentName} · missed ${button.dataset.sourceName}`;
            meetingSelect.value = "";
            Array.from(meetingSelect.options).forEach((option) => {
                if (option.value) {
                    option.hidden = option.dataset.forRequirement !== button.dataset.requirementId;
                    option.disabled = option.hidden;
                }
            });
            setDates([], "Select an eligible meeting first…");
            modal.hidden = false;
            document.body.classList.add("modal-open");
        });
    });
    meetingSelect.addEventListener("change", async () => {
        setDates([], "Loading available dates…");
        if (!meetingSelect.value) { setDates([], "Select a meeting first…"); return; }
        const query = new URLSearchParams({requirement_id: requirementInput.value, meeting_id: meetingSelect.value});
        try {
            const response = await fetch(`${form.dataset.datesUrl}?${query.toString()}`, {credentials: "same-origin"});
            if (!response.ok) throw new Error("Availability unavailable");
            const data = await response.json();
            setDates(data.dates || [], "Select a date…");
        } catch (error) { setDates([], "Could not load dates. Try again."); }
    });
    modal.querySelectorAll("[data-close-assign-makeup]").forEach((button) => button.addEventListener("click", close));
    modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !modal.hidden) close(); });
});
