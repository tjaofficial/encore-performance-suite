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

    const calendarApp = document.querySelector(".calendar-app");
    const calendarBody = document.querySelector("[data-calendar-body]");
    const calendarSidebar = document.querySelector("[data-calendar-sidebar]");
    const sidebarCollapse = document.querySelector("[data-sidebar-collapse]");
    const sidebarResizer = document.querySelector("[data-sidebar-resizer]");

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
    const eventStartInput = eventForm?.elements?.start_at || null;
    const eventEndInput = eventForm?.elements?.end_at || null;

    const recurrencePreset = document.querySelector("[data-recurrence-preset]");
    const recurrenceModal = document.querySelector("[data-recurrence-modal]");

    const popover = document.querySelector("[data-event-popover]");
    const popoverEdit = document.querySelector("[data-popover-edit]");
    const popoverDelete = document.querySelector("[data-popover-delete]");
    const popoverClose = document.querySelector("[data-popover-close]");
    const popoverType = document.querySelector("[data-popover-type]");
    const popoverTitle = document.querySelector("[data-popover-title]");
    const popoverTime = document.querySelector("[data-popover-time]");
    const popoverHeaderTime = document.querySelector("[data-popover-header-time]");
    const popoverLocation = document.querySelector("[data-popover-location]");
    const popoverDescription = document.querySelector("[data-popover-description]");
    const popoverDot = document.querySelector("[data-popover-dot]");
    const popoverBadge = document.querySelector("[data-popover-badge]");
    const popoverDetailLink = document.querySelector("[data-popover-detail-link]");
    const genericDetailLink = document.querySelector("[data-generic-detail-link]");
    const genericEventType = document.querySelector("[data-generic-event-type]");
    const genericCategory = document.querySelector("[data-generic-category]");
    const genericStart = document.querySelector("[data-generic-start]");
    const genericEnd = document.querySelector("[data-generic-end]");
    const genericAllDay = document.querySelector("[data-generic-all-day]");
    const genericRepeats = document.querySelector("[data-generic-repeats]");
    const genericNotes = document.querySelector("[data-generic-notes]");
    const genericNotesWrap = document.querySelector("[data-generic-notes-wrap]");

    const classPopover = document.querySelector("[data-class-popover]");
    const genericPopover = document.querySelector("[data-generic-popover]");
    const genericLocationRow = document.querySelector("[data-generic-location-row]");
    const genericDescriptionWrap = document.querySelector("[data-generic-description-wrap]");

    const classStatus = document.querySelector("[data-class-status]");
    const classCode = document.querySelector("[data-class-code]");
    const classType = document.querySelector("[data-class-type]");
    const classSeason = document.querySelector("[data-class-season]");
    const classLocation = document.querySelector("[data-class-location]");
    const classRoom = document.querySelector("[data-class-room]");
    const classFee = document.querySelector("[data-class-fee]");
    const classInstructor = document.querySelector("[data-class-instructor]");
    const classDressCode = document.querySelector("[data-class-dress-code]");
    const classDressCodeWrap = document.querySelector("[data-class-dress-code-wrap]");
    const classOpenings = document.querySelector("[data-class-openings]");
    const classCurrentSize = document.querySelector("[data-class-current-size]");
    const classCapacity = document.querySelector("[data-class-capacity]");
    const classWaitlist = document.querySelector("[data-class-waitlist]");

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

    document.addEventListener("click", (event) => {
        if (
            !popover
            || popover.hidden
            || popover.contains(event.target)
            || event.target.closest(".fc-event")
        ) {
            return;
        }

        closePopover();
    });

    const formatEventTime = (event) => {
        const props = event.extendedProps || {};

        const originalStart = props.displayStart
            ? new Date(props.displayStart)
            : null;

        const originalEnd = props.displayEnd
            ? new Date(props.displayEnd)
            : null;

        const start = (
            originalStart
            && !Number.isNaN(originalStart.getTime())
        )
            ? originalStart
            : event.start;

        const end = (
            originalEnd
            && !Number.isNaN(originalEnd.getTime())
        )
            ? originalEnd
            : event.end;

        if (event.allDay) {
            if (!start) {
                return "All day";
            }

            const formatter = new Intl.DateTimeFormat(
                undefined,
                {
                    dateStyle: "medium",
                }
            );

            if (!end) {
                return `All day · ${formatter.format(start)}`;
            }

            const startLabel = formatter.format(start);
            const endLabel = formatter.format(end);

            return startLabel === endLabel
                ? `All day · ${startLabel}`
                : `All day · ${startLabel} – ${endLabel}`;
        }

        const formatter = new Intl.DateTimeFormat(
            undefined,
            {
                dateStyle: "medium",
                timeStyle: "short",
            }
        );

        const startLabel = start
            ? formatter.format(start)
            : "";

        const endLabel = end
            ? formatter.format(end)
            : "";

        return endLabel
            ? `${startLabel} – ${endLabel}`
            : startLabel;
    };

    const positionPopover = (jsEvent) => {
        if (!popover) {
            return;
        }

        const viewportPadding = 12;
        const gap = 12;
        const rect = popover.getBoundingClientRect();

        const popoverWidth = Math.min(
            rect.width || 420,
            window.innerWidth - (viewportPadding * 2)
        );

        const popoverHeight = Math.min(
            rect.height || 430,
            window.innerHeight - (viewportPadding * 2)
        );

        let left = jsEvent.clientX + gap;
        let top = jsEvent.clientY + gap;

        if (
            left + popoverWidth
            > window.innerWidth - viewportPadding
        ) {
            left = jsEvent.clientX - popoverWidth - gap;
        }

        if (
            top + popoverHeight
            > window.innerHeight - viewportPadding
        ) {
            top = jsEvent.clientY - popoverHeight - gap;
        }

        left = Math.max(
            viewportPadding,
            Math.min(
                left,
                window.innerWidth
                - popoverWidth
                - viewportPadding
            )
        );

        top = Math.max(
            viewportPadding,
            Math.min(
                top,
                window.innerHeight
                - popoverHeight
                - viewportPadding
            )
        );

        popover.style.left = `${Math.round(left)}px`;
        popover.style.top = `${Math.round(top)}px`;
    };

    const formatSingleDateTime = (value, allDay = false) => {
        if (!value) {
            return "—";
        }

        const date = new Date(value);

        if (Number.isNaN(date.getTime())) {
            return "—";
        }

        return new Intl.DateTimeFormat(
            undefined,
            allDay
                ? {
                    dateStyle: "medium",
                }
                : {
                    dateStyle: "medium",
                    timeStyle: "short",
                }
        ).format(date);
    };

    const recurrenceLabel = (recurrence) => {
        if (!recurrence) {
            return "Does not repeat";
        }

        const interval = Number.parseInt(
            recurrence.interval || 1,
            10
        );

        const unit = {
            daily: "day",
            weekly: "week",
            monthly: "month",
            yearly: "year",
        }[recurrence.frequency] || recurrence.frequency || "period";

        const base = interval === 1
            ? `Every ${unit}`
            : `Every ${interval} ${unit}s`;

        if (recurrence.endType === "on_date" && recurrence.endDate) {
            return `${base} · until ${formatSingleDateTime(recurrence.endDate, true)}`;
        }

        if (
            recurrence.endType === "after_count"
            && recurrence.occurrenceCount
        ) {
            return `${base} · ${recurrence.occurrenceCount} occurrences`;
        }

        return base;
    };

    const scopeLabel = (scope) => {
        if (scope === "main") {
            return "Main Event";
        }

        if (scope === "personal") {
            return "Personal Event";
        }

        return "Calendar Event";
    };

    const setDetailRow = (selector, value, formatter = null) => {
        const row = document.querySelector(selector);
        if (!row) {
            return;
        }

        const dd = row.querySelector("dd");
        const hasValue = (
            value !== null
            && value !== undefined
            && String(value).trim() !== ""
        );

        row.hidden = !hasValue;

        if (dd && hasValue) {
            dd.textContent = formatter
                ? formatter(value)
                : String(value);
        }
    };

    const openPopover = (event, jsEvent) => {
        const props = event.extendedProps || {};
        const isClass = props.sourceType === "class";

        activePopoverEvent = event;

        popoverType.textContent = (
            props.categoryName
            || props.eventType
            || "Calendar"
        );

        popoverTitle.textContent = event.title;

        const formattedTime = formatEventTime(event);

        if (popoverTime) {
            popoverTime.textContent = formattedTime;
        }

        if (popoverHeaderTime) {
            popoverHeaderTime.textContent = formattedTime;
        }

        const eventColor = (
            event.backgroundColor
            || event.borderColor
            || "#2E3CF1"
        );

        popover.style.setProperty(
            "--event-color",
            eventColor
        );

        popoverDot.style.setProperty(
            "--event-color",
            eventColor
        );

        if (popoverBadge) {
            popoverBadge.textContent = (
                props.eventType
                || props.sourceType
                || "Event"
            ).toUpperCase();
        }

        const canEdit = Boolean(props.editable);
        const canDelete = Boolean(props.deletable);

        popoverEdit.hidden = !canEdit;
        popoverDelete.hidden = !canDelete;

        const detailUrl = props.detailUrl || "";

        if (classPopover && genericPopover) {
            classPopover.hidden = !isClass;
            genericPopover.hidden = isClass;
        }

        if (isClass) {
            if (classStatus) {
                classStatus.textContent = (
                    props.statusLabel
                    || "Active"
                );
            }

            setDetailRow(
                "[data-class-code-row]",
                props.classCode
            );
            setDetailRow(
                "[data-class-type-row]",
                props.classType
            );
            setDetailRow(
                "[data-class-season-row]",
                props.seasonName
            );
            setDetailRow(
                "[data-class-location-row]",
                props.location
            );
            setDetailRow(
                "[data-class-room-row]",
                props.room
            );
            setDetailRow(
                "[data-class-fee-row]",
                props.fee,
                (value) => `$${value}`
            );
            setDetailRow(
                "[data-class-instructor-row]",
                props.instructor
            );

            const dressCode = (
                props.dressCode
                || ""
            ).trim();

            if (classDressCode) {
                classDressCode.textContent = dressCode;
            }

            if (classDressCodeWrap) {
                classDressCodeWrap.hidden = !dressCode;
            }

            if (classOpenings) {
                classOpenings.textContent = (
                    props.openings === null
                    || props.openings === undefined
                )
                    ? "—"
                    : String(props.openings);
            }

            if (classCurrentSize) {
                classCurrentSize.textContent = (
                    props.currentSize ?? "—"
                );
            }

            if (classCapacity) {
                classCapacity.textContent = (
                    props.capacity || "—"
                );
            }

            if (classWaitlist) {
                classWaitlist.textContent = (
                    props.waitlistCount ?? 0
                );
            }

            popoverDetailLink.hidden = !detailUrl;
            popoverDetailLink.href = detailUrl || "#";
        } else {
            const calendarEventId = props.calendarEventId || null;

            const fillGenericDetails = (item = null) => {
                const detail = item || {};

                const categoryName = (
                    props.categoryName
                    || detail.categoryName
                    || "No category"
                );

                if (genericEventType) {
                    genericEventType.textContent = (
                        detail.scope
                            ? scopeLabel(detail.scope)
                            : (
                                props.sourceType === "task"
                                    ? "Task"
                                    : props.sourceType === "absence"
                                    ? "Absence"
                                    : props.eventType || "Calendar Event"
                            )
                    );
                }

                if (genericCategory) {
                    genericCategory.textContent = categoryName;
                }

                const isAllDay = Boolean(
                    detail.allDay ?? event.allDay
                );

                if (genericStart) {
                    genericStart.textContent = formatSingleDateTime(
                        detail.startAt || event.start,
                        isAllDay
                    );
                }

                if (genericEnd) {
                    const endValue = detail.endAt || event.end;

                    genericEnd.textContent = endValue
                        ? formatSingleDateTime(
                            endValue,
                            isAllDay
                        )
                        : "—";
                }

                if (genericAllDay) {
                    genericAllDay.textContent = (
                        isAllDay ? "Yes" : "No"
                    );
                }

                if (genericRepeats) {
                    genericRepeats.textContent = recurrenceLabel(
                        detail.recurrence || null
                    );
                }

                const location = (
                    detail.location
                    || props.location
                    || ""
                );

                popoverLocation.textContent = (
                    location || "—"
                );

                if (genericLocationRow) {
                    genericLocationRow.hidden = false;
                }

                const description = (
                    detail.description
                    || props.description
                    || (
                        props.sourceType === "absence"
                            ? `${props.student || ""} · ${props.className || ""}`
                            : ""
                    )
                );

                const isSavedCalendarEvent = (
                    props.sourceType === "calendar_event"
                    || Boolean(calendarEventId)
                );

                popoverDescription.textContent = (
                    description
                    || (
                        isSavedCalendarEvent
                            ? "No description added."
                            : ""
                    )
                );

                if (genericDescriptionWrap) {
                    genericDescriptionWrap.hidden = (
                        !description
                        && !isSavedCalendarEvent
                    );
                }

                /*
                Notes are internal. Only show them in the popup when
                this user can edit the saved event.
                */
                const canShowNotes = (
                    Boolean(detail.canEdit)
                    || Boolean(props.editable)
                );

                const notes = canShowNotes
                    ? (detail.notes || "")
                    : "";

                if (genericNotes) {
                    genericNotes.textContent = notes;
                }

                if (genericNotesWrap) {
                    genericNotesWrap.hidden = !notes;
                }

                if (genericDetailLink) {
                    genericDetailLink.hidden = !detailUrl;
                    genericDetailLink.href = detailUrl || "#";
                }
            };

            /*
            Feed data is enough for tasks/absences/etc. Saved Encore
            calendar events also have a detail endpoint containing the
            exact fields from the Add/Edit Event form, so load that
            before finalizing the card.
            */
            fillGenericDetails();

            if (calendarEventId) {
                fetch(`${eventBaseUrl}${calendarEventId}/`, {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                })
                    .then((response) => {
                        if (!response.ok) {
                            throw new Error(
                                "Unable to load event details."
                            );
                        }

                        return response.json();
                    })
                    .then((payload) => {
                        if (payload.ok && payload.event) {
                            fillGenericDetails(payload.event);

                            window.requestAnimationFrame(() => {
                                positionPopover(jsEvent);
                            });
                        }
                    })
                    .catch(() => {
                        /*
                        The feed data still gives a useful popup if the
                        detail request is unavailable for any reason.
                        */
                    });
            }
        }

        /*
        Hidden elements do not have reliable dimensions. Show the card
        first, then measure and clamp it to the viewport.
        */
        popover.hidden = false;

        window.requestAnimationFrame(() => {
            positionPopover(jsEvent);
        });
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
        normalizeEditorEnd();

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


    const SIDEBAR_WIDTH_KEY = "encore-calendar-sidebar-width";
    const SIDEBAR_COLLAPSED_KEY = "encore-calendar-sidebar-collapsed";
    const SIDEBAR_MIN_WIDTH = 230;
    const SIDEBAR_MAX_WIDTH = 430;

    const clampSidebarWidth = (value) => Math.min(
        SIDEBAR_MAX_WIDTH,
        Math.max(SIDEBAR_MIN_WIDTH, value)
    );

    const setSidebarWidth = (width) => {
        const safeWidth = clampSidebarWidth(width);
        document.documentElement.style.setProperty(
            "--sidebar-width",
            `${safeWidth}px`
        );
        window.localStorage.setItem(
            SIDEBAR_WIDTH_KEY,
            String(safeWidth)
        );

        window.requestAnimationFrame(() => {
            if (typeof calendar !== "undefined") {
                calendar.updateSize();
            }
        });
    };

    const setSidebarCollapsed = (collapsed) => {
        if (!calendarBody || !calendarSidebar) {
            return;
        }

        calendarBody.classList.toggle(
            "sidebar-is-collapsed",
            collapsed
        );

        if (sidebarCollapse) {
            const arrow = sidebarCollapse.querySelector("span");
            if (arrow) {
                arrow.textContent = collapsed ? "›" : "‹";
            }
            sidebarCollapse.setAttribute(
                "aria-label",
                collapsed
                    ? "Expand calendar sidebar"
                    : "Collapse calendar sidebar"
            );
            sidebarCollapse.title = (
                collapsed
                    ? "Expand sidebar"
                    : "Collapse sidebar"
            );
        }

        window.localStorage.setItem(
            SIDEBAR_COLLAPSED_KEY,
            collapsed ? "1" : "0"
        );

        window.setTimeout(() => {
            calendar.updateSize();
        }, 180);
    };

    const savedSidebarWidth = Number.parseInt(
        window.localStorage.getItem(SIDEBAR_WIDTH_KEY) || "",
        10
    );

    if (Number.isFinite(savedSidebarWidth)) {
        document.documentElement.style.setProperty(
            "--sidebar-width",
            `${clampSidebarWidth(savedSidebarWidth)}px`
        );
    }

    if (sidebarCollapse) {
        sidebarCollapse.addEventListener("click", () => {
            setSidebarCollapsed(
                !calendarBody.classList.contains("sidebar-is-collapsed")
            );
        });
    }

    if (
        window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1"
        && window.innerWidth > 900
    ) {
        calendarBody.classList.add("sidebar-is-collapsed");

        if (sidebarCollapse) {
            const arrow = sidebarCollapse.querySelector("span");
            if (arrow) {
                arrow.textContent = "›";
            }
            sidebarCollapse.setAttribute(
                "aria-label",
                "Expand calendar sidebar"
            );
            sidebarCollapse.title = "Expand sidebar";
        }
    }

    if (sidebarResizer && calendarSidebar) {
        let resizingSidebar = false;

        const stopSidebarResize = () => {
            if (!resizingSidebar) {
                return;
            }

            resizingSidebar = false;
            body.classList.remove("is-resizing-calendar-sidebar");
            window.removeEventListener("pointermove", resizeSidebar);
            window.removeEventListener("pointerup", stopSidebarResize);
        };

        const resizeSidebar = (event) => {
            if (!resizingSidebar) {
                return;
            }

            setSidebarWidth(event.clientX);
        };

        sidebarResizer.addEventListener("pointerdown", (event) => {
            if (
                calendarBody.classList.contains("sidebar-is-collapsed")
                || window.innerWidth <= 900
            ) {
                return;
            }

            resizingSidebar = true;
            body.classList.add("is-resizing-calendar-sidebar");
            sidebarResizer.setPointerCapture?.(event.pointerId);
            window.addEventListener("pointermove", resizeSidebar);
            window.addEventListener("pointerup", stopSidebarResize);
            event.preventDefault();
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

    const seasonCheckboxes = Array.from(
        document.querySelectorAll("[data-season-toggle]")
    );

    const instructorCheckboxes = Array.from(
        document.querySelectorAll("[data-instructor-toggle]")
    );

    // Parent-only tree: student -> enrolled source class -> regular/make-up.
    // Keep selection separate from the shared teacher/admin class hierarchy.
    const familyTree = document.querySelector("[data-family-tree]");
    const familyAll = document.querySelector("[data-family-all]");
    const familyStudents = Array.from(document.querySelectorAll("[data-family-student]"));
    const familyClasses = Array.from(document.querySelectorAll("[data-family-class]"));
    const familyLeaves = Array.from(document.querySelectorAll("[data-family-leaf]"));
    const familySelectionKey = `encore-family-calendar:${feedUrl}`;
    if (familyTree) {
        try {
            const stored = JSON.parse(localStorage.getItem(familySelectionKey) || "null");
            if (Array.isArray(stored)) {
                const selected = new Set(stored);
                familyLeaves.forEach((leaf) => {
                    leaf.checked = selected.has(`${leaf.dataset.familyLeaf}:${leaf.dataset.familyMode}`);
                });
            }
        } catch { /* Keep initial selections. */ }
    }

    const updateFamilyTreeStates = () => {
        familyClasses.forEach((node) => {
            const leaves = familyLeaves.filter((leaf) => leaf.dataset.familyLeaf === node.dataset.familyClass);
            const checked = leaves.filter((leaf) => leaf.checked).length;
            node.checked = checked > 0;
            node.indeterminate = checked > 0 && checked < leaves.length;
        });
        familyStudents.forEach((node) => {
            const prefix = `${node.dataset.familyStudent}:`;
            const leaves = familyLeaves.filter((leaf) => leaf.dataset.familyLeaf.startsWith(prefix));
            const checked = leaves.filter((leaf) => leaf.checked).length;
            node.checked = checked > 0;
            node.indeterminate = checked > 0 && checked < leaves.length;
        });
        if (familyAll) {
            const checked = familyLeaves.filter((leaf) => leaf.checked).length;
            familyAll.checked = checked > 0;
            familyAll.indeterminate = checked > 0 && checked < familyLeaves.length;
        }
    };

    const familyChanged = () => {
        updateFamilyTreeStates();
        try {
            localStorage.setItem(familySelectionKey, JSON.stringify(
                familyLeaves.filter((leaf) => leaf.checked)
                    .map((leaf) => `${leaf.dataset.familyLeaf}:${leaf.dataset.familyMode}`)
            ));
        } catch { /* Filters still work without local storage. */ }
        calendar.refetchEvents();
    };

    if (familyTree) {
        familyAll?.addEventListener("change", () => {
            familyLeaves.forEach((leaf) => { leaf.checked = familyAll.checked; });
            familyChanged();
        });
        familyStudents.forEach((node) => {
            node.addEventListener("click", (event) => event.stopPropagation());
            node.addEventListener("change", () => {
                const prefix = `${node.dataset.familyStudent}:`;
                familyLeaves.filter((leaf) => leaf.dataset.familyLeaf.startsWith(prefix))
                    .forEach((leaf) => { leaf.checked = node.checked; });
                familyChanged();
            });
        });
        familyClasses.forEach((node) => {
            node.addEventListener("click", (event) => event.stopPropagation());
            node.addEventListener("change", () => {
                familyLeaves.filter((leaf) => leaf.dataset.familyLeaf === node.dataset.familyClass)
                    .forEach((leaf) => { leaf.checked = node.checked; });
                familyChanged();
            });
        });
        familyLeaves.forEach((leaf) => leaf.addEventListener("change", familyChanged));
        updateFamilyTreeStates();
    }

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

    const savedSeasonIds = new Set(
        (savedVisibility.selected_season_ids || [])
            .map((value) => String(value))
    );

    if (savedSeasonIds.size) {
        seasonCheckboxes.forEach((input) => {
            input.checked = savedSeasonIds.has(
                input.dataset.seasonToggle
            );

            if (!input.checked) {
                document.querySelectorAll(
                    `[data-season-id="${input.dataset.seasonToggle}"]`
                ).forEach((child) => {
                    child.checked = false;
                });
            }
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

    const groupParents = Array.from(
        document.querySelectorAll("[data-group-parent]")
    );

    const groupToggles = Array.from(
        document.querySelectorAll("[data-group-toggle]")
    );

    const groupChildren = (groupName) => Array.from(
        document.querySelectorAll(
            `[data-group-child="${groupName}"]`
        )
    );

    const updateGroupParentState = (groupName) => {
        const parent = document.querySelector(
            `[data-group-parent="${groupName}"]`
        );

        if (!parent) {
            return;
        }

        const children = groupChildren(groupName);

        if (!children.length) {
            parent.indeterminate = false;
            return;
        }

        const checkedCount = children.filter(
            (input) => input.checked
        ).length;

        parent.checked = checkedCount > 0;
        parent.indeterminate = (
            checkedCount > 0
            && checkedCount < children.length
        );
    };

    const updateSeasonParentState = (seasonId) => {
        const seasonInput = document.querySelector(
            `[data-season-toggle="${seasonId}"]`
        );
        if (!seasonInput) {
            return;
        }

        const children = Array.from(
            document.querySelectorAll(`[data-season-id="${seasonId}"]`)
        );
        if (!children.length) {
            seasonInput.indeterminate = false;
            return;
        }

        const checkedCount = children.filter((input) => input.checked).length;
        seasonInput.checked = checkedCount > 0;
        seasonInput.indeterminate = (
            checkedCount > 0
            && checkedCount < children.length
        );
    };

    const updateAllGroupParents = () => {
        seasonCheckboxes.forEach((input) => {
            updateSeasonParentState(input.dataset.seasonToggle);
        });

        groupParents.forEach((parent) => {
            updateGroupParentState(
                parent.dataset.groupParent
            );
        });
    };

    const setGroupChildren = (groupName, checked) => {
        groupChildren(groupName).forEach((input) => {
            input.checked = checked;
        });

        updateGroupParentState(groupName);
    };

    groupParents.forEach((parent) => {
        parent.addEventListener("change", () => {
            const groupName = parent.dataset.groupParent;
            const checked = parent.checked;

            parent.indeterminate = false;
            setGroupChildren(groupName, checked);

            calendar.refetchEvents();
            saveVisibilityPreference();
        });
    });

    seasonCheckboxes.forEach((seasonInput) => {
        seasonInput.addEventListener("click", (event) => {
            event.stopPropagation();
        });

        seasonInput.addEventListener("change", () => {
            const seasonId = seasonInput.dataset.seasonToggle;
            seasonInput.indeterminate = false;
            document.querySelectorAll(
                `[data-season-id="${seasonId}"]`
            ).forEach((input) => {
                input.checked = seasonInput.checked;
            });

            updateGroupParentState("classes");
            calendar.refetchEvents();
            saveVisibilityPreference();
        });
    });

    document.querySelectorAll("[data-group-child]").forEach((input) => {
        if (input.matches("[data-season-toggle]")) {
            return;
        }

        input.addEventListener("change", () => {
            if (input.dataset.seasonId) {
                updateSeasonParentState(input.dataset.seasonId);
            }

            updateGroupParentState(
                input.dataset.groupChild
            );

            calendar.refetchEvents();
            saveVisibilityPreference();
        });
    });

    groupToggles.forEach((button) => {
        button.addEventListener("click", () => {
            const groupName = button.dataset.groupToggle;
            const group = document.querySelector(
                `[data-source-group="${groupName}"]`
            );

            if (!group) {
                return;
            }

            const collapsed = group.classList.toggle(
                "is-collapsed"
            );

            button.classList.toggle(
                "is-collapsed",
                collapsed
            );
            button.setAttribute(
                "aria-expanded",
                collapsed ? "false" : "true"
            );
        });
    });

    updateAllGroupParents();
    if (familyTree) updateFamilyTreeStates();

    const feedQuery = (info) => {
        const params = new URLSearchParams({
            start: info.startStr,
            end: info.endStr,
        });

        let sources = sourceCheckboxes
            .filter((input) => input.checked)
            .map((input) => input.dataset.sourceToggle);

        const checkedSeasons = seasonCheckboxes.filter(
            (input) => input.checked
        );

        if (
            seasonCheckboxes.length
            && checkedSeasons.length === 0
        ) {
            sources = sources.filter(
                (source) => source !== "classes"
            );
        } else if (
            checkedSeasons.length
            && checkedSeasons.length < seasonCheckboxes.length
        ) {
            params.set(
                "season_ids",
                checkedSeasons
                    .map((input) => input.dataset.seasonToggle)
                    .join(",")
            );
        }

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

        if (familyTree) {
            // Empty selections must mean no events, never 'all events'.
            const regular = familyLeaves.filter((leaf) => leaf.checked && leaf.dataset.familyMode === "regular")
                .map((leaf) => leaf.dataset.familyLeaf);
            const makeups = familyLeaves.filter((leaf) => leaf.checked && leaf.dataset.familyMode === "makeup")
                .map((leaf) => leaf.dataset.familyLeaf);
            if (!regular.length) {
                sources = sources.filter((source) => source !== "classes");
            } else if (!sources.includes("classes")) {
                sources.push("classes");
            }
            params.set("family_regular_pairs", regular.join(","));
            params.set("family_makeup_pairs", makeups.join(","));
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

    const localDateTimeValue = (value) => {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "";
        }
        const offset = date.getTimezoneOffset();
        return new Date(date.getTime() - offset * 60000)
            .toISOString()
            .slice(0, 16);
    };

    const normalizeEditorEnd = () => {
        if (!eventStartInput || !eventEndInput) {
            return;
        }

        const start = new Date(eventStartInput.value);
        const end = new Date(eventEndInput.value);

        if (Number.isNaN(start.getTime())) {
            return;
        }

        if (
            !eventEndInput.value
            || Number.isNaN(end.getTime())
            || end <= start
        ) {
            eventEndInput.value = localDateTimeValue(
                new Date(start.getTime() + 60 * 60 * 1000)
            );
        }
    };

    if (eventStartInput) {
        eventStartInput.addEventListener("change", normalizeEditorEnd);
        eventStartInput.addEventListener("input", normalizeEditorEnd);
    }

    const updateDraggedCalendarEvent = async (info) => {
        const props = info.event.extendedProps || {};
        const eventId = props.calendarEventId;

        if (props.sourceType !== "calendar_event" || !eventId || !props.editable) {
            info.revert();
            return;
        }

        const response = await fetch(`${eventBaseUrl}${eventId}/`, {
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        });

        if (!response.ok) {
            throw new Error("Unable to load the event before moving it.");
        }

        const payload = await response.json();
        const detail = payload.event;
        if (!payload.ok || !detail) {
            throw new Error("Unable to load the event before moving it.");
        }

        const oldStart = info.oldEvent.start;
        const newStart = info.event.start;
        if (!oldStart || !newStart) {
            throw new Error("Encore could not determine the new event date.");
        }

        const deltaMs = newStart.getTime() - oldStart.getTime();
        const masterStart = new Date(detail.startAt);
        const masterEnd = new Date(detail.endAt);
        const movedStart = new Date(masterStart.getTime() + deltaMs);
        const movedEnd = new Date(masterEnd.getTime() + deltaMs);

        const formData = new FormData();
        formData.append("title", detail.title || "");
        formData.append("scope", detail.scope || "main");
        formData.append("description", detail.description || "");
        formData.append("event_type", detail.eventType || "general");
        formData.append("category", detail.categoryId || "");
        formData.append("location", detail.location || "");
        formData.append("notes", detail.notes || "");
        formData.append("start_at", localDateTimeValue(movedStart));
        formData.append("end_at", localDateTimeValue(movedEnd));

        if (detail.allDay) {
            formData.append("all_day", "1");
        }
        if (detail.isPublic) {
            formData.append("is_public", "1");
        }

        if (detail.recurrence) {
            formData.append("recurrence_preset", "custom");
            formData.append("custom_frequency", detail.recurrence.frequency);
            formData.append("custom_interval", detail.recurrence.interval || 1);
            (detail.recurrence.weekdays || []).forEach((day) => {
                formData.append("custom_weekdays", String(day));
            });
            formData.append("custom_end_type", detail.recurrence.endType || "never");
            if (detail.recurrence.endDate) {
                formData.append("custom_end_date", detail.recurrence.endDate);
            }
            if (detail.recurrence.occurrenceCount) {
                formData.append("custom_occurrence_count", detail.recurrence.occurrenceCount);
            }
        } else {
            formData.append("recurrence_preset", "none");
        }

        await postForm(`${eventBaseUrl}${eventId}/edit/`, formData);
        calendar.refetchEvents();
    };

    const calendar = new FullCalendar.Calendar(
        calendarElement,
        {
            initialView: body.dataset.defaultView || "dayGridMonth",
            height: "100%",
            expandRows: false,
            scrollTime: "08:00:00",
            scrollTimeReset: false,
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
            editable: true,

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
                    .then((rows) => {
                        const localDateString = (date) => {
                            const year = date.getFullYear();
                            const month = String(
                                date.getMonth() + 1
                            ).padStart(2, "0");
                            const day = String(
                                date.getDate()
                            ).padStart(2, "0");

                            return `${year}-${month}-${day}`;
                        };

                        const normalizedRows = rows.map((row) => {
                            const originalStart = row.start;
                            const originalEnd = row.end;
                            const props = row.extendedProps || {};

                            const startDate = new Date(originalStart);
                            const endDate = new Date(originalEnd);

                            const isValidRange = (
                                !Number.isNaN(startDate.getTime())
                                && !Number.isNaN(endDate.getTime())
                            );

                            const spansMultipleDates = (
                                isValidRange
                                && localDateString(startDate)
                                !== localDateString(endDate)
                            );

                            /*
                            User-created calendar events should render as
                            real bars when they span dates. FullCalendar's
                            default "auto" display can use the timed/list
                            presentation in month view, which makes a
                            multi-day event look like separate one-day rows.
                            */
                            const canDrag = (
                                props.sourceType === "calendar_event"
                                && Boolean(props.editable)
                            );

                            const baseRow = {
                                ...row,
                                editable: canDrag,
                                startEditable: canDrag,
                                durationEditable: canDrag,
                                display: (
                                    props.sourceType === "calendar_event"
                                    && spansMultipleDates
                                )
                                    ? "block"
                                    : row.display,
                                extendedProps: {
                                    ...props,
                                    displayStart: originalStart,
                                    displayEnd: originalEnd,
                                },
                            };

                            if (!row.allDay || !isValidRange) {
                                return baseRow;
                            }

                            /*
                            FullCalendar all-day `end` is exclusive.
                            Encore stores the final included day at
                            23:59:59, so Sep 3–Sep 9 must be rendered as
                            start Sep 3 / end Sep 10.
                            */
                            const exclusiveEnd = new Date(
                                endDate.getFullYear(),
                                endDate.getMonth(),
                                endDate.getDate() + 1
                            );

                            return {
                                ...baseRow,
                                start: localDateString(startDate),
                                end: localDateString(exclusiveEnd),
                                allDay: true,
                            };
                        });

                        successCallback(normalizedRows);
                    })
                    .catch(failureCallback);
            },

            eventClassNames(info) {
                const props = info.event.extendedProps || {};
                const classes = [];

                if (props.sourceType === "task") {
                    classes.push("encore-task-event");
                }

                if (props.sourceType === "makeup") {
                    classes.push("encore-makeup-event");
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
                    && props.sourceType !== "absence"
                    && info.event.end
                    && info.event.end < new Date()
                ) {
                    classes.push("is-past-event");
                }

                return classes;
            },

            eventDrop(info) {
                updateDraggedCalendarEvent(info).catch((error) => {
                    info.revert();
                    window.alert(error.message);
                });
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
            window.requestAnimationFrame(() => {
                fitMonthCellsToViewport();
                calendar.updateSize();
            });
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
            "selected_season_ids",
            seasonCheckboxes
                .filter((input) => input.checked)
                .map((input) => input.dataset.seasonToggle)
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

        document.querySelectorAll("[data-category-color-id]").forEach((input) => {
            formData.append(
                `category_color_${input.dataset.categoryColorId}`,
                input.value
            );
        });

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

    const hierarchyManagedInputs = new Set(
        document.querySelectorAll(
            "[data-group-parent], [data-group-child]"
        )
    );

    [
        ...sourceCheckboxes,
        ...categoryCheckboxes,
        ...seasonCheckboxes,
        ...classCheckboxes,
        ...instructorCheckboxes,
    ].forEach((input) => {
        if (hierarchyManagedInputs.has(input) || input === familyAll) {
            return;
        }

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
                if (category.scope === "main" && role === "administrator") {
                    settingsRow.className = "settings-category-row";
                    settingsRow.dataset.settingsCategoryId = category.id;
                    settingsRow.innerHTML = `
                        <input
                            type="color"
                            name="category_color_${category.id}"
                            value="${category.color}"
                            data-category-color-id="${category.id}"
                            aria-label="Color for ${category.name}"
                        >
                        <span>${category.name} <small>Main</small></span>
                    `;
                } else {
                    settingsRow.innerHTML = `
                        <span class="source-swatch" style="--swatch:${category.color}"></span>
                        <span>${category.name} <small>Personal</small></span>
                    `;
                }
                settingsCategoryList.appendChild(settingsRow);

                const sidebarLabel = document.createElement("label");
                sidebarLabel.innerHTML = `
                    <input
                        type="checkbox"
                        data-category-toggle="${category.id}"
                        data-group-child="${category.scope === "main" ? "main" : "personal"}"
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
                        updateGroupParentState(
                            input.dataset.groupChild
                        );
                        calendar.refetchEvents();
                        saveVisibilityPreference();
                    });

                    updateGroupParentState(
                        input.dataset.groupChild
                    );
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

                document.querySelectorAll("[data-category-color-id]").forEach((input) => {
                    const categoryId = input.dataset.categoryColorId;
                    document.querySelectorAll(
                        `[data-category-toggle="${categoryId}"]`
                    ).forEach((checkbox) => {
                        const swatch = checkbox.parentElement?.querySelector(".source-swatch");
                        if (swatch) {
                            swatch.style.setProperty("--swatch", input.value);
                        }
                    });
                });

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
