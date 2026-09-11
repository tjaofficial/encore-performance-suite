document.addEventListener("DOMContentLoaded", () => {
    const modal = document.getElementById("cancel-subscription-modal");
    const openButton = document.querySelector("[data-open-cancel-modal]");
    const closeButtons = document.querySelectorAll("[data-close-cancel-modal]");

    if (!modal || !openButton) {
        return;
    }

    openButton.addEventListener("click", () => {
        if (typeof modal.showModal === "function") {
            modal.showModal();
        } else {
            modal.setAttribute("open", "");
        }
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (typeof modal.close === "function") {
                modal.close();
            } else {
                modal.removeAttribute("open");
            }
        });
    });

    modal.addEventListener("click", (event) => {
        const rect = modal.getBoundingClientRect();

        const clickedBackdrop =
            event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom;

        if (clickedBackdrop && typeof modal.close === "function") {
            modal.close();
        }
    });
});
