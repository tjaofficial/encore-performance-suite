/* Encore Email Manager V2 runtime bundle */

document.addEventListener("DOMContentLoaded", () => {
    const editors = document.querySelectorAll(
        "[data-email-editor]"
    );

    editors.forEach((editor) => {
        const source = editor.querySelector(
            "[data-email-html-source]"
        );
        const surface = editor.querySelector(
            "[data-editor-surface]"
        );
        const html = editor.querySelector(
            "[data-editor-html]"
        );
        const toolbar = editor.querySelector(
            "[data-editor-toolbar]"
        );
        const modeToggle = editor.querySelector(
            "[data-editor-mode-toggle]"
        );

        if (!source || !surface || !html || !modeToggle) {
            return;
        }

        let htmlMode = false;

        const syncFromSource = () => {
            surface.innerHTML = source.value || "";
            html.value = source.value || "";
        };

        const syncToSource = () => {
            source.value = (
                htmlMode
                ? html.value
                : surface.innerHTML
            );
        };

        const runCommand = (
            command,
            value = null
        ) => {
            surface.focus();
            document.execCommand(
                command,
                false,
                value
            );
            syncToSource();
        };

        editor.querySelectorAll(
            "[data-editor-command]"
        ).forEach((button) => {
            button.addEventListener(
                "click",
                () => runCommand(
                    button.dataset.editorCommand
                )
            );
        });

        const block = editor.querySelector(
            "[data-editor-block]"
        );

        if (block) {
            block.addEventListener(
                "change",
                () => runCommand(
                    "formatBlock",
                    block.value
                )
            );
        }

        const size = editor.querySelector(
            "[data-editor-size]"
        );

        if (size) {
            size.addEventListener(
                "change",
                () => runCommand(
                    "fontSize",
                    size.value
                )
            );
        }

        const color = editor.querySelector(
            "[data-editor-color]"
        );

        if (color) {
            color.addEventListener(
                "input",
                () => runCommand(
                    "foreColor",
                    color.value
                )
            );
        }

        const link = editor.querySelector(
            "[data-editor-link]"
        );

        if (link) {
            link.addEventListener(
                "click",
                () => {
                    const url = window.prompt(
                        "Enter the link URL:"
                    );

                    if (url) {
                        runCommand(
                            "createLink",
                            url
                        );
                    }
                }
            );
        }

        surface.addEventListener(
            "input",
            syncToSource
        );

        html.addEventListener(
            "input",
            syncToSource
        );

        modeToggle.addEventListener(
            "click",
            () => {
                if (htmlMode) {
                    surface.innerHTML = html.value;
                    surface.hidden = false;
                    html.hidden = true;
                    toolbar.classList.remove(
                        "html-mode"
                    );
                    modeToggle.textContent = "HTML";
                    htmlMode = false;
                } else {
                    html.value = surface.innerHTML;
                    surface.hidden = true;
                    html.hidden = false;
                    toolbar.classList.add(
                        "html-mode"
                    );
                    modeToggle.textContent = "Editor";
                    htmlMode = true;
                }

                syncToSource();
            }
        );

        const form = editor.closest("form");

        if (form) {
            form.addEventListener(
                "submit",
                syncToSource
            );
        }

        editor.addEventListener(
            "encore:set-html",
            (event) => {
                const value = (
                    event.detail
                    && typeof event.detail.html === "string"
                )
                    ? event.detail.html
                    : "";

                source.value = value;
                surface.innerHTML = value;
                html.value = value;
            }
        );

        syncFromSource();
    });
});


document.addEventListener("DOMContentLoaded", () => {
    const compose = document.querySelector("[data-email-compose]");
    const templateBuilder = document.querySelector("[data-template-builder]");

    const escapeHtml = (value) => (
        String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;")
    );

    const parseJsonScript = (id, fallback) => {
        const node = document.getElementById(id);
        if (!node) {
            return fallback;
        }

        try {
            return JSON.parse(node.textContent);
        } catch (error) {
            return fallback;
        }
    };

    const initializeAutomationBuilder = (root) => {
        if (!root) {
            return;
        }

        const enabled = root.querySelector('[name="automation-enabled"]');
        const fields = root.querySelector("[data-automation-fields]");
        const trigger = root.querySelector("[data-automation-trigger]");
        const timing = root.querySelector("[data-automation-timing]");
        const help = root.querySelector("[data-automation-trigger-help]");

        if (!enabled || !fields) {
            return;
        }

        const field = (name) => root.querySelector(
            `[data-automation-field="${name}"]`
        );

        const thresholdTriggers = new Set([
            "consecutive_absences",
            "total_absences",
            "waitlist_threshold",
            "class_capacity",
        ]);

        const amountTriggers = new Set([
            "balance_threshold",
        ]);

        const relativeTriggers = new Set([
            "class_created",
            "registration_opens",
            "registration_closes",
            "class_starts",
            "upcoming_payment",
            "performance_approaching",
        ]);

        const helpText = {
            consecutive_absences: (
                "Example: set Number / Threshold to 3 to send after three consecutive absences."
            ),
            total_absences: (
                "Example: set Number / Threshold to 5 to send after five total absences."
            ),
            class_created: (
                "Use Immediately to send when the class is created, or Relative to a Date for messaging tied to the class start date."
            ),
            waitlist_threshold: (
                "Set the number of students that should trigger the message."
            ),
            balance_threshold: (
                "Set the dollar amount that should trigger the message."
            ),
            weekly: (
                "Choose the weekday and time Encore should run this rule."
            ),
            monthly: (
                "Choose the day of month and time Encore should run this rule."
            ),
            yearly: (
                "Choose the month, day, and time Encore should run this rule."
            ),
        };

        const update = () => {
            fields.hidden = !enabled.checked;

            if (fields.hidden) {
                return;
            }

            const triggerValue = trigger ? trigger.value : "";
            const timingValue = timing ? timing.value : "";

            const threshold = field("threshold");
            const amount = field("amount");
            const delay = field("delay");
            const relative = field("relative");
            const weekday = field("weekday");
            const monthday = field("monthday");
            const yearly = field("yearly");
            const time = field("time");

            if (threshold) {
                threshold.hidden = !thresholdTriggers.has(triggerValue);
            }

            if (amount) {
                amount.hidden = !amountTriggers.has(triggerValue);
            }

            if (delay) {
                delay.hidden = timingValue !== "delay";
            }

            if (relative) {
                relative.hidden = (
                    timingValue !== "relative"
                    || !relativeTriggers.has(triggerValue)
                );
            }

            if (weekday) {
                weekday.hidden = triggerValue !== "weekly";
            }

            if (monthday) {
                monthday.hidden = triggerValue !== "monthly";
            }

            if (yearly) {
                yearly.hidden = triggerValue !== "yearly";
            }

            if (time) {
                time.hidden = ![
                    "weekly",
                    "monthly",
                    "yearly",
                ].includes(triggerValue);
            }

            if (help) {
                help.textContent = (
                    helpText[triggerValue]
                    || "Encore stores this rule with the template. Event integrations can call it when the matching studio action occurs."
                );
            }
        };

        enabled.addEventListener("change", update);

        if (trigger) {
            trigger.addEventListener("change", update);
        }

        if (timing) {
            timing.addEventListener("change", update);
        }

        update();
    };

    initializeAutomationBuilder(templateBuilder);

    if (!compose) {
        return;
    }

    const catalog = parseJsonScript(
        "email-audience-catalog",
        {
            groups: [],
            options: {},
        }
    );

    const templatePayloads = parseJsonScript(
        "email-template-payloads",
        {}
    );

    const selectionField = compose.querySelector("[data-recipient-selection]");
    const groupPicker = compose.querySelector("[data-audience-group-picker]");
    const optionTitle = compose.querySelector("[data-audience-option-title]");
    const optionDescription = compose.querySelector("[data-audience-option-description]");
    const optionList = compose.querySelector("[data-audience-options]");
    const searchWrap = compose.querySelector("[data-audience-search-wrap]");
    const search = compose.querySelector("[data-audience-search]");
    const selectAllWrap = compose.querySelector("[data-select-all-wrap]");
    const selectAll = compose.querySelector("[data-audience-select-all]");
    const allOption = compose.querySelector("[data-audience-all-option]");
    const allCheckbox = compose.querySelector("[data-audience-all]");
    const summary = compose.querySelector("[data-selected-audience-summary]");
    const studentEmailOption = compose.querySelector("[data-student-email-option]");
    const studentEmailCheckbox = compose.querySelector('[name="send_to_students"]');
    const estimate = compose.querySelector("[data-recipient-estimate]");

    let state = {
        all: false,
        groups: {
            students: [],
            instructors: [],
            classes: [],
            instructor_students: [],
            admins: [],
        },
    };

    if (selectionField && selectionField.value) {
        try {
            const saved = JSON.parse(selectionField.value);

            if (saved && typeof saved === "object") {
                state = {
                    ...state,
                    ...saved,
                    groups: {
                        ...state.groups,
                        ...(saved.groups || {}),
                    },
                };
            }
        } catch (error) {
            // Keep defaults.
        }
    }

    const currentGroup = () => (
        groupPicker
        ? groupPicker.value
        : "students"
    );

    const groupDefinition = (key) => (
        catalog.groups.find(
            (group) => group.key === key
        )
        || {
            key,
            label: key,
            description: "",
        }
    );

    const optionMap = (key) => new Map(
        (catalog.options[key] || []).map(
            (item) => [
                String(item.id),
                item,
            ]
        )
    );

    const saveState = () => {
        if (selectionField) {
            selectionField.value = JSON.stringify(state);
        }
    };

    const studentAudienceSelected = () => (
        state.all
        || state.groups.students.length > 0
        || state.groups.classes.length > 0
        || state.groups.instructor_students.length > 0
    );

    let previewTimer = null;

    const updatePreview = () => {
        saveState();

        if (!compose.dataset.previewUrl || !estimate) {
            return;
        }

        clearTimeout(previewTimer);

        previewTimer = setTimeout(
            async () => {
                const csrf = compose.querySelector(
                    '[name="csrfmiddlewaretoken"]'
                );

                try {
                    const response = await fetch(
                        compose.dataset.previewUrl,
                        {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                                "X-CSRFToken": csrf ? csrf.value : "",
                            },
                            body: JSON.stringify({
                                selection: state,
                                send_to_students: (
                                    studentEmailCheckbox
                                    ? studentEmailCheckbox.checked
                                    : false
                                ),
                            }),
                        }
                    );

                    if (!response.ok) {
                        return;
                    }

                    const data = await response.json();

                    estimate.querySelector("strong").textContent = data.total;

                    const parts = [];

                    if (data.counts.guardian) {
                        parts.push(`${data.counts.guardian} family`);
                    }

                    if (data.counts.student) {
                        parts.push(`${data.counts.student} student`);
                    }

                    if (data.counts.instructor) {
                        parts.push(`${data.counts.instructor} instructor`);
                    }

                    if (data.counts.admin) {
                        parts.push(`${data.counts.admin} admin`);
                    }

                    if (data.counts.suppressed) {
                        parts.push(`${data.counts.suppressed} suppressed`);
                    }

                    estimate.querySelector("small").textContent = (
                        parts.join(" · ")
                        || "No deliverable addresses selected."
                    );
                } catch (error) {
                    estimate.querySelector("small").textContent = (
                        "Recipient preview unavailable."
                    );
                }
            },
            250
        );
    };

    const renderSummary = () => {
        if (!summary) {
            return;
        }

        summary.innerHTML = "";

        if (state.all) {
            const block = document.createElement("div");
            block.className = "selected-audience-group";
            block.innerHTML = `
                <div class="selected-audience-group-title">
                    <strong>All</strong>
                    <span>Entire Studio Audience</span>
                </div>
            `;
            summary.appendChild(block);
        }

        Object.entries(state.groups).forEach(
            ([key, values]) => {
                if (!values.length) {
                    return;
                }

                const definition = groupDefinition(key);
                const items = optionMap(key);
                const block = document.createElement("details");

                block.className = "selected-audience-group";
                block.open = values.length <= 5;

                const labels = values.map(
                    (id) => {
                        const item = items.get(String(id));
                        return item ? item.label : `#${id}`;
                    }
                );

                block.innerHTML = `
                    <summary>
                        <strong>${definition.label}</strong>
                        <span>${values.length} selected</span>
                    </summary>
                    <div class="selected-audience-names">
                        ${labels
                            .map(
                                (label) => `<span>${escapeHtml(label)}</span>`
                            )
                            .join("")}
                    </div>
                `;

                summary.appendChild(block);
            }
        );

        if (!summary.children.length) {
            summary.innerHTML = `
                <div class="selected-audience-empty">
                    No recipients selected yet.
                </div>
            `;
        }

        if (studentEmailOption) {
            studentEmailOption.hidden = !studentAudienceSelected();

            if (
                studentEmailCheckbox
                && studentEmailOption.hidden
            ) {
                studentEmailCheckbox.checked = false;
            }
        }

        updatePreview();
    };

    const updateSelectAllState = () => {
        if (!selectAll || currentGroup() === "all") {
            return;
        }

        const key = currentGroup();
        const available = catalog.options[key] || [];
        const selected = new Set(
            state.groups[key].map(String)
        );

        selectAll.checked = (
            available.length > 0
            && available.every(
                (item) => selected.has(String(item.id))
            )
        );

        selectAll.indeterminate = (
            selected.size > 0
            && !selectAll.checked
        );
    };

    const renderOptions = () => {
        if (!groupPicker || !optionList) {
            return;
        }

        const key = currentGroup();
        const definition = groupDefinition(key);

        if (optionTitle) {
            optionTitle.textContent = definition.label;
        }

        if (optionDescription) {
            optionDescription.textContent = definition.description || "";
        }

        const isAll = key === "all";

        if (allOption) {
            allOption.hidden = !isAll;
        }

        if (searchWrap) {
            searchWrap.hidden = isAll;
        }

        if (selectAllWrap) {
            selectAllWrap.hidden = isAll;
        }

        optionList.hidden = isAll;

        if (isAll) {
            if (allCheckbox) {
                allCheckbox.checked = state.all;
            }
            return;
        }

        const query = search
            ? search.value.trim().toLowerCase()
            : "";

        const options = (catalog.options[key] || []).filter(
            (item) => (
                !query
                || item.label.toLowerCase().includes(query)
                || (
                    item.meta
                    && item.meta.toLowerCase().includes(query)
                )
            )
        );

        const selected = new Set(
            state.groups[key].map(String)
        );

        optionList.innerHTML = "";

        options.forEach((item) => {
            const label = document.createElement("label");
            label.className = "audience-checkbox-option";

            label.innerHTML = `
                <input
                    type="checkbox"
                    value="${item.id}"
                    ${selected.has(String(item.id)) ? "checked" : ""}
                >
                <span class="audience-checkmark">✓</span>
                <span>
                    <strong>${escapeHtml(item.label)}</strong>
                    ${item.meta ? `<small>${escapeHtml(item.meta)}</small>` : ""}
                </span>
            `;

            const input = label.querySelector("input");

            input.addEventListener(
                "change",
                () => {
                    const values = new Set(
                        state.groups[key].map(String)
                    );

                    if (input.checked) {
                        values.add(String(item.id));
                    } else {
                        values.delete(String(item.id));
                    }

                    state.groups[key] = Array.from(values);
                    renderSummary();
                    updateSelectAllState();
                }
            );

            optionList.appendChild(label);
        });

        updateSelectAllState();
    };

    if (groupPicker) {
        groupPicker.addEventListener(
            "change",
            () => {
                if (search) {
                    search.value = "";
                }

                renderOptions();
            }
        );
    }

    if (search) {
        search.addEventListener("input", renderOptions);
    }

    if (selectAll) {
        selectAll.addEventListener(
            "change",
            () => {
                const key = currentGroup();

                state.groups[key] = (
                    selectAll.checked
                    ? (catalog.options[key] || []).map(
                        (item) => String(item.id)
                    )
                    : []
                );

                renderOptions();
                renderSummary();
            }
        );
    }

    if (allCheckbox) {
        allCheckbox.addEventListener(
            "change",
            () => {
                state.all = allCheckbox.checked;
                renderSummary();
            }
        );
    }

    if (studentEmailCheckbox) {
        studentEmailCheckbox.addEventListener(
            "change",
            updatePreview
        );
    }

    const sourceRadios = compose.querySelectorAll(
        '[name="message_source"]'
    );
    const templateField = compose.querySelector("[data-template-field]");
    const templateSelect = compose.querySelector('[name="template"]');
    const subject = compose.querySelector('[name="subject"]');
    const signature = compose.querySelector('[name="signature"]');
    const textBody = compose.querySelector('[name="text_body"]');
    const editor = compose.querySelector("[data-email-editor]");

    const selectedMessageSource = () => {
        const selected = Array.from(sourceRadios).find(
            (radio) => radio.checked
        );
        return selected ? selected.value : "new";
    };

    const updateMessageSource = () => {
        const useTemplate = selectedMessageSource() === "template";

        if (templateField) {
            templateField.hidden = !useTemplate;
        }

        if (!useTemplate && templateSelect) {
            templateSelect.value = "";
        }
    };

    sourceRadios.forEach((radio) => {
        radio.addEventListener("change", updateMessageSource);
    });

    if (templateSelect) {
        templateSelect.addEventListener(
            "change",
            () => {
                const payload = templatePayloads[
                    templateSelect.value
                ];

                if (!payload) {
                    return;
                }

                if (subject) {
                    subject.value = payload.subject || "";
                }

                if (signature) {
                    signature.value = payload.signature_id || "";
                }

                if (textBody) {
                    textBody.value = payload.text_body || "";
                }

                if (editor) {
                    editor.dispatchEvent(
                        new CustomEvent(
                            "encore:set-html",
                            {
                                detail: {
                                    html: payload.html_body || "",
                                },
                            }
                        )
                    );
                }
            }
        );
    }

    const schedule = compose.querySelector('[name="schedule_email"]');
    const scheduleField = compose.querySelector("[data-schedule-date-field]");
    const sendButton = compose.querySelector("[data-send-button]");

    const updateSchedule = () => {
        const enabled = schedule && schedule.checked;

        if (scheduleField) {
            scheduleField.hidden = !enabled;
        }

        if (sendButton) {
            sendButton.textContent = (
                enabled
                ? "Schedule Email"
                : "Send Email"
            );
        }
    };

    if (schedule) {
        schedule.addEventListener("change", updateSchedule);
    }

    compose.addEventListener("submit", saveState);

    updateMessageSource();
    updateSchedule();
    renderOptions();
    renderSummary();
});
