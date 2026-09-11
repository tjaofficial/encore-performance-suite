document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("toggle-password");

    if (!toggle) {
        return;
    }

    const input = toggle
        .closest(".password-field")
        .querySelector("input");

    toggle.addEventListener("click", () => {
        const showing = input.type === "text";

        input.type = showing ? "password" : "text";
        toggle.textContent = showing ? "Show" : "Hide";
        toggle.setAttribute(
            "aria-label",
            showing ? "Show password" : "Hide password"
        );
    });
});
