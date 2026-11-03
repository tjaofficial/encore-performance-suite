document.addEventListener("DOMContentLoaded", () => {
  const checks = [...document.querySelectorAll("[data-select-instructor]")];
  const selectAll = document.querySelector("[data-select-all-instructors]");
  const bar = document.querySelector("[data-instructor-selection-bar]");
  const modal = document.querySelector("[data-instructor-bulk-modal]");
  const count = document.querySelector("[data-instructor-count]");
  const modalCount = document.querySelector("[data-modal-instructor-count]");
  const idsInput = document.querySelector("[data-bulk-instructor-ids]");
  const fieldSelect = document.querySelector("[data-instructor-bulk-field]");
  const valueSlot = document.querySelector("[data-instructor-bulk-value]");
  const selectedIds = () => checks.filter(el => el.checked).map(el => el.value);
  const sync = () => {
    const ids = selectedIds();
    if (bar) bar.hidden = !ids.length;
    if (count) count.textContent = ids.length;
    if (modalCount) modalCount.textContent = ids.length;
    if (idsInput) idsInput.value = JSON.stringify(ids);
    if (selectAll) {selectAll.checked = checks.length > 0 && ids.length === checks.length;selectAll.indeterminate = ids.length > 0 && ids.length < checks.length;}
  };
  checks.forEach(el => el.addEventListener("change", sync));
  if (selectAll) selectAll.addEventListener("change", () => {checks.forEach(el => {el.checked = selectAll.checked;});sync();});
  document.querySelector("[data-clear-instructors]")?.addEventListener("click", () => {checks.forEach(el => {el.checked = false;});sync();});
  const open = enabled => {if (!modal) return;modal.hidden = !enabled;document.body.classList.toggle("instructor-bulk-open",enabled);if (enabled) fieldSelect?.focus();};
  document.querySelector("[data-open-instructor-bulk]")?.addEventListener("click", () => {if (!selectedIds().length)return;sync();open(true);});
  modal?.querySelectorAll("[data-close-instructor-bulk]").forEach(el => el.addEventListener("click", () => open(false)));
  document.addEventListener("keydown", e => {if (e.key === "Escape" && modal && !modal.hidden)open(false);});
  const renderValue = () => {
    if (!valueSlot) return;
    valueSlot.replaceChildren();
    if (fieldSelect?.value === "is_active") {
      const select=document.createElement("select");select.name="value";select.required=true;
      [["","Choose status…"],["true","Active"],["false","Inactive"]].forEach(([v,t])=>{const option=document.createElement("option");option.value=v;option.textContent=t;select.append(option);});valueSlot.append(select);
    } else if (fieldSelect?.value === "phone") {
      const input=document.createElement("input");input.type="tel";input.name="value";input.maxLength=30;input.placeholder="Phone number (leave blank to clear)";valueSlot.append(input);
    }
  };
  fieldSelect?.addEventListener("change",renderValue);
  renderValue();
  modal?.addEventListener("submit",e=>{sync();if (!selectedIds().length){e.preventDefault();return;}const label=fieldSelect.value === "is_active" ? "status" : "phone number";if (!window.confirm(`Apply the new ${label} to ${selectedIds().length} selected instructor(s)?`))e.preventDefault();});
  sync();
});
