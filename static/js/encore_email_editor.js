document.addEventListener("DOMContentLoaded", () => {
    const editors = document.querySelectorAll(
        "[data-email-editor]"
    );

    editors.forEach((editor) => {
        const source = editor.querySelector(
            "[data-email-html-source]"
        );
        const surface = editor.querySelector(
            "[data-editor-surface]"
        );
        const html = editor.querySelector(
            "[data-editor-html]"
        );
        const toolbar = editor.querySelector(
            "[data-editor-toolbar]"
        );
        const modeToggle = editor.querySelector(
            "[data-editor-mode-toggle]"
        );

        if (!source || !surface || !html || !modeToggle) {
            return;
        }

        let htmlMode = false;

        const syncFromSource = () => {
            surface.innerHTML = source.value || "";
            html.value = source.value || "";
        };

        const syncToSource = () => {
            source.value = (
                htmlMode
                ? html.value
                : surface.innerHTML
            );
        };

        const runCommand = (
            command,
            value = null
        ) => {
            surface.focus();
            document.execCommand(
                command,
                false,
                value
            );
            syncToSource();
        };

        editor.querySelectorAll(
            "[data-editor-command]"
        ).forEach((button) => {
            button.addEventListener(
                "click",
                () => runCommand(
                    button.dataset.editorCommand
                )
            );
        });

        const block = editor.querySelector(
            "[data-editor-block]"
        );

        if (block) {
            block.addEventListener(
                "change",
                () => runCommand(
                    "formatBlock",
                    block.value
                )
            );
        }

        const size = editor.querySelector(
            "[data-editor-size]"
        );

        if (size) {
            size.addEventListener(
                "change",
                () => runCommand(
                    "fontSize",
                    size.value
                )
            );
        }

        const color = editor.querySelector(
            "[data-editor-color]"
        );

        if (color) {
            color.addEventListener(
                "input",
                () => runCommand(
                    "foreColor",
                    color.value
                )
            );
        }

        const link = editor.querySelector(
            "[data-editor-link]"
        );

        if (link) {
            link.addEventListener(
                "click",
                () => {
                    const url = window.prompt(
                        "Enter the link URL:"
                    );

                    if (url) {
                        runCommand(
                            "createLink",
                            url
                        );
                    }
                }
            );
        }

        surface.addEventListener(
            "input",
            syncToSource
        );

        html.addEventListener(
            "input",
            syncToSource
        );

        modeToggle.addEventListener(
            "click",
            () => {
                if (htmlMode) {
                    surface.innerHTML = html.value;
                    surface.hidden = false;
                    html.hidden = true;
                    toolbar.classList.remove(
                        "html-mode"
                    );
                    modeToggle.textContent = "HTML";
                    htmlMode = false;
                } else {
                    html.value = surface.innerHTML;
                    surface.hidden = true;
                    html.hidden = false;
                    toolbar.classList.add(
                        "html-mode"
                    );
                    modeToggle.textContent = "Editor";
                    htmlMode = true;
                }

                syncToSource();
            }
        );

        const form = editor.closest("form");

        if (form) {
            form.addEventListener(
                "submit",
                syncToSource
            );
        }

        editor.addEventListener(
            "encore:set-html",
            (event) => {
                const value = (
                    event.detail
                    && typeof event.detail.html === "string"
                )
                    ? event.detail.html
                    : "";

                source.value = value;
                surface.innerHTML = value;
                html.value = value;
            }
        );

        syncFromSource();
    });
});
