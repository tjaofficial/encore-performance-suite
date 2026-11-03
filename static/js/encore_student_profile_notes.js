document.addEventListener('DOMContentLoaded', () => {
  const panel = document.querySelector('.student-private-notes');
  if (!panel) return;
  const input = panel.querySelector('[data-note-input]');
  const status = panel.querySelector('[data-note-status]');
  const csrf = document.cookie.split('; ').find(item => item.startsWith('csrftoken='))?.split('=')[1] || '';
  let timer = null, saving = false, dirty = false;
  async function save() {
    if (!dirty || saving) return;
    saving = true;
    dirty = false;
    const text = input.value;
    status.textContent = 'Saving…';
    status.classList.remove('is-error');
    try {
      const response = await fetch(panel.dataset.saveUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type':'application/json', 'X-CSRFToken': decodeURIComponent(csrf)},
        body: JSON.stringify({text, version: input.dataset.version || ''})
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || 'Could not save.');
      input.dataset.version = body.version;
      status.textContent = dirty ? 'Unsaved changes' : 'Saved';
    } catch(error) {
      dirty = true;
      status.textContent = error.message;
      status.classList.add('is-error');
      // A version conflict requires reloading, never automatically overwrite.
      return;
    } finally { saving = false; }
    if (dirty) schedule();
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(save, 850); }
  input.addEventListener('input', () => { dirty = true; status.textContent = 'Unsaved changes'; schedule(); });
  input.addEventListener('blur', () => { clearTimeout(timer); save(); });
});
