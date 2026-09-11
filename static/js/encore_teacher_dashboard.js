document.addEventListener("DOMContentLoaded", () => {
    const widget = document.querySelector(
        "[data-teacher-class-widget]"
    );

    if (!widget) {
        return;
    }

    const selectors = Array.from(
        widget.querySelectorAll(
            "[data-class-selector]"
        )
    );

    const panels = Array.from(
        widget.querySelectorAll(
            "[data-class-panel]"
        )
    );

    const placeholder = widget.querySelector(
        "[data-class-placeholder]"
    );

    if (!selectors.length || !panels.length) {
        return;
    }

    const selectClass = (index) => {
        selectors.forEach((selector) => {
            const selected = (
                Number(
                    selector.dataset.classIndex
                ) === index
            );

            selector.classList.toggle(
                "is-selected",
                selected
            );

            selector.setAttribute(
                "aria-pressed",
                String(selected)
            );
        });

        panels.forEach((panel) => {
            const selected = (
                Number(
                    panel.dataset.classIndex
                ) === index
            );

            panel.hidden = !selected;
        });

        if (placeholder) {
            placeholder.hidden = true;
        }
    };

    selectors.forEach((selector) => {
        selector.addEventListener(
            "click",
            () => {
                selectClass(
                    Number(
                        selector.dataset.classIndex
                    )
                );
            }
        );
    });

    selectors.forEach((selector) => {
        selector.classList.remove(
            "is-selected"
        );

        selector.setAttribute(
            "aria-pressed",
            "false"
        );
    });

    panels.forEach((panel) => {
        panel.hidden = true;
    });

    if (placeholder) {
        placeholder.hidden = false;
    }
});
