(() => {
    "use strict";

    const config = document.getElementById("encore-tour-config");
    if (!config) return;

    const page = config.dataset.tourPage || "";
    const updateUrl = config.dataset.tourUpdateUrl || "";
    const dataUrl = config.dataset.tourDataUrl || "";
    const meetingUrl = config.dataset.tourMeetingUrl || "";
    const supportUrl = config.dataset.tourSupportUrl || "/support/";
    let currentStep = Number.parseInt(config.dataset.tourStep || "0", 10);
    if (Number.isNaN(currentStep)) currentStep = 0;

    const ui = {
        blockers: [],
        holeBlocker: null,
        outline: null,
        card: null,
        arrow: null,
        target: null,
        resizeHandler: null,
        targetClickHandler: null,
    };

    const getCookie = (name) => {
        const cookie = document.cookie
            .split(";")
            .map((value) => value.trim())
            .find((value) => value.startsWith(`${name}=`));
        return cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";
    };

    const saveState = async (action, step = currentStep) => {
        if (!updateUrl) return;
        try {
            await fetch(updateUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCookie("csrftoken"),
                },
                body: JSON.stringify({ action, step }),
            });
        } catch (error) {
            console.warn("Encore tour state could not be saved.", error);
        }
    };

    const removeNode = (node) => {
        if (node && node.parentNode) node.parentNode.removeChild(node);
    };

    const cleanup = () => {
        ui.blockers.forEach(removeNode);
        ui.blockers = [];
        removeNode(ui.holeBlocker);
        removeNode(ui.outline);
        removeNode(ui.card);
        removeNode(ui.arrow);
        ui.holeBlocker = null;
        ui.outline = null;
        ui.card = null;
        ui.arrow = null;

        if (ui.target && ui.targetClickHandler) {
            ui.target.removeEventListener("click", ui.targetClickHandler, true);
        }
        ui.target = null;
        ui.targetClickHandler = null;

        if (ui.resizeHandler) {
            window.removeEventListener("resize", ui.resizeHandler);
            window.removeEventListener("scroll", ui.resizeHandler, true);
            ui.resizeHandler = null;
        }
    };

    const finishVisuals = () => {
        cleanup();
        document.body.classList.remove("encore-tour-active");
    };

    const createBlocker = (left, top, width, height) => {
        if (width <= 0 || height <= 0) return;
        const blocker = document.createElement("div");
        blocker.className = "encore-tour-blocker";
        Object.assign(blocker.style, {
            left: `${left}px`,
            top: `${top}px`,
            width: `${width}px`,
            height: `${height}px`,
        });
        document.body.appendChild(blocker);
        ui.blockers.push(blocker);
    };

    const positionSpotlight = (target, allowTargetClick) => {
        ui.blockers.forEach(removeNode);
        ui.blockers = [];
        removeNode(ui.holeBlocker);
        removeNode(ui.outline);
        ui.holeBlocker = null;
        ui.outline = null;

        if (!target) {
            createBlocker(0, 0, window.innerWidth, window.innerHeight);
            return null;
        }

        const raw = target.getBoundingClientRect();
        const pad = 8;
        const left = Math.max(8, raw.left - pad);
        const top = Math.max(8, raw.top - pad);
        const right = Math.min(window.innerWidth - 8, raw.right + pad);
        const bottom = Math.min(window.innerHeight - 8, raw.bottom + pad);
        const width = Math.max(0, right - left);
        const height = Math.max(0, bottom - top);

        createBlocker(0, 0, window.innerWidth, top);
        createBlocker(0, top, left, height);
        createBlocker(right, top, window.innerWidth - right, height);
        createBlocker(0, bottom, window.innerWidth, window.innerHeight - bottom);

        if (!allowTargetClick) {
            const blocker = document.createElement("div");
            blocker.className = "encore-tour-hole-blocker";
            Object.assign(blocker.style, {
                left: `${left}px`,
                top: `${top}px`,
                width: `${width}px`,
                height: `${height}px`,
            });
            document.body.appendChild(blocker);
            ui.holeBlocker = blocker;
        }

        const outline = document.createElement("div");
        outline.className = "encore-tour-outline";
        Object.assign(outline.style, {
            left: `${left}px`,
            top: `${top}px`,
            width: `${width}px`,
            height: `${height}px`,
        });
        document.body.appendChild(outline);
        ui.outline = outline;

        return { left, top, right, bottom, width, height };
    };

    const positionCard = (card, rect, placement) => {
        const gap = 18;
        const margin = 12;
        const cardRect = card.getBoundingClientRect();
        let left = Math.max(margin, (window.innerWidth - cardRect.width) / 2);
        let top = Math.max(margin, (window.innerHeight - cardRect.height) / 2);

        if (rect) {
            if (placement === "below") {
                left = Math.min(
                    window.innerWidth - cardRect.width - margin,
                    Math.max(margin, rect.left + (rect.width - cardRect.width) / 2)
                );
                top = rect.bottom + gap;
                if (top + cardRect.height > window.innerHeight - margin) {
                    top = Math.max(margin, rect.top - cardRect.height - gap);
                }
            } else if (placement === "right") {
                left = rect.right + gap;
                top = Math.min(
                    window.innerHeight - cardRect.height - margin,
                    Math.max(margin, rect.top + 20)
                );
                if (left + cardRect.width > window.innerWidth - margin) {
                    left = Math.max(margin, rect.left - cardRect.width - gap);
                }
            } else if (placement === "above") {
                left = Math.min(
                    window.innerWidth - cardRect.width - margin,
                    Math.max(margin, rect.left + rect.width - cardRect.width)
                );
                top = rect.top - cardRect.height - gap;
                if (top < margin) top = rect.bottom + gap;
            }
        }

        card.style.left = `${Math.round(left)}px`;
        card.style.top = `${Math.round(top)}px`;
    };

    const positionArrow = (rect) => {
        removeNode(ui.arrow);
        ui.arrow = null;
        if (!rect) return;

        const arrow = document.createElement("div");
        arrow.className = "encore-tour-arrow";
        arrow.textContent = "←";
        arrow.style.left = `${Math.max(10, rect.right + 8)}px`;
        arrow.style.top = `${Math.max(10, rect.top + (rect.height / 2) - 22)}px`;

        if (rect.right + 60 > window.innerWidth) {
            arrow.textContent = "→";
            arrow.style.left = `${Math.max(10, rect.left - 52)}px`;
        }

        document.body.appendChild(arrow);
        ui.arrow = arrow;
    };

    const stepDefinitions = {
        0: {
            page: "settings",
            title: "Welcome to Encore Performance Suite!",
            kicker: "Welcome",
            body: `
                <p>Thank you for choosing Encore to help run your studio.</p>
                <p>We’ll give you a short guided tour of the workspace, then show you the best place to begin bringing your existing studio information into Encore.</p>
            `,
            selector: null,
            placement: "center",
        },
        1: {
            page: "settings",
            title: "Your header keeps the essentials close.",
            kicker: "1 · Header",
            body: `
                <p>The header includes your personal greeting, the current date, notifications, and your profile menu for quick access to Profile and Settings.</p>
                <p>Your studio logo and branding can be customized from Settings.</p>
            `,
            selector: '[data-encore-tour-target="header"]',
            placement: "below",
        },
        2: {
            page: "settings",
            title: "Your studio command center.",
            kicker: "2 · Navigation",
            body: `
                <p>The sidebar gives you fast access to Encore’s day-to-day management tools, including classes, enrollments, students, families, instructors, communications, reports, performance tools, and more.</p>
            `,
            selector: '[data-encore-tour-target="sidebar"]',
            placement: "right",
        },
        3: {
            page: "settings",
            title: "Start by bringing your studio into Encore.",
            kicker: "3 · Data Import & Export",
            body: `
                <p>This Settings area lets you personalize Encore for the way your studio operates.</p>
                <p>For a new studio, we recommend starting with <strong>Data Import &amp; Export</strong>. Click the highlighted row or use Next to continue.</p>
            `,
            selector: '[data-encore-tour-target="data-transfer"]',
            placement: "above",
            allowTargetClick: true,
            arrow: true,
        },
        4: {
            page: "data-transfer",
            title: "Choose the onboarding path that fits your studio.",
            kicker: "4 · Guided Onboarding",
            body: `
                <p>Encore can guide you through a supported vendor migration flow, such as Studio Director, with step-by-step tools built for that system.</p>
                <p>If you’d rather have help planning the move, <a href="${meetingUrl}">request an onboarding meeting with Encore</a> and we’ll review your studio’s migration needs with you.</p>
            `,
            selector: '[data-encore-tour-target="vendor-onboarding"]',
            placement: "below",
        },
        5: {
            page: "data-transfer",
            title: "You can also import files manually.",
            kicker: "5 · Import Data",
            body: `
                <p>If you already know which CSV files you want to move, you can use Import Data without the guided vendor process.</p>
                <p>Encore will help you identify the file, map its columns, validate the records, and import the data into your studio.</p>
            `,
            selector: '[data-encore-tour-target="import-data"]',
            placement: "above",
        },
        6: {
            page: "data-transfer",
            title: "You’re ready to get started!",
            kicker: "6 · You’re Ready",
            body: `
                <p>Encore has a lot more waiting for you, but you do not have to learn everything at once.</p>
                <p>Whenever you need help, visit the <a href="${supportUrl}" target="_blank" rel="noopener">Support Center</a> for step-by-step directions, feature explanations, automatic functions, common questions, and related help articles.</p>
                <p>You can return to the Support Center anytime from the Encore sidebar or your profile menu.</p>
            `,
            selector: null,
            placement: "center",
            final: true,
        },
    };

    const render = async (stepNumber) => {
        cleanup();
        currentStep = stepNumber;

        const definition = stepDefinitions[currentStep];
        if (!definition) {
            finishVisuals();
            return;
        }

        if (definition.page !== page) {
            if (definition.page === "data-transfer" && dataUrl) {
                window.location.assign(dataUrl);
            }
            return;
        }

        document.body.classList.add("encore-tour-active");

        const target = definition.selector
            ? document.querySelector(definition.selector)
            : null;
        ui.target = target;

        if (definition.selector && !target) {
            console.warn("Encore tour target not found:", definition.selector);
            return;
        }

        if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
            await new Promise((resolve) => window.setTimeout(resolve, 280));
        }

        const card = document.createElement("section");
        card.className = `encore-tour-card${currentStep === 0 ? " is-welcome" : ""}`;
        card.setAttribute("role", "dialog");
        card.setAttribute("aria-modal", "true");
        card.innerHTML = `
            <span class="encore-tour-kicker">${definition.kicker}</span>
            <h2>${definition.title}</h2>
            ${definition.body}
            <div class="encore-tour-actions">
                <button type="button" class="encore-tour-button secondary" data-tour-skip>Skip Tutorial</button>
                <button type="button" class="encore-tour-button primary" data-tour-next>${definition.final ? "Finish" : "Next"}</button>
            </div>
            ${currentStep > 0 ? `<div class="encore-tour-step-label">Step ${Math.min(currentStep, 6)} of 6</div>` : ""}
        `;
        document.body.appendChild(card);
        ui.card = card;

        const layout = () => {
            const rect = positionSpotlight(target, Boolean(definition.allowTargetClick));
            positionCard(card, rect, definition.placement);
            if (definition.arrow) positionArrow(rect);
        };
        layout();
        ui.resizeHandler = layout;
        window.addEventListener("resize", layout);
        window.addEventListener("scroll", layout, true);

        card.querySelector("[data-tour-skip]")?.addEventListener("click", async () => {
            await saveState("skip", currentStep);
            finishVisuals();
        });

        card.querySelector("[data-tour-next]")?.addEventListener("click", async () => {
            if (definition.final) {
                await saveState("complete", currentStep);
                finishVisuals();
                return;
            }

            const nextStep = currentStep + 1;
            await saveState("progress", nextStep);
            if (currentStep === 3 && dataUrl) {
                window.location.assign(dataUrl);
                return;
            }
            render(nextStep);
        });

        if (currentStep === 3 && target) {
            ui.targetClickHandler = async (event) => {
                event.preventDefault();
                const href = target.getAttribute("href") || dataUrl;
                await saveState("progress", 4);
                window.location.assign(href);
            };
            target.addEventListener("click", ui.targetClickHandler, true);
        }

        card.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", async () => {
                await saveState("progress", currentStep);
            });
        });
    };

    if (page === "data-transfer" && currentStep < 4) {
        currentStep = 4;
        saveState("progress", 4).finally(() => render(4));
    } else {
        render(currentStep);
    }
})();
