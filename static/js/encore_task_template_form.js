document.addEventListener("DOMContentLoaded", () => {
    const builder = document.querySelector("[data-template-builder]");

    if (!builder) {
        return;
    }

    const taskList = builder.querySelector("[data-template-task-list]");
    const triggerList = builder.querySelector("[data-template-trigger-list]");

    const taskTotal = builder.querySelector("#id_items-TOTAL_FORMS");
    const triggerTotal = builder.querySelector("#id_triggers-TOTAL_FORMS");

    const taskTemplate = document.querySelector("#template-task-empty-form");
    const triggerTemplate = document.querySelector("#template-trigger-empty-form");

    const addTaskButton = builder.querySelector("[data-add-template-task]");
    const addTriggerButton = builder.querySelector("[data-add-template-trigger]");

    const activeCards = (selector) => {
        return Array.from(
            builder.querySelectorAll(selector)
        ).filter((card) => !card.hidden);
    };

    const updateTaskNumbers = () => {
        activeCards("[data-template-task]").forEach((card, index) => {
            const number = card.querySelector(".template-item-number");

            if (number) {
                number.textContent = `Task ${index + 1}`;
            }

            const orderInput = card.querySelector(
                'input[name$="-order"]'
            );

            if (orderInput) {
                orderInput.value = String(index + 1);
            }
        });
    };

    const updateTriggerNumbers = () => {
        activeCards("[data-template-trigger]").forEach((card, index) => {
            const number = card.querySelector(".template-item-number");

            if (number) {
                number.textContent = `Trigger ${index + 1}`;
            }
        });
    };

    const updateRemoveVisibility = () => {
        const taskCards = activeCards("[data-template-task]");
        const triggerCards = activeCards("[data-template-trigger]");

        taskCards.forEach((card) => {
            const button = card.querySelector("[data-remove-template-task]");

            if (button) {
                button.hidden = taskCards.length <= 1;
            }
        });

        triggerCards.forEach((card) => {
            const button = card.querySelector("[data-remove-template-trigger]");

            if (button) {
                button.hidden = triggerCards.length <= 1;
            }
        });
    };

    const refreshDueFields = (card) => {
        const dueRule = card.querySelector(
            'select[name$="-due_rule"]'
        );

        const offset = card.querySelector(
            "[data-due-offset-field]"
        );

        if (!dueRule || !offset) {
            return;
        }

        const showOffset = dueRule.value === "days_after";
        offset.hidden = !showOffset;

        if (!showOffset) {
            const input = offset.querySelector(
                'input[name$="-due_offset_days"]'
            );

            if (input) {
                input.value = "0";
            }
        }
    };

    const refreshTriggerFields = (card) => {
        const type = card.querySelector(
            'select[name$="-trigger_type"]'
        );

        if (!type) {
            return;
        }

        const weekdays = card.querySelector(
            "[data-trigger-weekdays]"
        );

        const runDate = card.querySelector(
            "[data-trigger-date]"
        );

        const runTime = card.querySelector(
            "[data-trigger-time]"
        );

        const isSpecific = type.value === "specific_datetime";
        const isRecurring = type.value === "recurring";

        if (weekdays) {
            weekdays.hidden = !isRecurring;
        }

        if (runDate) {
            runDate.hidden = !isSpecific;
        }

        if (runTime) {
            runTime.hidden = !(isSpecific || isRecurring);
        }
    };

    const wireTaskCard = (card) => {
        const dueRule = card.querySelector(
            'select[name$="-due_rule"]'
        );

        if (dueRule && !dueRule.dataset.wired) {
            dueRule.dataset.wired = "1";

            dueRule.addEventListener(
                "change",
                () => refreshDueFields(card)
            );
        }

        const remove = card.querySelector(
            "[data-remove-template-task]"
        );

        if (remove && !remove.dataset.wired) {
            remove.dataset.wired = "1";

            remove.addEventListener("click", () => {
                const cards = activeCards("[data-template-task]");

                if (cards.length <= 1) {
                    return;
                }

                const deleteInput = card.querySelector(
                    'input[name$="-DELETE"]'
                );

                if (deleteInput) {
                    deleteInput.checked = true;
                }

                card.hidden = true;

                updateTaskNumbers();
                updateRemoveVisibility();
            });
        }

        refreshDueFields(card);
    };

    const wireTriggerCard = (card) => {
        const type = card.querySelector(
            'select[name$="-trigger_type"]'
        );

        if (type && !type.dataset.wired) {
            type.dataset.wired = "1";

            type.addEventListener(
                "change",
                () => refreshTriggerFields(card)
            );
        }

        const remove = card.querySelector(
            "[data-remove-template-trigger]"
        );

        if (remove && !remove.dataset.wired) {
            remove.dataset.wired = "1";

            remove.addEventListener("click", () => {
                const cards = activeCards("[data-template-trigger]");

                if (cards.length <= 1) {
                    return;
                }

                const deleteInput = card.querySelector(
                    'input[name$="-DELETE"]'
                );

                if (deleteInput) {
                    deleteInput.checked = true;
                }

                card.hidden = true;

                updateTriggerNumbers();
                updateRemoveVisibility();
            });
        }

        refreshTriggerFields(card);
    };

    const addFormFromTemplate = (
        template,
        list,
        totalInput,
        wire,
    ) => {
        if (!template || !list || !totalInput) {
            return;
        }

        const index = Number.parseInt(
            totalInput.value,
            10
        );

        const html = template.innerHTML.replaceAll(
            "__prefix__",
            String(index)
        );

        const wrapper = document.createElement("div");
        wrapper.innerHTML = html.trim();

        const card = wrapper.firstElementChild;

        if (!card) {
            return;
        }

        list.appendChild(card);
        totalInput.value = String(index + 1);

        wire(card);

        updateTaskNumbers();
        updateTriggerNumbers();
        updateRemoveVisibility();
    };

    builder.querySelectorAll("[data-template-task]").forEach(
        wireTaskCard
    );

    builder.querySelectorAll("[data-template-trigger]").forEach(
        wireTriggerCard
    );

    if (addTaskButton) {
        addTaskButton.addEventListener("click", () => {
            addFormFromTemplate(
                taskTemplate,
                taskList,
                taskTotal,
                wireTaskCard,
            );
        });
    }

    if (addTriggerButton) {
        addTriggerButton.addEventListener("click", () => {
            addFormFromTemplate(
                triggerTemplate,
                triggerList,
                triggerTotal,
                wireTriggerCard,
            );
        });
    }

    updateTaskNumbers();
    updateTriggerNumbers();
    updateRemoveVisibility();
});
