document.addEventListener("DOMContentLoaded", () => {
    const rows = document.querySelectorAll(
        "[data-costume-assignment]"
    );

    const csrf = () => {
        const item = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith("csrftoken="));

        return item
            ? decodeURIComponent(item.split("=")[1])
            : "";
    };

    rows.forEach((row) => {
        row.querySelectorAll(
            "[data-assignment-field]"
        ).forEach((field) => {
            let timer = null;

            const save = async () => {
                const body = new URLSearchParams({
                    field: field.dataset.assignmentField,
                    value: field.value,
                });

                const response = await fetch(
                    row.dataset.saveUrl,
                    {
                        method: "POST",
                        headers: {
                            "X-CSRFToken": csrf(),
                            "X-Requested-With": "XMLHttpRequest",
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        body,
                    }
                );

                row.classList.toggle(
                    "save-error",
                    !response.ok
                );
            };

            field.addEventListener("change", save);

            if (
                field.tagName === "INPUT"
                || field.tagName === "TEXTAREA"
            ) {
                field.addEventListener("input", () => {
                    if (timer) {
                        window.clearTimeout(timer);
                    }

                    timer = window.setTimeout(
                        save,
                        450
                    );
                });
            }
        });
    });
});
