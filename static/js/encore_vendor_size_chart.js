document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-vendor-size-chart-form]");
    if (!form) return;

    const stack = form.querySelector("[data-vendor-entry-stack]");
    const addButton = form.querySelector("[data-add-vendor-size]");
    const template = form.querySelector("[data-vendor-entry-template]");
    const totalForms = form.querySelector('input[name="entries-TOTAL_FORMS"]');

    if (!stack || !addButton || !template || !totalForms) return;

    const visibleEntries = () => Array.from(
        stack.querySelectorAll("[data-vendor-entry]")
    ).filter((entry) => !entry.hidden);

    const collapseEntry = (entry) => {
        const body = entry.querySelector("[data-vendor-entry-body]");
        const toggle = entry.querySelector("[data-vendor-entry-toggle]");
        if (body) body.hidden = true;
        if (toggle) toggle.setAttribute("aria-expanded", "false");
        entry.classList.remove("is-open");
    };

    const openEntry = (entry) => {
        visibleEntries().forEach((other) => {
            if (other !== entry) collapseEntry(other);
        });

        const body = entry.querySelector("[data-vendor-entry-body]");
        const toggle = entry.querySelector("[data-vendor-entry-toggle]");
        if (body) body.hidden = false;
        if (toggle) toggle.setAttribute("aria-expanded", "true");
        entry.classList.add("is-open");
    };

    const refreshEmptyState = () => {
        const empty = stack.querySelector("[data-vendor-entry-empty]");
        if (empty) empty.hidden = visibleEntries().length > 0;
    };

    const wireEntry = (entry) => {
        const toggle = entry.querySelector("[data-vendor-entry-toggle]");
        const body = entry.querySelector("[data-vendor-entry-body]");
        const remove = entry.querySelector("[data-remove-vendor-size]");
        const label = entry.querySelector("[data-vendor-entry-label]");
        const sizeInput = entry.querySelector('input[name$="-size_label"]');
        const deleteInput = entry.querySelector('input[name$="-DELETE"]');

        if (toggle && body) {
            toggle.addEventListener("click", () => {
                if (body.hidden) {
                    openEntry(entry);
                } else {
                    collapseEntry(entry);
                }
            });
        }

        if (sizeInput && label) {
            const refreshLabel = () => {
                label.textContent = sizeInput.value.trim() || "New Size";
            };
            sizeInput.addEventListener("input", refreshLabel);
            refreshLabel();
        }

        if (remove) {
            remove.addEventListener("click", () => {
                if (deleteInput) deleteInput.checked = true;
                entry.hidden = true;
                collapseEntry(entry);

                const next = visibleEntries()[0];
                if (next) openEntry(next);
                refreshEmptyState();
            });
        }
    };

    Array.from(stack.querySelectorAll("[data-vendor-entry]")).forEach(wireEntry);

    const initialEntries = visibleEntries();
    if (initialEntries.length) {
        openEntry(initialEntries[0]);
    }

    addButton.addEventListener("click", () => {
        const index = Number.parseInt(totalForms.value, 10) || 0;
        const html = template.innerHTML.replaceAll("__prefix__", String(index));
        const holder = document.createElement("div");
        holder.innerHTML = html.trim();
        const entry = holder.firstElementChild;
        if (!entry) return;

        const empty = stack.querySelector("[data-vendor-entry-empty]");
        if (empty) empty.hidden = true;

        stack.appendChild(entry);
        totalForms.value = String(index + 1);
        wireEntry(entry);
        openEntry(entry);

        const sizeInput = entry.querySelector('input[name$="-size_label"]');
        if (sizeInput) sizeInput.focus();

        entry.scrollIntoView({ behavior: "smooth", block: "center" });
    });

    refreshEmptyState();
});
