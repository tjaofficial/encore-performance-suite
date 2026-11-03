document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("tuition-settings-form");
    if (!form) return;
    const studioWidePanel = document.getElementById("studio-wide-settings");
    const flatPanel = document.getElementById("flat-rate-settings");
    const tieredPanel = document.getElementById("tiered-rate-settings");
    const addTierButton = document.getElementById("add-tuition-tier");
    const tierList = document.getElementById("tuition-tier-list");
    const template = document.getElementById("empty-tier-template");
    const totalForms = document.getElementById("id_tiers-TOTAL_FORMS");
    function checked(name){return form.querySelector(`input[name="${name}"]:checked`)}
    function syncPanels(){const pricing=checked("pricing_mode");const method=checked("studio_wide_method");const wide=pricing&&pricing.value==="studio_wide";studioWidePanel?.classList.toggle("visible",wide);if(flatPanel)flatPanel.style.display=wide&&method?.value==="flat_hourly"?"block":"none";if(tieredPanel)tieredPanel.style.display=wide&&method?.value==="tiered_hourly"?"block":"none"}
    form.querySelectorAll('input[name="pricing_mode"],input[name="studio_wide_method"]').forEach(i=>i.addEventListener("change",syncPanels));
    if(addTierButton&&tierList&&template&&totalForms){addTierButton.addEventListener("click",function(){const index=Number(totalForms.value);const html=template.innerHTML.replaceAll("__prefix__",String(index));const wrapper=document.createElement("div");wrapper.innerHTML=html.trim();const row=wrapper.firstElementChild;const hourInput=row.querySelector('input[name$="-hour_number"]');if(hourInput&&!hourInput.value){const vals=Array.from(tierList.querySelectorAll('input[name$="-hour_number"]')).map(i=>Number(i.value||0)).filter(Boolean);hourInput.value=vals.length?Math.max(...vals)+1:1}tierList.appendChild(row);totalForms.value=index+1})}

    const validationBanner = document.getElementById("tuition-validation-banner");
    if (validationBanner) {
        const firstError =
            form.querySelector(".field-error") ||
            form.querySelector(".form-errors") ||
            validationBanner;

        window.setTimeout(function () {
            firstError.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });

            const fieldGroup = firstError.closest(".field-group, .tuition-subsection, .billing-card");
            const focusTarget = fieldGroup
                ? fieldGroup.querySelector("select, input:not([type='hidden']), textarea")
                : null;

            if (focusTarget) {
                focusTarget.focus({ preventScroll: true });
            }
        }, 100);
    }

    syncPanels();
});
