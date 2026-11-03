(function () {
    const body = document.body;

    function openModal(id) {
        const modal = document.getElementById(id);
        if (!modal) return;
        modal.hidden = false;
        body.classList.add("parent-modal-open");
    }

    function closeModal(modal) {
        if (!modal) return;
        modal.hidden = true;
        if (!document.querySelector("[data-parent-modal]:not([hidden])")) {
            body.classList.remove("parent-modal-open");
        }
    }

    document.addEventListener("click", function (event) {
        const opener = event.target.closest("[data-parent-modal-open]");
        if (opener) {
            event.preventDefault();
            openModal(opener.dataset.parentModalOpen);
            return;
        }

        const closer = event.target.closest("[data-parent-modal-close]");
        if (closer) {
            event.preventDefault();
            closeModal(closer.closest("[data-parent-modal]"));
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        document.querySelectorAll("[data-parent-modal]:not([hidden])").forEach(closeModal);
    });

    const config = document.getElementById("parent-billing-config");
    const paymentModal = document.getElementById("family-payment-modal");

    if (!config || !paymentModal || typeof window.Stripe !== "function") {
        return;
    }

    let stripe = null;
    let elements = null;
    let paymentElement = null;
    let initialized = false;
    let loading = false;

    const submitButton = document.getElementById("parent-payment-submit");
    const paymentContainer = document.getElementById("parent-payment-element");
    const errorBox = document.getElementById("parent-payment-error");

    function csrftoken() {
        const input = document.querySelector("#parent-billing-csrf input[name='csrfmiddlewaretoken']");
        if (input?.value) return input.value;
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function showError(message) {
        if (!errorBox) return;
        errorBox.textContent = message || "Something went wrong while starting the payment.";
        errorBox.hidden = false;
    }

    async function initializePayment() {
        if (initialized || loading) return;
        loading = true;

        try {
            const response = await fetch(config.dataset.intentUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrftoken(),
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/json",
                },
                credentials: "same-origin",
                body: JSON.stringify({}),
            });

            const payload = await response.json();
            if (!response.ok || !payload.client_secret) {
                throw new Error(payload.error || "Unable to start the payment.");
            }

            stripe = window.Stripe(config.dataset.publishableKey, {
                stripeAccount: config.dataset.connectedAccount,
            });

            elements = stripe.elements({
                clientSecret: payload.client_secret,
                appearance: {
                    theme: "stripe",
                    variables: {
                        borderRadius: "10px",
                    },
                },
            });

            paymentElement = elements.create("payment", {
                layout: "tabs",
            });

            paymentContainer.innerHTML = "";
            paymentElement.mount(paymentContainer);
            initialized = true;
            submitButton.disabled = false;
        } catch (error) {
            paymentContainer.innerHTML = "";
            showError(error.message);
        } finally {
            loading = false;
        }
    }

    document.addEventListener("click", function (event) {
        const opener = event.target.closest('[data-parent-modal-open="family-payment-modal"]');
        if (opener) {
            initializePayment();
        }
    });

    submitButton?.addEventListener("click", async function () {
        if (!stripe || !elements || !initialized) return;

        submitButton.disabled = true;
        submitButton.textContent = "Processing…";
        errorBox.hidden = true;

        try {
            const result = await stripe.confirmPayment({
                elements,
                confirmParams: {
                    return_url: new URL(config.dataset.returnUrl, window.location.origin).toString(),
                },
                redirect: "if_required",
            });

            if (result.error) {
                throw new Error(result.error.message || "The payment could not be completed.");
            }

            if (result.paymentIntent) {
                const returnUrl = new URL(config.dataset.returnUrl, window.location.origin);
                returnUrl.searchParams.set("payment_intent", result.paymentIntent.id);
                window.location.assign(returnUrl.toString());
                return;
            }

            window.location.assign(config.dataset.returnUrl);
        } catch (error) {
            showError(error.message);
            submitButton.disabled = false;
            submitButton.textContent = `Pay $${config.dataset.amount}`;
        }
    });
})();


(function () {
  const btn = document.getElementById('autopay-enable');
  if (!btn) return;
  const consent = document.getElementById('autopay-consent');
  const container = document.getElementById('autopay-payment-form');
  const errorBox = document.getElementById('autopay-error');
  const choices = Array.from(document.querySelectorAll('[data-autopay-method]'));
  const hint = document.getElementById('autopay-method-hint');
  const csrf = () => document.querySelector('#autopay-csrf input[name=csrfmiddlewaretoken]')?.value ||
    decodeURIComponent((document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [, ''])[1]);
  const showError = message => { errorBox.hidden = false; errorBox.textContent = message; };
  const clearError = () => { errorBox.hidden = true; errorBox.textContent = ''; };
  let stripe, elements, paymentElement, setupId, selected = '', ready = false, busy = false;

  function selectChoice(method) {
    selected = method;
    choices.forEach(choice => {
      const active = choice.dataset.autopayMethod === method;
      choice.classList.toggle('is-selected', active);
      choice.setAttribute('aria-pressed', String(active));
    });
    if (hint) hint.textContent = method === 'card'
      ? 'Card preferred. Use the card tab in Stripe’s secure form below if Stripe remembers another method.'
      : 'Bank preferred. Select a bank account in Stripe’s secure form below if it remembers another method.';
  }

  function mountPaymentElement() {
    if (paymentElement) { paymentElement.destroy(); paymentElement = null; }
    // The server now creates a method-specific SetupIntent. Stripe determines
    // the eligible UI from that intent; we do not pretend ordering is enforcement.
    paymentElement = elements.create('payment', {layout: 'tabs'});
    container.hidden = false;
    paymentElement.mount(container);
  }

  async function chooseMethod(method) {
    if (busy) return;
    if (!['card', 'us_bank_account'].includes(method)) return;
    clearError();
    selectChoice(method);
    if (typeof window.Stripe !== 'function') return showError('Stripe did not load. Refresh and try again.');
    busy = true;
    ready = false;
    choices.forEach(c => { c.disabled = true; });
    btn.disabled = true;
    if (hint) hint.textContent = 'Loading the secure ' + (method === 'card' ? 'card' : 'bank account') + ' form…';
    try {
      // A fresh SetupIntent is required when changing methods. Changing a
      // visual preference on an existing intent cannot turn Link into ACH.
      if (paymentElement) { paymentElement.destroy(); paymentElement = null; }
      container.innerHTML = '';
      if (elements) { elements = null; }
      const response = await fetch(btn.dataset.setupUrl, {
        method:'POST', credentials:'same-origin',
        headers:{'X-CSRFToken':csrf(),'Content-Type':'application/json'},
        body:JSON.stringify({autopay_consent:true,method_type:method,collect_current_balance:!!document.getElementById("autopay-balance-consent")?.checked})
      });
      const data = await response.json();
      if (!response.ok || !data.client_secret) throw new Error(data.error || 'Unable to start AutoPay setup.');
      setupId = data.setup_intent_id;
      if (!stripe) stripe = window.Stripe(btn.dataset.publishable, {stripeAccount:btn.dataset.account});
      elements = stripe.elements({clientSecret:data.client_secret});
      mountPaymentElement();
      ready = true;
      btn.textContent = 'Save Payment Method & Enable AutoPay';
      selectChoice(method);
    } catch (e) {
      showError(e.message || 'AutoPay setup failed.');
      if (hint) hint.textContent = 'Could not open the payment form. Select a method to try again.';
    } finally {
      busy = false;
      choices.forEach(c => { c.disabled = false; });
      btn.disabled = false;
    }
  }

  choices.forEach(c => c.addEventListener('click', () => chooseMethod(c.dataset.autopayMethod)));

  const params = new URLSearchParams(window.location.search);
  const returnedId = params.get('setup_intent');
  if (returnedId && /^seti_[A-Za-z0-9]+$/.test(returnedId)) {
    btn.disabled = true;
    btn.textContent = 'Verifying payment method…';
    fetch(btn.dataset.confirmUrl, {method:'POST',credentials:'same-origin',
      headers:{'X-CSRFToken':csrf(),'Content-Type':'application/json'},
      body:JSON.stringify({setup_intent_id:returnedId,collect_current_balance:!!document.getElementById("autopay-balance-consent")?.checked})})
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Bank setup is not complete.');
        const clean = new URL(window.location.href);
        ['setup_intent','setup_intent_client_secret','redirect_status'].forEach(k=>clean.searchParams.delete(k));
        window.location.replace(clean.toString());
      })
      .catch(e => { showError(e.message); btn.disabled = false; btn.textContent = 'Set Up AutoPay'; });
  }

  btn.addEventListener('click', async () => {
    clearError();
    if (!ready) {
      if (!selected) return showError('First choose Bank account (ACH) or Credit/debit card above.');
      return chooseMethod(selected);
    }
    if (!consent.checked) return showError('Please agree to the recurring payment authorization first.');
    if (busy) return;
    busy = true;
    btn.disabled = true;
    try {
      const result = await stripe.confirmSetup({
        elements,
        confirmParams:{return_url:window.location.href},
        redirect:'if_required'
      });
      if (result.error) throw new Error(result.error.message || 'Payment method setup failed.');
      if (!result.setupIntent || result.setupIntent.status !== 'succeeded') {
        throw new Error('Verification is pending. Complete Stripe verification before enabling AutoPay.');
      }
      const response = await fetch(btn.dataset.confirmUrl, {method:'POST',credentials:'same-origin',
        headers:{'X-CSRFToken':csrf(),'Content-Type':'application/json'},
        body:JSON.stringify({setup_intent_id:result.setupIntent.id || setupId,collect_current_balance:!!document.getElementById("autopay-balance-consent")?.checked})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'AutoPay activation failed.');
      window.location.reload();
    } catch (e) {
      showError(e.message || 'AutoPay setup failed.');
      btn.disabled = false;
      busy = false;
    }
  });
})();
