(() => {
  const root = document.getElementById('ep-activation');
  if (!root) return;
  const container = document.getElementById('ep-stripe-onboarding');
  const loading = document.getElementById('ep-loading');
  const error = document.getElementById('ep-onboarding-error');
  const result = document.getElementById('ep-status-result');
  let connect = null;
  let started = false;
  const csrf = document.querySelector('#ep-token-form input[name=csrfmiddlewaretoken]')?.value || '';
  const showError = message => {
    if (error) { error.textContent = message; error.hidden = false; }
    if (loading) loading.hidden = true;
  };
  const text = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  };
  async function fetchClientSecret() {
    const response = await fetch(root.dataset.sessionUrl, {method: 'POST', credentials: 'same-origin',
      headers: {'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest'}});
    const data = await response.json();
    if (!response.ok || !data.client_secret) throw new Error(data.error || 'Could not open Stripe verification.');
    return data.client_secret;
  }
  function renderStatus(data) {
    const state = data.state || 'error';
    result.dataset.state = state;
    text('ep-status-message', data.message || 'Status unavailable.');
    text('ep-card-status', data.card_status || 'pending');
    text('ep-status-pill', data.state_label || 'Status unavailable');
    document.getElementById('ep-status-pill')?.classList.toggle('ep-ready', state === 'active');
    text('ep-result-state', data.state_label || 'Status unavailable');
    text('ep-result-description', data.message || '');
    const titles = {active: 'Your studio is ready to accept payments!', review: 'Information submitted — waiting for Stripe',
      action_required: 'One more step: Stripe needs information', not_started: 'Start your payment setup', error: 'We could not confirm your payment status'};
    const next = {
      active: 'Online card payments are now active. An activation notification and email will be sent to studio administrators. You can return to Billing. Parent payment and AutoPay testing comes next.',
      review: 'Stripe has not enabled card payments yet. Encore has no immediate action to show. We will check for updates and notify you when payments are active. You can also check status again.',
      action_required: 'Stripe needs additional information. Resume the secure verification form below, submit the missing information, then check your status.',
      not_started: 'Start secure verification below to activate online payments for your studio.',
      error: 'The current status could not be verified. Please try again.'
    };
    text('ep-result-title', titles[state] || titles.error);
    text('ep-result-next', next[state] || next.error);
    const steps = document.getElementById('ep-steps');
    if (steps) steps.hidden = state === 'active' || state === 'review';
    text('ep-form-heading', state === 'active' ? 'Manage your payment account' : state === 'review' ? 'Verification submitted' : 'Complete your payment account');
    if (container && !started) container.hidden = state === 'active' || state === 'review';
  }
  async function refreshStatus() {
    try {
      const response = await fetch(root.dataset.statusUrl, {credentials: 'same-origin', cache: 'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Status unavailable.');
      renderStatus(data);
      return data;
    } catch(e) { text('ep-status-message', e.message); return null; }
  }
  async function start() {
    if (!container) return;
    error.hidden = true;
    loading.hidden = false;
    container.hidden = false;
    container.replaceChildren();
    try {
      if (typeof window.StripeConnect?.init !== 'function')
        throw new Error('Stripe Connect.js has not loaded. Check if your browser blocks connect-js.stripe.com.');
      connect = window.StripeConnect.init({publishableKey: root.dataset.publishableKey, fetchClientSecret});
      const onboarding = connect.create('account-onboarding');
      onboarding.setCollectionOptions({fields: 'eventually_due', futureRequirements: 'include'});
      onboarding.setOnExit(() => { refreshStatus(); });
      container.appendChild(onboarding);
      started = true;
      loading.hidden = true;
    } catch(e) { showError(e.message); }
  }
  document.getElementById('ep-refresh')?.addEventListener('click', refreshStatus);
  document.getElementById('ep-refresh-top')?.addEventListener('click', refreshStatus);
  document.getElementById('ep-retry')?.addEventListener('click', start);
  document.getElementById('ep-manage')?.addEventListener('click', async () => {
    if (!connect) await start();
    if (!connect) return;
    const management = document.getElementById('ep-stripe-management');
    if (management.hidden) {
      management.hidden = false;
      management.appendChild(connect.create('account-management'));
      container.hidden = true;
    } else {
      management.hidden = true;
      management.replaceChildren();
      container.hidden = false;
    }
  });
  const initial = result?.dataset.state;
  // Once information is submitted, preserve the status view until the owner chooses to resume.
  if (container && initial !== 'active' && initial !== 'review') {
    if (typeof window.StripeConnect?.init === 'function') start();
    else {
      window.StripeConnect = window.StripeConnect || {};
      window.StripeConnect.onLoad = start;
    }
  }
  // Checking never confirms payments on its own; the authenticated Django endpoint does.
  refreshStatus();
  // Stripe can enable card payments moments after onboarding finishes.
  // Refresh while this page is visible; no repeated notifications are created server-side.
  window.setInterval(() => { if (!document.hidden) refreshStatus(); }, 20000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshStatus(); });
})();
