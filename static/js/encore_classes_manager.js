document.addEventListener("DOMContentLoaded", () => {
    const dropInToggle = document.getElementById("id_allow_drop_ins");
    const dropInPrice = document.getElementById("id_drop_in_price");

    if (!dropInToggle || !dropInPrice) {
        return;
    }

    const syncDropInPrice = () => {
        dropInPrice.disabled = !dropInToggle.checked;

        if (!dropInToggle.checked) {
            dropInPrice.value = "";
        }
    };

    dropInToggle.addEventListener("change", syncDropInPrice);
    syncDropInPrice();
});
