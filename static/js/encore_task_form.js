document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-task-form]");

    if (!form) {
        return;
    }

    const audience = document.querySelector("#id_audience_type");
    const classSelect = document.querySelector("#id_class_instance");
    const teachersBlock = document.querySelector("[data-selected-teachers]");
    const studentsBlock = document.querySelector("[data-selected-students]");
    const studentOptions = document.querySelector("[data-student-options]");
    const rosterUrl = form.dataset.rosterUrl;

    const refreshAudience = () => {
        const value = audience ? audience.value : "";

        if (teachersBlock) {
            teachersBlock.hidden = value !== "selected_teachers";
        }

        if (studentsBlock) {
            studentsBlock.hidden = value !== "selected_students";
        }
    };

    const loadRoster = async () => {
        if (
            !classSelect
            || !studentOptions
            || !rosterUrl
            || !classSelect.value
        ) {
            return;
        }

        try {
            const response = await fetch(
                `${rosterUrl}?class_id=${encodeURIComponent(classSelect.value)}`,
                {
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                }
            );

            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            const wrapper = document.createElement("div");
            wrapper.className = "task-checkbox-list";

            payload.results.forEach((student) => {
                const label = document.createElement("label");
                label.className = "task-checkbox-option";

                const input = document.createElement("input");
                input.type = "checkbox";
                input.name = "selected_students";
                input.value = student.id;

                const span = document.createElement("span");
                span.textContent = student.label;

                label.append(input, span);
                wrapper.appendChild(label);
            });

            studentOptions.replaceChildren(wrapper);
        } catch {
            // Keep server-rendered roster choices if refresh fails.
        }
    };

    if (audience) {
        audience.addEventListener(
            "change",
            refreshAudience
        );
    }

    if (classSelect) {
        classSelect.addEventListener(
            "change",
            loadRoster
        );
    }

    refreshAudience();
});
