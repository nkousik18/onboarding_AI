/**
 * LightHouse — single-button theme toggle.
 *
 * Renders one sliding switch (top-right) that flips between
 * light and dark. Persists choice to localStorage under "theme".
 *
 * To add the toggle to a page: include this script and an empty
 *   <button id="lhThemeToggle"></button>
 * (or let this script auto-create one if none exists).
 */
(function () {
  var STORAGE_KEY = 'theme';
  var html = document.documentElement;

  function applyTheme(theme) {
    html.setAttribute('data-theme', theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (e) {}
    var btn = document.getElementById('lhThemeToggle');
    if (btn) {
      btn.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
      btn.title = theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode';
    }
  }

  function getInitialTheme() {
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (e) {}
    return 'dark';
  }

  // Apply early to avoid a flash, even if button hasn't rendered yet.
  applyTheme(getInitialTheme());

  function buildToggle() {
    var btn = document.getElementById('lhThemeToggle');
    var created = false;
    if (!btn) {
      btn = document.createElement('button');
      btn.id = 'lhThemeToggle';
      created = true;
    }
    btn.type = 'button';
    btn.className = 'lh-theme-toggle';
    btn.setAttribute('aria-label', 'Toggle color theme');
    btn.innerHTML =
      '<span class="lh-theme-toggle__thumb" aria-hidden="true">' +
        // Moon (visible in dark mode)
        '<svg class="icon-moon" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>' +
        // Sun (visible in light mode)
        '<svg class="icon-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="6.34" y2="6.34"/><line x1="17.66" y1="17.66" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="6.34" y2="17.66"/><line x1="17.66" y1="6.34" x2="19.07" y2="4.93"/></svg>' +
      '</span>';

    btn.addEventListener('click', function () {
      var current = html.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
      applyTheme(current === 'light' ? 'dark' : 'light');
    });

    if (created) document.body.appendChild(btn);

    // Re-apply so attributes/title sync now that the button exists.
    applyTheme(getInitialTheme());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildToggle);
  } else {
    buildToggle();
  }
})();
