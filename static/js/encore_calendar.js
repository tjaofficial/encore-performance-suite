document.addEventListener("DOMContentLoaded", () => {
    const calendarElement = document.getElementById("encore-calendar");

    if (!calendarElement) {
        return;
    }

    const body = document.body;
    const feedUrl = body.dataset.calendarFeedUrl;
    const eventCreateUrl = body.dataset.eventCreateUrl;
    const eventBaseUrl = eventCreateUrl.replace(/add\/?$/, "");
    const categoryCreateUrl = body.dataset.categoryCreateUrl;
    const preferenceUrl = body.dataset.preferenceUrl;
    const role = body.dataset.role;

    const createMenuToggle = document.querySelector("[data-create-menu-toggle]");
    const createMenu = document.querySelector("[data-create-menu]");
    const createEventButton = document.querySelector("[data-create-event]");

    const editor = document.querySelector("[data-event-editor]");
    const eventForm = document.querySelector("[data-calendar-event-form]");
    const eventIdInput = document.querySelector("[data-event-id]");
    const editorTitle = document.querySelector("[data-editor-title]");
    const eventErrors = document.querySelector("[data-event-errors]");
    const eventScope = document.querySelector("[data-event-scope]");
    const categorySelect = document.querySelector("[data-category-select]");
    const publicRow = document.querySelector("[data-public-row]");

    const recurrencePreset = document.querySelector("[data-recurrence-preset]");
    const recurrenceModal = document.querySelector("[data-recurrence-modal]");

    const popover = document.querySelector("[data-event-popover]");
    const popoverEdit = document.querySelector("[data-popover-edit]");
    const popoverDelete = document.querySelector("[data-popover-delete]");
    const popoverClose = document.querySelector("[data-popover-close]");
    const popoverType = document.querySelector("[data-popover-type]");
    const popoverTitle = document.querySelector("[data-popover-title]");
    const popoverTime = document.querySelector("[data-popover-time]");
    const popoverLocation = document.querySelector("[data-popover-location]");
    const popoverDescription = document.querySelector("[data-popover-description]");
    const popoverDot = document.querySelector("[data-popover-dot]");
    const popoverDetailLink = document.querySelector("[data-popover-detail-link]");

    const settingsDrawer = document.querySelector("[data-settings-drawer]");
    const settingsForm = document.querySelector("[data-calendar-settings-form]");
    const addCategoryButton = document.querySelector("[data-add-category]");
    const newCategoryName = document.querySelector("[data-new-category-name]");
    const newCategoryColor = document.querySelector("[data-new-category-color]");
    const newCategoryScope = document.querySelector("[data-new-category-scope]");
    const settingsCategoryList = document.querySelector("[data-settings-category-list]");
    const personalCategoryList = document.querySelector("[data-personal-category-list]");
    const mainCategoryList = document.querySelector("[data-main-category-list]");

    let activePopoverEvent = null;
    let activeEditingEventId = null;

    const getCookie = (name) => {
        const row = document.cookie
            .split(";")
            .map((item) => item.trim())
            .find((item) => item.startsWith(`${name}=`));

        return row
            ? decodeURIComponent(row.split("=")[1])
            : "";
    };

    const csrf = () => getCookie("csrftoken");

    const postForm = async (url, formData) => {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrf(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: formData,
        });

        const contentType = (
            response.headers.get("content-type")
            || ""
        );

        let data = null;

        if (contentType.includes("application/json")) {
            data = await response.json();
        } else {
            const text = await response.text();

            const error = new Error(
                response.redirected
                    ? (
                        "Encore returned a page instead of a calendar response. "
                        + "Your session may have expired; refresh and try again."
                    )
                    : (
                        `Encore returned an unexpected ${response.status} response.`
                    )
            );

            error.payload = {
                error: error.message,
                responseText: text,
            };

            throw error;
        }

        if (!response.ok) {
            const error = new Error(
                data.error || "Unable to save."
            );
            error.payload = data;
            throw error;
        }

        return data;
    };

    const closeCreateMenu = () => {
        if (createMenu) {
            createMenu.hidden = true;
        }
    };

    if (createMenuToggle && createMenu) {
        createMenuToggle.addEventListener("click", (event) => {
            event.stopPropagation();
            createMenu.hidden = !createMenu.hidden;
        });

        document.addEventListener("click", closeCreateMenu);

        createMenu.addEventListener("click", (event) => {
            event.stopPropagation();
        });
    }

    const closePopover = () => {
        if (!popover) {
            return;
        }

        popover.hidden = true;
        activePopoverEvent = null;
    };

    if (popoverClose) {
        popoverClose.addEventListener("click", closePopover);
    }

    const formatEventTime = (event) => {
        if (event.allDay) {
            return "All day";
        }

        const formatter = new Intl.DateTimeFormat(
            undefined,
            {
                dateStyle: "medium",
                timeStyle: "short",
            }
        );

        const start = event.start
            ? formatter.format(event.start)
            : "";

        const end = event.end
            ? formatter.format(event.end)
            : "";

        return end
            ? `${start} – ${end}`
            : start;
    };

    const positionPopover = (jsEvent) => {
        if (!popover) {
            return;
        }

        const width = Math.min(
            380,
            window.innerWidth - 24
        );

        let left = jsEvent.clientX + 14;
        let top = jsEvent.clientY + 14;

        if (left + width > window.innerWidth - 12) {
            left = Math.max(
                12,
                jsEvent.clientX - width - 14
            );
        }

        if (top + 300 > window.innerHeight - 12) {
            top = Math.max(
                12,
                window.innerHeight - 312
            );
        }

        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;
    };

    const openPopover = (event, jsEvent) => {
        const props = event.extendedProps || {};

        activePopoverEvent = event;

        popoverType.textContent = (
            props.categoryName
            || props.eventType
            || "Calendar"
        );

        popoverTitle.textContent = event.title;
        popoverTime.textContent = formatEventTime(event);

        popoverLocation.textContent = props.location || "";
        popoverLocation.hidden = !props.location;

        const description = (
            props.description
            || (
                props.sourceType === "absence"
                    ? `${props.student || ""} · ${props.className || ""}`
                    : ""
            )
        );

        popoverDescription.textContent = description;
        popoverDescription.hidden = !description;

        popoverDot.style.setProperty(
            "--event-color",
            event.backgroundColor || "#2E3CF1"
        );

        const canEdit = Boolean(props.editable);
        const canDelete = Boolean(props.deletable);

        popoverEdit.hidden = !canEdit;
        popoverDelete.hidden = !canDelete;

        const detailUrl = props.detailUrl || "";
        popoverDetailLink.hidden = !detailUrl;
        popoverDetailLink.href = detailUrl || "#";

        positionPopover(jsEvent);
        popover.hidden = false;
    };

    const filterCategoryOptions = () => {
        if (!eventScope || !categorySelect) {
            return;
        }

        const selectedScope = eventScope.value;

        Array.from(categorySelect.options).forEach((option) => {
            if (!option.value) {
                option.hidden = false;
                return;
            }

            option.hidden = (
                option.dataset.categoryScope !== selectedScope
            );
        });

        const selectedOption = categorySelect.selectedOptions[0];

        if (
            selectedOption
            && selectedOption.value
            && selectedOption.dataset.categoryScope !== selectedScope
        ) {
            categorySelect.value = "";
        }

        if (publicRow) {
            publicRow.hidden = selectedScope !== "main";
        }
    };

    if (eventScope) {
        eventScope.addEventListener(
            "change",
            filterCategoryOptions
        );
    }

    const setDateTimeValue = (input, dateValue) => {
        if (!input || !dateValue) {
            return;
        }

        const date = new Date(dateValue);
        const offset = date.getTimezoneOffset();
        const local = new Date(
            date.getTime()
            - offset * 60000
        );

        input.value = local
            .toISOString()
            .slice(0, 16);
    };

    const resetRecurrenceFields = () => {
        eventForm.querySelectorAll(
            'input[name="custom_weekdays"]'
        ).forEach((input) => {
            input.checked = false;
        });

        const interval = eventForm.querySelector(
            '[name="custom_interval"]'
        );
        const frequency = eventForm.querySelector(
            '[name="custom_frequency"]'
        );
        const endDate = eventForm.querySelector(
            '[name="custom_end_date"]'
        );
        const occurrenceCount = eventForm.querySelector(
            '[name="custom_occurrence_count"]'
        );

        if (interval) interval.value = "1";
        if (frequency) frequency.value = "weekly";
        if (endDate) endDate.value = "";
        if (occurrenceCount) occurrenceCount.value = "";

        const never = eventForm.querySelector(
            '[name="custom_end_type"][value="never"]'
        );

        if (never) {
            never.checked = true;
        }
    };

    const openEditor = ({
        eventId = null,
        start = null,
        end = null,
        allDay = false,
    } = {}) => {
        closeCreateMenu();
        closePopover();

        eventForm.reset();
        resetRecurrenceFields();

        activeEditingEventId = eventId;
        eventIdInput.value = eventId || "";
        editorTitle.textContent = (
            eventId
                ? "Edit Event"
                : "Add Event"
        );

        eventErrors.hidden = true;
        eventErrors.textContent = "";

        if (!eventId) {
            if (eventScope) {
                eventScope.value = (
                    role === "administrator"
                        ? "main"
                        : "personal"
                );
            }

            const startDate = (
                start
                    ? new Date(start)
                    : new Date()
            );

            const endDate = (
                end
                    ? new Date(end)
                    : new Date(
                        startDate.getTime()
                        + 60 * 60 * 1000
                    )
            );

            setDateTimeValue(
                eventForm.elements.start_at,
                startDate
            );
            setDateTimeValue(
                eventForm.elements.end_at,
                endDate
            );

            eventForm.elements.all_day.checked = Boolean(allDay);
            recurrencePreset.value = "none";

            filterCategoryOptions();

            editor.hidden = false;
            eventForm.elements.title.focus();
            return;
        }

        editor.hidden = false;

        fetch(`${eventBaseUrl}${eventId}/`, {
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.ok) {
                    throw new Error("Unable to load event.");
                }

                const item = payload.event;

                eventForm.elements.title.value = item.title || "";
                eventForm.elements.scope.value = item.scope;
                eventForm.elements.description.value = item.description || "";
                eventForm.elements.event_type.value = item.eventType || "general";
                eventForm.elements.category.value = item.categoryId || "";
                eventForm.elements.location.value = item.location || "";
                eventForm.elements.notes.value = item.notes || "";
                eventForm.elements.all_day.checked = Boolean(item.allDay);

                if (eventForm.elements.is_public) {
                    eventForm.elements.is_public.checked = Boolean(item.isPublic);
                }

                setDateTimeValue(
                    eventForm.elements.start_at,
                    item.startAt
                );

                setDateTimeValue(
                    eventForm.elements.end_at,
                    item.endAt
                );

                if (item.recurrence) {
                    recurrencePreset.value = "custom";

                    eventForm.elements.custom_frequency.value = (
                        item.recurrence.frequency
                    );
                    eventForm.elements.custom_interval.value = (
                        item.recurrence.interval || 1
                    );

                    eventForm.querySelectorAll(
                        '[name="custom_weekdays"]'
                    ).forEach((input) => {
                        input.checked = (
                            item.recurrence.weekdays || []
                        ).includes(
                            Number.parseInt(
                                input.value,
                                10
                            )
                        );
                    });

                    const endType = eventForm.querySelector(
                        `[name="custom_end_type"][value="${item.recurrence.endType}"]`
                    );

                    if (endType) {
                        endType.checked = true;
                    }

                    eventForm.elements.custom_end_date.value = (
                        item.recurrence.endDate || ""
                    );

                    eventForm.elements.custom_occurrence_count.value = (
                        item.recurrence.occurrenceCount || ""
                    );
                } else {
                    recurrencePreset.value = "none";
                }

                filterCategoryOptions();
            })
            .catch((error) => {
                eventErrors.textContent = error.message;
                eventErrors.hidden = false;
            });
    };

    document.querySelectorAll("[data-close-editor]").forEach((button) => {
        button.addEventListener("click", () => {
            editor.hidden = true;
        });
    });

    if (createEventButton) {
        createEventButton.addEventListener("click", () => {
            openEditor();
        });
    }

    if (recurrencePreset) {
        recurrencePreset.addEventListener("change", () => {
            if (recurrencePreset.value === "custom") {
                recurrenceModal.hidden = false;
            }
        });
    }

    document.querySelectorAll("[data-close-recurrence]").forEach((button) => {
        button.addEventListener("click", () => {
            recurrenceModal.hidden = true;
        });
    });

    const saveRecurrence = document.querySelector("[data-save-recurrence]");

    if (saveRecurrence) {
        saveRecurrence.addEventListener("click", () => {
            recurrencePreset.value = "custom";
            recurrenceModal.hidden = true;
        });
    }

    const renderErrors = (payload) => {
        const errors = payload.errors || {};
        const messages = [];

        Object.entries(errors).forEach(([field, rows]) => {
            rows.forEach((row) => {
                messages.push(
                    `${field.replaceAll("_", " ")}: ${row.message}`
                );
            });
        });

        eventErrors.textContent = (
            messages.join(" ")
            || payload.error
            || "Unable to save event."
        );
        eventErrors.hidden = false;
    };

    eventForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        eventErrors.hidden = true;
        eventErrors.textContent = "";

        const formData = new FormData(eventForm);

        if (!eventForm.elements.all_day.checked) {
            formData.delete("all_day");
        }

        if (
            eventForm.elements.is_public
            && !eventForm.elements.is_public.checked
        ) {
            formData.delete("is_public");
        }

        const url = activeEditingEventId
            ? `${eventBaseUrl}${activeEditingEventId}/edit/`
            : eventCreateUrl;

        try {
            await postForm(url, formData);
            editor.hidden = true;
            calendar.refetchEvents();
        } catch (error) {
            renderErrors(
                error.payload || {
                    error: error.message,
                }
            );
        }
    });

    if (popoverEdit) {
        popoverEdit.addEventListener("click", () => {
            if (!activePopoverEvent) {
                return;
            }

            const eventId = (
                activePopoverEvent.extendedProps.calendarEventId
            );

            if (eventId) {
                openEditor({
                    eventId,
                });
            }
        });
    }

    if (popoverDelete) {
        popoverDelete.addEventListener("click", async () => {
            if (!activePopoverEvent) {
                return;
            }

            const eventId = (
                activePopoverEvent.extendedProps.calendarEventId
            );

            if (!eventId) {
                return;
            }

            const confirmed = window.confirm(
                `Delete "${activePopoverEvent.title}"?`
            );

            if (!confirmed) {
                return;
            }

            try {
                await postForm(
                    `${eventBaseUrl}${eventId}/delete/`,
                    new FormData()
                );

                closePopover();
                calendar.refetchEvents();
            } catch (error) {
                window.alert(error.message);
            }
        });
    }

    const sourceCheckboxes = Array.from(
        document.querySelectorAll("[data-source-toggle]")
    );

    const categoryCheckboxes = Array.from(
        document.querySelectorAll("[data-category-toggle]")
    );

    const classCheckboxes = Array.from(
        document.querySelectorAll("[data-class-toggle]")
    );

    const instructorCheckboxes = Array.from(
        document.querySelectorAll("[data-instructor-toggle]")
    );

    const visibilityScript = document.getElementById(
        "calendar-source-visibility"
    );

    let savedVisibility = {};

    if (visibilityScript) {
        try {
            savedVisibility = JSON.parse(
                visibilityScript.textContent
            ) || {};
        } catch {
            savedVisibility = {};
        }
    }

    sourceCheckboxes.forEach((input) => {
        const key = input.dataset.sourceToggle;

        if (
            Object.prototype.hasOwnProperty.call(
                savedVisibility,
                key
            )
        ) {
            input.checked = Boolean(
                savedVisibility[key]
            );
        }
    });

    const hiddenCategoryIds = new Set(
        (savedVisibility.hidden_category_ids || [])
            .map((value) => String(value))
    );

    categoryCheckboxes.forEach((input) => {
        input.checked = !hiddenCategoryIds.has(
            input.dataset.categoryToggle
        );
    });

    const savedClassIds = new Set(
        (savedVisibility.selected_class_ids || [])
            .map((value) => String(value))
    );

    if (savedClassIds.size) {
        classCheckboxes.forEach((input) => {
            input.checked = savedClassIds.has(
                input.dataset.classToggle
            );
        });
    }

    const savedInstructorIds = new Set(
        (savedVisibility.selected_instructor_ids || [])
            .map((value) => String(value))
    );

    if (savedInstructorIds.size) {
        instructorCheckboxes.forEach((input) => {
            input.checked = savedInstructorIds.has(
                input.dataset.instructorToggle
            );
        });
    }

    const feedQuery = (info) => {
        const params = new URLSearchParams({
            start: info.startStr,
            end: info.endStr,
        });

        let sources = sourceCheckboxes
            .filter((input) => input.checked)
            .map((input) => input.dataset.sourceToggle);

        const checkedClasses = classCheckboxes.filter(
            (input) => input.checked
        );

        if (
            classCheckboxes.length
            && checkedClasses.length === 0
        ) {
            sources = sources.filter(
                (source) => source !== "classes"
            );
        } else if (
            checkedClasses.length
            && checkedClasses.length < classCheckboxes.length
        ) {
            params.set(
                "class_ids",
                checkedClasses
                    .map((input) => input.dataset.classToggle)
                    .join(",")
            );
        }

        const checkedInstructors = instructorCheckboxes.filter(
            (input) => input.checked
        );

        if (
            instructorCheckboxes.length
            && checkedInstructors.length === 0
        ) {
            sources = sources.filter(
                (source) => source !== "classes"
            );
        } else if (
            checkedInstructors.length
            && checkedInstructors.length < instructorCheckboxes.length
        ) {
            params.set(
                "instructor_ids",
                checkedInstructors
                    .map((input) => input.dataset.instructorToggle)
                    .join(",")
            );
        }

        params.set(
            "sources",
            sources.join(",")
        );

        const hiddenCategories = categoryCheckboxes
            .filter((input) => !input.checked)
            .map((input) => input.dataset.categoryToggle);

        if (hiddenCategories.length) {
            params.set(
                "hidden_category_ids",
                hiddenCategories.join(",")
            );
        }

        return params;
    };

    const calendar = new FullCalendar.Calendar(
        calendarElement,
        {
            initialView: body.dataset.defaultView || "dayGridMonth",
            height: "auto",
            firstDay: Number.parseInt(
                body.dataset.firstDay || "0",
                10
            ),
            weekends: body.dataset.showWeekends !== "0",
            nowIndicator: true,
            dayMaxEvents: true,
            selectable: (
                role === "administrator"
                || role === "teacher"
            ),

            headerToolbar: {
                left: "prev,next today",
                center: "title",
                right: "dayGridMonth,timeGridWeek,timeGridDay,listWeek",
            },

            buttonText: {
                today: "Today",
                month: "Month",
                week: "Week",
                day: "Day",
                list: "Agenda",
            },

            events(info, successCallback, failureCallback) {
                const params = feedQuery(info);

                fetch(`${feedUrl}?${params.toString()}`, {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                })
                    .then((response) => {
                        if (!response.ok) {
                            throw new Error("Unable to load calendar.");
                        }

                        return response.json();
                    })
                    .then(successCallback)
                    .catch(failureCallback);
            },

            eventClassNames(info) {
                const props = info.event.extendedProps || {};
                const classes = [];

                if (props.sourceType === "task") {
                    classes.push("encore-task-event");
                }

                if (props.sourceType === "absence") {
                    classes.push("encore-absence-event");
                }

                if (!info.event.allDay) {
                    classes.push("encore-timed-event");
                }

                if (
                    settingsForm
                    && settingsForm.elements.dim_past_events.checked
                    && info.event.end
                    && info.event.end < new Date()
                ) {
                    classes.push("is-past-event");
                }

                return classes;
            },

            eventClick(info) {
                info.jsEvent.preventDefault();
                openPopover(
                    info.event,
                    info.jsEvent
                );
            },

            select(info) {
                openEditor({
                    start: info.start,
                    end: info.end,
                    allDay: info.allDay,
                });
                calendar.unselect();
            },
        }
    );

    const fitMonthCellsToViewport = () => {
        const monthView = calendarElement.querySelector(
            ".fc-dayGridMonth-view"
        );

        if (!monthView) {
            return;
        }

        const dayCell = monthView.querySelector(
            ".fc-daygrid-day"
        );

        const rows = monthView.querySelectorAll(
            ".fc-scrollgrid-sync-table > tbody > tr"
        );

        const calendarSurface = document.querySelector(
            ".calendar-surface"
        );

        if (
            !dayCell
            || !rows.length
            || !calendarSurface
        ) {
            return;
        }

        const dayWidth = dayCell.getBoundingClientRect().width;

        const toolbar = calendarElement.querySelector(
            ".fc-header-toolbar"
        );

        const columnHeader = monthView.querySelector(
            ".fc-col-header"
        );

        const surfaceHeight = calendarSurface.clientHeight;

        const toolbarHeight = toolbar
            ? toolbar.getBoundingClientRect().height
            : 0;

        const headerHeight = columnHeader
            ? columnHeader.getBoundingClientRect().height
            : 0;

        const usableHeight = Math.max(
            300,
            surfaceHeight
            - toolbarHeight
            - headerHeight
            - 30
        );

        const fitHeight = Math.floor(
            usableHeight / rows.length
        );

        /*
        Stay square when square cells fit. If the available
        viewport is shorter than the square height, shrink the
        rows just enough to keep the full month visible.
        */
        const dayHeight = Math.max(
            88,
            Math.min(
                Math.round(dayWidth),
                fitHeight
            )
        );

        monthView.style.setProperty(
            "--encore-calendar-day-size",
            `${dayHeight}px`
        );

        calendar.updateSize();
    };

    calendar.render();

    window.requestAnimationFrame(
        fitMonthCellsToViewport
    );

    calendar.on(
        "datesSet",
        () => {
            window.requestAnimationFrame(
                fitMonthCellsToViewport
            );
        }
    );

    let calendarResizeTimer = null;

    window.addEventListener(
        "resize",
        () => {
            window.clearTimeout(
                calendarResizeTimer
            );

            calendarResizeTimer = window.setTimeout(
                () => {
                    calendar.updateSize();

                    window.requestAnimationFrame(
                        fitMonthCellsToViewport
                    );
                },
                120
            );
        }
    );

    const preferenceFormData = () => {
        const formData = new FormData();

        formData.append(
            "default_view",
            settingsForm.elements.default_view.value
        );
        formData.append(
            "week_starts_on",
            settingsForm.elements.week_starts_on.value
        );

        if (settingsForm.elements.show_weekends.checked) {
            formData.append("show_weekends", "1");
        }

        if (settingsForm.elements.show_completed_tasks.checked) {
            formData.append("show_completed_tasks", "1");
        }

        if (settingsForm.elements.dim_past_events.checked) {
            formData.append("dim_past_events", "1");
        }

        sourceCheckboxes.forEach((input) => {
            formData.append(
                `source_${input.dataset.sourceToggle}`,
                input.checked ? "1" : "0"
            );
        });

        formData.append(
            "hidden_category_ids",
            categoryCheckboxes
                .filter((input) => !input.checked)
                .map((input) => input.dataset.categoryToggle)
                .join(",")
        );

        formData.append(
            "selected_class_ids",
            classCheckboxes
                .filter((input) => input.checked)
                .map((input) => input.dataset.classToggle)
                .join(",")
        );

        formData.append(
            "selected_instructor_ids",
            instructorCheckboxes
                .filter((input) => input.checked)
                .map((input) => input.dataset.instructorToggle)
                .join(",")
        );

        return formData;
    };

    const saveVisibilityPreference = () => {
        postForm(
            preferenceUrl,
            preferenceFormData()
        ).catch(() => {
            // Visibility still works for this session even if persistence fails.
        });
    };

    [
        ...sourceCheckboxes,
        ...categoryCheckboxes,
        ...classCheckboxes,
        ...instructorCheckboxes,
    ].forEach((input) => {
        input.addEventListener("change", () => {
            calendar.refetchEvents();
            saveVisibilityPreference();
        });
    });

    document.querySelectorAll("[data-open-settings]").forEach((button) => {
        button.addEventListener("click", () => {
            settingsDrawer.hidden = false;
        });
    });

    document.querySelectorAll("[data-close-settings]").forEach((button) => {
        button.addEventListener("click", () => {
            settingsDrawer.hidden = true;
        });
    });

    if (addCategoryButton) {
        addCategoryButton.addEventListener("click", async () => {
            const name = newCategoryName.value.trim();

            if (!name) {
                newCategoryName.focus();
                return;
            }

            const formData = new FormData();
            const scope = (
                newCategoryScope
                    ? newCategoryScope.value
                    : "personal"
            );

            formData.append("scope", scope);
            formData.append("name", name);
            formData.append("color", newCategoryColor.value);

            try {
                const payload = await postForm(
                    categoryCreateUrl,
                    formData
                );

                const category = payload.category;

                const settingsRow = document.createElement("div");
                settingsRow.innerHTML = `
                    <span class="source-swatch" style="--swatch:${category.color}"></span>
                    <span>${category.name}</span>
                `;
                settingsCategoryList.appendChild(settingsRow);

                const sidebarLabel = document.createElement("label");
                sidebarLabel.innerHTML = `
                    <input
                        type="checkbox"
                        data-category-toggle="${category.id}"
                        checked
                    >
                    <span
                        class="source-swatch"
                        style="--swatch:${category.color}"
                    ></span>
                    <span>${category.name}</span>
                `;

                const targetCategoryList = (
                    category.scope === "main"
                        ? mainCategoryList
                        : personalCategoryList
                );

                if (targetCategoryList) {
                    targetCategoryList.appendChild(sidebarLabel);

                    const input = sidebarLabel.querySelector("input");
                    categoryCheckboxes.push(input);

                    input.addEventListener("change", () => {
                        calendar.refetchEvents();
                        saveVisibilityPreference();
                    });
                }

                const option = document.createElement("option");
                option.value = category.id;
                option.dataset.categoryScope = category.scope;
                option.textContent = category.name;
                categorySelect.appendChild(option);

                newCategoryName.value = "";
            } catch (error) {
                window.alert(error.message);
            }
        });
    }

    if (settingsForm) {
        settingsForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            try {
                await postForm(
                    preferenceUrl,
                    preferenceFormData()
                );

                calendar.setOption(
                    "weekends",
                    settingsForm.elements.show_weekends.checked
                );

                calendar.setOption(
                    "firstDay",
                    Number.parseInt(
                        settingsForm.elements.week_starts_on.value,
                        10
                    )
                );

                calendar.changeView(
                    settingsForm.elements.default_view.value
                );

                calendar.refetchEvents();
                settingsDrawer.hidden = true;
            } catch (error) {
                window.alert(error.message);
            }
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }

        closePopover();
        closeCreateMenu();

        if (editor) {
            editor.hidden = true;
        }

        if (recurrenceModal) {
            recurrenceModal.hidden = true;
        }

        if (settingsDrawer) {
            settingsDrawer.hidden = true;
        }
    });
});
