document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector(
        "[data-time-off-form]"
    );

    if (form) {
        const hiddenDates = form.querySelector(
            'input[name="dates"]'
        );

        const dateInput = form.querySelector(
            "[data-time-off-date-input]"
        );

        const addButton = form.querySelector(
            "[data-add-time-off-date]"
        );

        const selectedDates = form.querySelector(
            "[data-selected-time-off-dates]"
        );

        let dates = (
            hiddenDates.value
                ? hiddenDates.value
                    .split(",")
                    .map((value) => value.trim())
                    .filter(Boolean)
                : []
        );

        const syncHidden = () => {
            dates.sort();
            hiddenDates.value = dates.join(",");
        };

        const renderDates = () => {
            selectedDates.innerHTML = "";

            dates.forEach((value) => {
                const date = new Date(
                    `${value}T12:00:00`
                );

                const chip = document.createElement(
                    "div"
                );

                chip.className = "time-off-date-chip";

                const label = document.createElement(
                    "span"
                );

                label.textContent = (
                    new Intl.DateTimeFormat(
                        undefined,
                        {
                            weekday: "short",
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                        }
                    ).format(date)
                );

                const remove = document.createElement(
                    "button"
                );

                remove.type = "button";
                remove.setAttribute(
                    "aria-label",
                    `Remove ${label.textContent}`
                );
                remove.textContent = "×";

                remove.addEventListener(
                    "click",
                    () => {
                        dates = dates.filter(
                            (item) => item !== value
                        );

                        syncHidden();
                        renderDates();
                    }
                );

                chip.append(
                    label,
                    remove
                );

                selectedDates.appendChild(
                    chip
                );
            });

            selectedDates.classList.toggle(
                "empty",
                dates.length === 0
            );

            if (dates.length === 0) {
                const empty = document.createElement(
                    "p"
                );

                empty.textContent = (
                    "No dates selected yet."
                );

                selectedDates.appendChild(
                    empty
                );
            }
        };

        const addDate = () => {
            const value = dateInput.value;

            if (!value) {
                dateInput.focus();
                return;
            }

            if (!dates.includes(value)) {
                dates.push(value);
            }

            syncHidden();
            renderDates();

            dateInput.value = "";
            dateInput.focus();
        };

        addButton.addEventListener(
            "click",
            addDate
        );

        dateInput.addEventListener(
            "keydown",
            (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    addDate();
                }
            }
        );

        // A date typed or picked in the field counts even if the teacher
        // forgets to press the separate Add Date button.
        form.addEventListener("submit", (event) => {
            const pending = (dateInput.value || "").trim();
            if (pending && !dates.includes(pending)) {
                dates.push(pending);
            }
            syncHidden();
            renderDates();
            if (!dates.length) {
                event.preventDefault();
                dateInput.setCustomValidity("Choose at least one date.");
                dateInput.reportValidity();
                dateInput.focus();
            } else {
                dateInput.setCustomValidity("");
            }
        });
        dateInput.addEventListener("input", () => dateInput.setCustomValidity(""));
        dateInput.addEventListener("change", () => dateInput.setCustomValidity(""));

        syncHidden();
        renderDates();
    }

    const reviewForm = document.querySelector(
        "[data-time-off-review-form]"
    );

    if (reviewForm) {
        document.querySelectorAll(
            "[data-time-off-bulk]"
        ).forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    const value = (
                        button.dataset.timeOffBulk
                    );

                    reviewForm.querySelectorAll(
                        'select[name^="date_"]'
                    ).forEach((select) => {
                        select.value = value;
                    });
                }
            );
        });
    }
});
