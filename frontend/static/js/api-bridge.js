/**
 * api-bridge.js
 *
 * Glue between the legacy dashboard scripts (which call relative
 * `/api/...` paths) and the JWT-secured Django API on a different
 * origin. Wraps window.fetch so the existing scripts keep working
 * without rewriting their many call sites.
 *
 *  - Rewrites `/api/...` and same-origin `<page-origin>/api/...`
 *    to API_BASE_URL.
 *  - Adds `Authorization: Bearer <access>` from localStorage if
 *    the request is going to the API and no Authorization header
 *    is already set.
 *  - On 401, attempts a one-shot refresh via api-client.js's
 *    refresh handler if available, otherwise redirects to login.
 *
 * Loaded BEFORE the dashboard scripts.
 */
(function () {
  var API_BASE_URL = 'http://localhost:8000/api';
  var STORAGE_KEY_ACCESS = 'lighthouse_access_token';
  var STORAGE_KEY_REFRESH = 'lighthouse_refresh_token';
  var ORIG_FETCH = window.fetch.bind(window);

  function rewriteUrl(input) {
    // Accept both string and Request inputs
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    if (!url) return input;

    // /api/... — relative path
    if (url.indexOf('/api/') === 0) {
      return API_BASE_URL + url.slice(4); // drop leading "/api" -> append the rest
    }
    // Same-origin absolute path matching window.location.origin + /api/
    try {
      var parsed = new URL(url, window.location.origin);
      if (parsed.origin === window.location.origin && parsed.pathname.indexOf('/api/') === 0) {
        return API_BASE_URL + parsed.pathname.slice(4) + parsed.search;
      }
    } catch (_) {}
    return input;
  }

  function isApiUrl(url) {
    return typeof url === 'string' && url.indexOf(API_BASE_URL) === 0;
  }

  async function attemptRefresh() {
    var refresh = localStorage.getItem(STORAGE_KEY_REFRESH);
    if (!refresh) return false;
    try {
      var res = await ORIG_FETCH(API_BASE_URL + '/auth/refresh/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh: refresh }),
      });
      if (!res.ok) return false;
      var data = await res.json();
      if (data && data.access) {
        localStorage.setItem(STORAGE_KEY_ACCESS, data.access);
        return true;
      }
    } catch (_) {}
    return false;
  }

  window.fetch = async function (input, init) {
    var rewritten = rewriteUrl(input);
    init = init || {};

    if (isApiUrl(typeof rewritten === 'string' ? rewritten : (rewritten.url || ''))) {
      var headers = new Headers(init.headers || (typeof input !== 'string' && input.headers) || {});
      if (!headers.has('Authorization')) {
        var access = localStorage.getItem(STORAGE_KEY_ACCESS);
        if (access) headers.set('Authorization', 'Bearer ' + access);
      }
      if (!headers.has('Content-Type') && init.body && typeof init.body === 'string') {
        headers.set('Content-Type', 'application/json');
      }
      init.headers = headers;
    }

    var res = await ORIG_FETCH(rewritten, init);

    if (res.status === 401 && isApiUrl(typeof rewritten === 'string' ? rewritten : (rewritten.url || ''))) {
      var refreshed = await attemptRefresh();
      if (refreshed) {
        var headers2 = new Headers(init.headers || {});
        headers2.set('Authorization', 'Bearer ' + localStorage.getItem(STORAGE_KEY_ACCESS));
        init.headers = headers2;
        return ORIG_FETCH(rewritten, init);
      }
      // Fall through; caller can decide whether to redirect.
    }
    return res;
  };

  // Convenience: redirect to login on hard 401 if there's no access token
  // (covers the case where a dashboard page is opened without logging in).
  if (!localStorage.getItem(STORAGE_KEY_ACCESS) && /(?:project_dashboard|home|integrations|workspace|detail)\.html$/.test(location.pathname)) {
    // Only redirect when we're clearly trying to use the app shell.
    // Comment this out if you prefer the page to load and surface 401s instead.
    // location.replace('login.html');
  }
})();
