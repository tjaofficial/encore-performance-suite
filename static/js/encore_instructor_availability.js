document.addEventListener("DOMContentLoaded", () => {
    const editor = document.querySelector("[data-availability-editor]");
    if (!editor) return;

    const list = editor.querySelector("[data-availability-list]");
    const template = editor.querySelector("[data-availability-template]");
    const hidden = editor.querySelector("[data-availability-json]");
    const add = editor.querySelector("[data-add-availability]");
    const initialNode = document.getElementById("availability-initial-data");

    let initial = [];
    try {
        initial = JSON.parse(initialNode?.textContent || "[]");
    } catch (_) {
        initial = [];
    }

    const rowData = (row) => ({
        status: row.querySelector("[data-availability-status]")?.value || "available",
        days: Array.from(row.querySelectorAll("[data-availability-day]:checked"))
            .map((box) => Number(box.value)),
        start: row.querySelector("[data-availability-start]")?.value || "",
        end: row.querySelector("[data-availability-end]")?.value || "",
        notes: row.querySelector("[data-availability-notes]")?.value.trim() || "",
    });

    const sync = () => {
        const rows = Array.from(list.querySelectorAll("[data-availability-block]"));
        hidden.value = JSON.stringify(rows.map(rowData));

        rows.forEach((row, index) => {
            const title = row.querySelector("[data-availability-title]");
            if (title) title.textContent = `Availability ${index + 1}`;
        });
    };

    const applyPreset = (row, preset) => {
        const boxes = Array.from(row.querySelectorAll("[data-availability-day]"));
        const wanted = {
            weekdays: new Set([0, 1, 2, 3, 4]),
            weekends: new Set([5, 6]),
            everyday: new Set([0, 1, 2, 3, 4, 5, 6]),
            clear: new Set(),
        }[preset] || new Set();

        boxes.forEach((box) => {
            box.checked = wanted.has(Number(box.value));
        });
        sync();
    };

    const addRow = (data = {}) => {
        const fragment = template.content.cloneNode(true);
        const row = fragment.querySelector("[data-availability-block]");

        row.querySelector("[data-availability-status]").value =
            data.status || "available";
        row.querySelector("[data-availability-start]").value =
            data.start || "";
        row.querySelector("[data-availability-end]").value =
            data.end || "";
        row.querySelector("[data-availability-notes]").value =
            data.notes || "";

        const days = new Set((data.days || []).map(Number));
        row.querySelectorAll("[data-availability-day]").forEach((box) => {
            box.checked = days.has(Number(box.value));
        });

        row.querySelectorAll("input, select, textarea").forEach((field) => {
            field.addEventListener("input", sync);
            field.addEventListener("change", sync);
        });

        row.querySelectorAll("[data-day-preset]").forEach((button) => {
            button.addEventListener("click", () => {
                applyPreset(row, button.dataset.dayPreset);
            });
        });

        row.querySelector("[data-remove-availability]")?.addEventListener(
            "click",
            () => {
                row.remove();
                sync();
            }
        );

        list.appendChild(fragment);
        sync();
    };

    add?.addEventListener("click", () => addRow());

    if (initial.length) {
        initial.forEach(addRow);
    } else {
        addRow();
    }

    editor.closest("form")?.addEventListener("submit", sync);
});
