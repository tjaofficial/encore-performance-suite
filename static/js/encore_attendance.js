document.addEventListener("DOMContentLoaded", () => {
    document
        .querySelectorAll("[data-attendance-group]")
        .forEach((group) => {
            const choices = group.querySelectorAll(
                ".attendance-choice"
            );

            choices.forEach((choice) => {
                const input = choice.querySelector("input");

                input.addEventListener("change", () => {
                    choices.forEach((item) => {
                        item.classList.remove("selected");
                    });

                    if (input.checked) {
                        choice.classList.add("selected");
                    }
                });
            });
        });
});
