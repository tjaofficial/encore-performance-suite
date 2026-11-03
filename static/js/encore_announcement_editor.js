document.addEventListener('DOMContentLoaded', () => {
  const wrapper = document.querySelector('[data-ann-editor]');
  if (!wrapper) return;
  const editor = wrapper.querySelector('[contenteditable]');
  const textarea = wrapper.parentElement.querySelector('textarea[name="message"]');
  const form = wrapper.closest('form');
  if (!textarea || !form) return;
  const sync = () => { textarea.value = editor.innerHTML; };
  wrapper.querySelectorAll('[data-command], [data-block]').forEach(button => {
    // Keep the current selection when toolbar buttons are clicked.
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => {
      editor.focus();
      const block = button.dataset.block;
      if (block) document.execCommand('formatBlock', false, block);
      else if (button.dataset.command === 'createLink') {
        const selection = window.getSelection();
        if (!selection || selection.isCollapsed) {
          alert('Select the words you want to link first.');
          return;
        }
        const target = window.prompt('Enter a URL (https://…) or an Encore page path (/…):', 'https://');
        if (!target) return;
        const url = target.trim();
        if (!/^https?:\/\/\S+$/i.test(url) && !/^\/(?!\/)\S*$/.test(url) && !/^mailto:[^\s@]+@[^\s@]+$/i.test(url)) {
          alert('Use an https:// URL, a mailto: address, or a path beginning with /.');
          return;
        }
        document.execCommand('createLink', false, url);
      } else document.execCommand(button.dataset.command, false, null);
      sync();
    });
  });
  editor.addEventListener('input', sync);
  editor.addEventListener('blur', sync);
  form.addEventListener('submit', event => {
    sync();
    if (!editor.textContent.trim()) {
      event.preventDefault();
      editor.focus();
      editor.setAttribute('aria-invalid', 'true');
    }
  });
});
