/* Preserve original source of the Dances list across visits to individual dances. */
(function () {
  'use strict';
  const link = document.querySelector('.edl-back[data-smart-back]');
  if (!link) return;
  const key = 'encore:dances:source:' + location.pathname;
  const current = new URL(location.href);
  const studioPrefix = current.pathname.match(/^\/studios\/[^/]+\//)?.[0];
  if (!studioPrefix) return;
  function valid(raw) {
    if (!raw) return null;
    try {
      const u = new URL(raw, location.origin);
      if (u.origin !== location.origin || !u.pathname.startsWith(studioPrefix)) return null;
      if (u.pathname === current.pathname) return null;
      return u.pathname + u.search + u.hash;
    } catch (_) { return null; }
  }
  // The explicit next/return context takes precedence over referrer.
  const params = current.searchParams;
  const explicit = valid(params.get('next') || params.get('return'));
  const ref = valid(document.referrer);
  const fromDance = ref && /\/performance\/|\/dances\//.test(new URL(ref, location.origin).pathname)
                    && !/\/classes\//.test(new URL(ref, location.origin).pathname);
  if (explicit) {
    try { sessionStorage.setItem(key, explicit); } catch (_) {}
    link.href = explicit;
  } else if (ref && !fromDance) {
    try { sessionStorage.setItem(key, ref); } catch (_) {}
    link.href = ref;
  } else {
    let stored = null;
    try { stored = valid(sessionStorage.getItem(key)); } catch (_) {}
    if (stored) link.href = stored;
    else if (ref) link.href = ref;
  }
})();
