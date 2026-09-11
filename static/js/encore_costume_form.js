document.addEventListener("DOMContentLoaded", () => {
    const createTask = document.querySelector(
        "#id_create_student_task"
    );

    const dueBlock = document.querySelector(
        "[data-task-due]"
    );

    const refreshTaskDue = () => {
        if (!createTask || !dueBlock) {
            return;
        }

        dueBlock.hidden = !createTask.checked;
    };

    if (createTask) {
        createTask.addEventListener(
            "change",
            refreshTaskDue
        );

        refreshTaskDue();
    }

    const addLink = document.querySelector(
        "[data-add-costume-link]"
    );

    const linkList = document.querySelector(
        "[data-costume-link-list]"
    );

    const totalForms = document.querySelector(
        "#id_links-TOTAL_FORMS"
    );

    const emptyTemplate = document.querySelector(
        "#costume-link-empty-form"
    );

    if (
        addLink
        && linkList
        && totalForms
        && emptyTemplate
    ) {
        addLink.addEventListener("click", () => {
            const index = Number.parseInt(
                totalForms.value,
                10
            );

            const html = emptyTemplate.innerHTML.replaceAll(
                "__prefix__",
                String(index)
            );

            const wrapper = document.createElement("div");
            wrapper.innerHTML = html.trim();

            const row = wrapper.firstElementChild;

            if (!row) {
                return;
            }

            linkList.appendChild(row);
            totalForms.value = String(index + 1);
        });
    }
});
