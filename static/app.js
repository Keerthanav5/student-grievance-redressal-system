/* Global micro-interactions: page fade transitions + small UI helpers */
(function () {
  var root = document.documentElement;

  function onReady() {
    // Trigger entry animation
    root.classList.add('is-ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }

  // Fade-out on internal navigation (skips if already prevented, new tab, downloads, external, or explicitly opted out)
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!a) return;

    if (e.defaultPrevented) return;
    if (a.hasAttribute('download')) return;
    if (a.getAttribute('target') && a.getAttribute('target') !== '_self') return;
    if (a.dataset && a.dataset.noTransition === 'true') return;

    var href = a.getAttribute('href') || '';
    if (!href || href[0] === '#') return;

    // Only same-origin navigations
    try {
      var url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return;

      // Let the browser handle modified clicks (new tab/window)
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

      e.preventDefault();
      root.classList.add('is-leaving');

      window.setTimeout(function () {
        window.location.href = url.href;
      }, 170);
    } catch (_) {
      // If URL parsing fails, do nothing.
    }
  });

  // Fade-out on form submit
  document.addEventListener('submit', function () {
    root.classList.add('is-leaving');
  });

  // Password show/hide toggles
  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-toggle-password]') : null;
    if (!btn) return;

    var targetSelector = btn.getAttribute('data-target') || '';
    if (!targetSelector) return;

    var input = document.querySelector(targetSelector);
    if (!input) return;

    var isPassword = (input.getAttribute('type') || '').toLowerCase() !== 'text';
    input.setAttribute('type', isPassword ? 'text' : 'password');

    btn.classList.toggle('is-on', isPassword);
    btn.setAttribute('aria-pressed', isPassword ? 'true' : 'false');
    btn.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');

    // Keep cursor in the input
    input.focus({ preventScroll: true });
  });

  document.addEventListener('mousedown', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-toggle-password]') : null;
    if (!btn) return;
    // Prevent input blur on click
    e.preventDefault();
  });
})();
