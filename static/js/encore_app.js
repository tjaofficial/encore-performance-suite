document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("mobile-nav-toggle");
    const closeTargets = document.querySelectorAll(
        "[data-mobile-nav-close]"
    );

    const profileMenu = document.querySelector("[data-profile-menu]");
    const profileToggle = document.querySelector("[data-profile-menu-toggle]");
    const profileDropdown = document.querySelector("[data-profile-menu-dropdown]");

    const openNav = () => {
        document.body.classList.add("mobile-nav-open");
    };

    const closeNav = () => {
        document.body.classList.remove("mobile-nav-open");
    };

    const closeProfileMenu = () => {
        if (!profileToggle || !profileDropdown) {
            return;
        }

        profileDropdown.hidden = true;
        profileToggle.setAttribute("aria-expanded", "false");
    };

    const toggleProfileMenu = () => {
        if (!profileToggle || !profileDropdown) {
            return;
        }

        const isOpen = !profileDropdown.hidden;
        profileDropdown.hidden = isOpen;
        profileToggle.setAttribute("aria-expanded", String(!isOpen));
    };

    if (toggle) {
        toggle.addEventListener("click", openNav);
    }

    closeTargets.forEach((element) => {
        element.addEventListener("click", closeNav);
    });

    if (profileToggle) {
        profileToggle.addEventListener("click", (event) => {
            event.stopPropagation();
            toggleProfileMenu();
        });
    }

    document.addEventListener("click", (event) => {
        if (profileMenu && !profileMenu.contains(event.target)) {
            closeProfileMenu();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeNav();
            closeProfileMenu();
        }
    });
});
