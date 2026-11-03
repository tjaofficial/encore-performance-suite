document.addEventListener("DOMContentLoaded", () => {
    const card = document.querySelector("[data-vendor-attach-card]");
    if (!card) return;
    const attach = card.querySelector("[data-attach-vendor]");
    const fields = card.querySelector("[data-vendor-fields]");
    const vendor = document.getElementById("id_vendor");
    const chart = document.getElementById("id_vendor_size_chart");
    const preview = card.querySelector("[data-vendor-preview]");

    const renderVendorPreview = () => {
        if (!preview || !vendor || !vendor.value) {
            if (preview) preview.innerHTML = "";
            return;
        }

        const source = card.querySelector(`[data-vendor-info-id="${vendor.value}"]`);
        if (!source) {
            preview.innerHTML = "";
            return;
        }

        const parts = [];
        if (source.dataset.vendorContact) parts.push(source.dataset.vendorContact);
        if (source.dataset.vendorPhone) parts.push(source.dataset.vendorPhone);
        if (source.dataset.vendorEmail) parts.push(source.dataset.vendorEmail);
        if (source.dataset.vendorCustomerNumber) parts.push(`Account: ${source.dataset.vendorCustomerNumber}`);
        if (source.dataset.vendorAddress && source.dataset.vendorAddress.trim()) parts.push(source.dataset.vendorAddress.trim());

        const website = source.dataset.vendorWebsite
            ? `<a href="${source.dataset.vendorWebsite}" target="_blank" rel="noopener">Visit Store ↗</a>`
            : "";

        preview.innerHTML = `
            <div>
                <span>Selected Vendor</span>
                <strong>${source.dataset.vendorName || "Vendor"}</strong>
                ${parts.length ? `<p>${parts.join(" · ")}</p>` : ""}
            </div>
            ${website}
        `;
    };

    const syncCharts = () => {
        if (!chart || !vendor) return;
        const selectedVendor = vendor.value;
        Array.from(chart.options).forEach((option) => {
            if (!option.value) { option.hidden = false; return; }
            const text = option.textContent || "";
            const vendorName = vendor.options[vendor.selectedIndex]?.textContent || "";
            option.hidden = Boolean(selectedVendor) && !text.startsWith(vendorName + " —");
        });
        if (chart.selectedOptions[0]?.hidden) chart.value = "";
    };
    if (attach) attach.addEventListener("click", () => { attach.hidden = true; fields.hidden = false; vendor?.focus(); });
    vendor?.addEventListener("change", () => {
        syncCharts();
        renderVendorPreview();
    });
    syncCharts();
    renderVendorPreview();
});
