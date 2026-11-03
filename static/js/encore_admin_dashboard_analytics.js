document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-analytics-chart]").forEach((shell) => {
        const chart = shell.querySelector(".analytics-line-chart");
        const tooltip = shell.querySelector(".analytics-tooltip");

        if (!chart || !tooltip) {
            return;
        }

        const showTooltip = (point, clientX = null, clientY = null) => {
            const label = point.dataset.label || "";
            const value = point.dataset.value || "";

            tooltip.innerHTML = `<strong>${value}</strong><span>${label}</span>`;
            tooltip.hidden = false;

            const chartRect = chart.getBoundingClientRect();
            let left;
            let top;

            if (clientX !== null && clientY !== null) {
                left = clientX - chartRect.left;
                top = clientY - chartRect.top;
            } else {
                const pointRect = point.getBoundingClientRect();
                left = pointRect.left + (pointRect.width / 2) - chartRect.left;
                top = pointRect.top + (pointRect.height / 2) - chartRect.top;
            }

            const tooltipWidth = tooltip.offsetWidth;
            const tooltipHeight = tooltip.offsetHeight;
            const horizontalPadding = 8;
            const minLeft = (tooltipWidth / 2) + horizontalPadding;
            const maxLeft = chartRect.width - (tooltipWidth / 2) - horizontalPadding;
            const placeBelow = top < (tooltipHeight + 18);

            tooltip.classList.toggle("is-below", placeBelow);
            tooltip.style.left = `${Math.max(minLeft, Math.min(maxLeft, left))}px`;
            tooltip.style.top = `${top}px`;
        };

        const hideTooltip = () => {
            tooltip.hidden = true;
            tooltip.classList.remove("is-below");
        };

        shell.querySelectorAll(".analytics-data-point").forEach((point) => {
            point.addEventListener("mouseenter", (event) => {
                showTooltip(point, event.clientX, event.clientY);
            });

            point.addEventListener("mousemove", (event) => {
                showTooltip(point, event.clientX, event.clientY);
            });

            point.addEventListener("mouseleave", hideTooltip);
            point.addEventListener("focus", () => showTooltip(point));
            point.addEventListener("blur", hideTooltip);
        });
    });
});
