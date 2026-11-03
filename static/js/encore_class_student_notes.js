document.addEventListener('DOMContentLoaded', () => {
  const wrapper = document.querySelector('.class-student-notes');
  if (!wrapper) return;
  const csrf = document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || '';
  wrapper.querySelectorAll('textarea[data-note]').forEach(input => {
    const status = wrapper.querySelector(`[data-status="${input.dataset.note}"]`);
    let timer, busy = false, changed = false;
    async function save() {
      if (busy || !changed) return;
      busy = true; changed = false; status.textContent = 'Saving…'; status.classList.remove('error');
      try {
        const res = await fetch(wrapper.dataset.saveUrl, {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRFToken': decodeURIComponent(csrf)}, body:JSON.stringify({scope:input.dataset.note, text:input.value, version:input.dataset.version || ''})});
        const body = await res.json();
        if(!res.ok) throw Error(body.error || 'Could not save');
        input.dataset.version = body.version; status.textContent = 'Saved';
      } catch(err) { status.textContent = err.message; status.classList.add('error'); changed = true; }
      finally { busy = false; if(changed && !status.classList.contains('error')) schedule(); }
    }
    function schedule(){clearTimeout(timer);timer=setTimeout(save,850)}
    input.addEventListener('input',()=>{changed=true;status.textContent='Unsaved';schedule()});
    input.addEventListener('blur',()=>{clearTimeout(timer);save()});
  });
});
