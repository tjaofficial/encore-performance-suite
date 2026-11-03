document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-quick-task]").forEach((wrapper) => {
        const trigger = wrapper.querySelector("[data-quick-task-trigger]");
        const form = wrapper.querySelector("[data-quick-task-form]");
        const input = wrapper.querySelector("[data-quick-task-input]");

        if (!trigger || !form || !input) {
            return;
        }

        const open = () => {
            trigger.hidden = true;
            form.hidden = false;

            requestAnimationFrame(() => {
                input.focus();
            });
        };

        const close = () => {
            if (input.value.trim()) {
                return;
            }

            form.hidden = true;
            trigger.hidden = false;
        };

        trigger.addEventListener("click", open);

        input.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                event.preventDefault();
                input.value = "";
                close();
                trigger.focus();
                return;
            }

            if (event.key === "Enter") {
                if (!input.value.trim()) {
                    event.preventDefault();
                    close();
                    trigger.focus();
                }
            }
        });

        input.addEventListener("blur", () => {
            window.setTimeout(close, 100);
        });
    });

    document.querySelectorAll(".task-complete-form, .dashboard-task-complete").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (form.dataset.submitting === "true") {
                event.preventDefault();
                return;
            }

            event.preventDefault();
            form.dataset.submitting = "true";

            const row = form.closest(
                ".dashboard-task-row, "
                + ".class-task-row, "
                + ".teacher-task-row, "
                + ".admin-task-row, "
                + ".student-task-row, "
                + ".task-list-row"
            );

            const button = form.querySelector("button");

            if (button) {
                button.disabled = true;
                button.setAttribute("aria-pressed", "true");
            }

            if (row) {
                row.classList.add("task-completing");

                /*
                 * Let the user see the completed state for one full second:
                 * filled circle + strikethrough text.
                 */
                window.setTimeout(() => {
                    row.classList.add("task-removing");

                    /*
                     * Fade/collapse the row, then perform the existing
                     * Django form submission so completion is persisted.
                     */
                    window.setTimeout(() => {
                        form.submit();
                    }, 180);
                }, 1000);

                return;
            }

            /*
             * Fallback for a completion form used outside a recognized row:
             * preserve the one-second feedback delay, then submit normally.
             */
            window.setTimeout(() => {
                form.submit();
            }, 1000);
        });
    });
});



document.addEventListener("DOMContentLoaded", () => {
    const menus = Array.from(
        document.querySelectorAll("[data-task-menu]")
    );

    let openMenu = null;
    let openButton = null;
    let originalParent = null;
    let originalNextSibling = null;

    const restoreOpenMenu = () => {
        if (!openMenu) {
            return;
        }

        openMenu.hidden = true;
        openMenu.classList.remove(
            "task-menu-floating"
        );

        if (originalParent) {
            originalParent.insertBefore(
                openMenu,
                originalNextSibling
            );
        }

        if (openButton) {
            openButton.setAttribute(
                "aria-expanded",
                "false"
            );
        }

        openMenu = null;
        openButton = null;
        originalParent = null;
        originalNextSibling = null;
    };

    const positionMenu = (
        button,
        popover
    ) => {
        const rect = (
            button.getBoundingClientRect()
        );

        const menuWidth = (
            popover.offsetWidth
            || 110
        );

        const viewportPadding = 8;

        let left = (
            rect.right
            - menuWidth
        );

        if (left < viewportPadding) {
            left = viewportPadding;
        }

        let top = rect.bottom + 5;

        const menuHeight = (
            popover.offsetHeight
            || 70
        );

        if (
            top + menuHeight
            > window.innerHeight - viewportPadding
        ) {
            top = (
                rect.top
                - menuHeight
                - 5
            );
        }

        popover.style.left = `${left}px`;
        popover.style.top = `${top}px`;
    };

    menus.forEach((menu) => {
        const button = menu.querySelector(
            "[data-task-menu-button]"
        );

        const popover = menu.querySelector(
            "[data-task-menu-popover]"
        );

        if (!button || !popover) {
            return;
        }

        button.addEventListener(
            "click",
            (event) => {
                event.preventDefault();
                event.stopPropagation();

                if (
                    openMenu === popover
                    && !popover.hidden
                ) {
                    restoreOpenMenu();
                    return;
                }

                restoreOpenMenu();

                originalParent = popover.parentNode;
                originalNextSibling = (
                    popover.nextSibling
                );

                document.body.appendChild(
                    popover
                );

                popover.classList.add(
                    "task-menu-floating"
                );

                popover.hidden = false;

                openMenu = popover;
                openButton = button;

                button.setAttribute(
                    "aria-expanded",
                    "true"
                );

                positionMenu(
                    button,
                    popover
                );
            }
        );

        popover.addEventListener(
            "click",
            (event) => {
                event.stopPropagation();
            }
        );
    });

    document.addEventListener(
        "click",
        () => {
            restoreOpenMenu();
        }
    );

    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key === "Escape") {
                restoreOpenMenu();
            }
        }
    );

    window.addEventListener(
        "resize",
        () => {
            if (
                openMenu
                && openButton
            ) {
                positionMenu(
                    openButton,
                    openMenu
                );
            }
        }
    );

    window.addEventListener(
        "scroll",
        () => {
            if (
                openMenu
                && openButton
            ) {
                positionMenu(
                    openButton,
                    openMenu
                );
            }
        },
        true
    );
});
