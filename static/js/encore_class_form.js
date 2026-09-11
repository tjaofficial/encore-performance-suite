document.addEventListener("DOMContentLoaded", () => {
    const meetingList = document.querySelector("#class-meeting-list");
    const addMeetingButton = document.querySelector("#add-class-meeting");
    const template = document.querySelector("#empty-meeting-template");

    const updateMeetingNumbers = () => {
        if (!meetingList) {
            return;
        }

        const rows = Array.from(
            meetingList.querySelectorAll("[data-meeting-form]")
        );

        rows.forEach((row, index) => {
            const number = row.querySelector("[data-meeting-number]");

            if (number) {
                number.textContent = index + 1;
            }
        });
    };

    if (
        meetingList
        && addMeetingButton
        && template
    ) {
        const prefix = meetingList.dataset.formPrefix;
        const totalInput = document.querySelector(
            `#id_${prefix}-TOTAL_FORMS`
        );

        addMeetingButton.addEventListener("click", () => {
            if (!totalInput) {
                return;
            }

            const index = Number(totalInput.value);
            const html = template.innerHTML.replaceAll(
                "__prefix__",
                index
            );

            meetingList.insertAdjacentHTML(
                "beforeend",
                html
            );

            totalInput.value = index + 1;

            updateMeetingNumbers();
        });

        meetingList.addEventListener("click", (event) => {
            const removeButton = event.target.closest(
                "[data-remove-new-meeting]"
            );

            if (!removeButton) {
                return;
            }

            const row = removeButton.closest(
                "[data-meeting-form]"
            );

            if (row) {
                row.remove();
                updateMeetingNumbers();
            }
        });

        updateMeetingNumbers();
    }

    const allowDropIns = document.querySelector(
        "#id_allow_drop_ins"
    );

    const dropInPanel = document.querySelector(
        "#drop-in-price-panel"
    );

    const refreshDropInPrice = () => {
        if (!allowDropIns || !dropInPanel) {
            return;
        }

        dropInPanel.classList.toggle(
            "visible",
            allowDropIns.checked
        );
    };

    if (allowDropIns) {
        allowDropIns.addEventListener(
            "change",
            refreshDropInPrice
        );

        refreshDropInPrice();
    }
});
