document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector(
        "#dashboard-layout-form"
    );

    const hidden = document.querySelector(
        "#quick-links-json"
    );

    if (!form || !hidden) {
        return;
    }

    const status = document.querySelector(
        "#layout-save-status"
    );

    const markDirty = () => {
        if (status) {
            status.textContent = (
                "You have unsaved layout changes."
            );
        }
    };

    const serializeQuickLinks = () => {
        const enabled = {};

        document.querySelectorAll(
            "[data-quick-link-enabled]"
        ).forEach((checkbox) => {
            enabled[
                checkbox.dataset.quickLinkEnabled
            ] = checkbox.checked;
        });

        const labels = Array.from(
            document.querySelectorAll(
                "[data-custom-quick-link-label]"
            )
        );

        const urls = Array.from(
            document.querySelectorAll(
                "[data-custom-quick-link-url]"
            )
        );

        const custom = labels.map(
            (input, index) => ({
                label: input.value.trim(),
                url: (
                    urls[index]
                    ? urls[index].value.trim()
                    : ""
                ),
            })
        );

        hidden.value = JSON.stringify({
            enabled,
            custom,
        });
    };

    document.querySelectorAll(
        "[data-quick-link-enabled], "
        + "[data-custom-quick-link-label], "
        + "[data-custom-quick-link-url]"
    ).forEach((field) => {
        field.addEventListener(
            "change",
            () => {
                serializeQuickLinks();
                markDirty();
            }
        );

        field.addEventListener(
            "input",
            () => {
                serializeQuickLinks();
                markDirty();
            }
        );
    });

    form.addEventListener(
        "submit",
        (event) => {
            if (
                !event.submitter
                || event.submitter.value !== "reset"
            ) {
                serializeQuickLinks();
            }
        }
    );

    serializeQuickLinks();
});
