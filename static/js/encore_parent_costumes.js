document.addEventListener("click", function (event) {
    const opener = event.target.closest("[data-costume-modal-open]");
    if (opener) {
        const modal = document.getElementById(
            opener.getAttribute("data-costume-modal-open")
        );
        if (modal) {
            modal.hidden = false;
            document.body.classList.add("parent-modal-open");
        }
        return;
    }

    if (event.target.closest("[data-costume-modal-close]")) {
        const modal = event.target.closest("[data-costume-modal]");
        if (modal) {
            modal.hidden = true;
        }
        if (!document.querySelector("[data-costume-modal]:not([hidden])")) {
            document.body.classList.remove("parent-modal-open");
        }
    }
});

document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") {
        return;
    }

    document.querySelectorAll("[data-costume-modal]:not([hidden])").forEach(
        function (modal) {
            modal.hidden = true;
        }
    );
    document.body.classList.remove("parent-modal-open");
});
