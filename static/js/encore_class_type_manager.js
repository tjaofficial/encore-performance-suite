document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("classTypeBulkForm");
  if (!form) return;
  const checks = Array.from(form.querySelectorAll(".class-type-row-check"));
  const selectAll = document.getElementById("classTypeSelectAll");
  const label = document.getElementById("classTypeSelectionLabel");
  const buttons = Array.from(form.querySelectorAll(".class-type-bulk-actions button"));
  const update = () => {
    const selected = checks.filter(check => check.checked).length;
    label.textContent = selected ? `${selected} class type${selected === 1 ? "" : "s"} selected` : "Select class types for bulk changes";
    buttons.forEach(button => { button.disabled = selected === 0; });
    if (selectAll) {
      selectAll.checked = checks.length > 0 && selected === checks.length;
      selectAll.indeterminate = selected > 0 && selected < checks.length;
    }
  };
  checks.forEach(check => check.addEventListener("change", update));
  if (selectAll) selectAll.addEventListener("change", () => { checks.forEach(check => { check.checked = selectAll.checked; }); update(); });
  form.addEventListener("submit", (event) => {
    const action = event.submitter?.value;
    const selected = checks.filter(check => check.checked).length;
    if (!selected || !["activate", "deactivate"].includes(action)) { event.preventDefault(); return; }
    if (!window.confirm(`${action === "activate" ? "Activate" : "Deactivate"} ${selected} selected class type${selected === 1 ? "" : "s"}?`)) event.preventDefault();
  });
  update();
});
