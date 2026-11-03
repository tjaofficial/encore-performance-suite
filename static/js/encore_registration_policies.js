(() => {
    const form = document.querySelector("[data-policy-form]");
    if (!form) return;

    const input = form.querySelector("[data-policy-html-input]");
    const surface = form.querySelector("[data-editor-surface]");
    const scope = form.querySelector("[data-policy-scope]");
    const classPicker = form.querySelector("[data-policy-class-picker]");
    const classSearch = form.querySelector("[data-policy-class-search]");

    function syncHtml() {
        if (input && surface) input.value = surface.innerHTML.trim();
    }

    function focusSurface() {
        surface?.focus();
    }

    form.querySelectorAll("[data-editor-command]").forEach((button) => {
        button.addEventListener("mousedown", (event) => event.preventDefault());
        button.addEventListener("click", () => {
            focusSurface();
            document.execCommand(button.dataset.editorCommand, false, null);
            syncHtml();
        });
    });

    form.querySelector("[data-editor-block]")?.addEventListener("change", (event) => {
        focusSurface();
        document.execCommand("formatBlock", false, event.target.value);
        syncHtml();
    });

    form.querySelector("[data-editor-font]")?.addEventListener("change", (event) => {
        focusSurface();
        document.execCommand("fontName", false, event.target.value);
        syncHtml();
    });

    form.querySelector("[data-editor-size]")?.addEventListener("change", (event) => {
        focusSurface();
        document.execCommand("fontSize", false, event.target.value);
        syncHtml();
    });

    form.querySelector("[data-editor-link]")?.addEventListener("mousedown", (event) => event.preventDefault());
    form.querySelector("[data-editor-link]")?.addEventListener("click", () => {
        focusSurface();
        let url = window.prompt("Enter the URL for this link:", "https://");
        if (!url) return;
        url = url.trim();
        if (!/^(https?:\/\/|mailto:|tel:)/i.test(url)) {
            url = `https://${url}`;
        }
        document.execCommand("createLink", false, url);
        syncHtml();
    });

    surface?.addEventListener("input", syncHtml);
    surface?.addEventListener("blur", syncHtml);
    form.addEventListener("submit", syncHtml);

    function updateScope() {
        if (!scope || !classPicker) return;
        classPicker.hidden = scope.value !== "specific_classes";
    }
    scope?.addEventListener("change", updateScope);
    updateScope();

    classSearch?.addEventListener("input", () => {
        const query = classSearch.value.trim().toLowerCase();
        form.querySelectorAll("[data-class-option]").forEach((option) => {
            option.hidden = Boolean(query) && !option.dataset.search.includes(query);
        });
    });
})();
