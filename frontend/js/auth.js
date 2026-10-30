/* Login state for this tab: the Bearer token and the account it belongs to.
 * sessionStorage keeps it across page navigation and forgets it when the tab
 * closes. Trade-off: a script injected into the page could read it, which is
 * why every page escapes the data it renders. Logging out = forgetting the token. */
const Auth = (() => {
  const TOKEN_KEY = "revenue-analytics-token";
  const USER_KEY = "revenue-analytics-user";
  const PAGES = ["index.html", "visualize.html", "forecast.html"];

  function read(key) {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function token() {
    return read(TOKEN_KEY);
  }

  function user() {
    try {
      return JSON.parse(read(USER_KEY));
    } catch {
      return null;
    }
  }

  function isLoggedIn() {
    return Boolean(token());
  }

  function setToken(value) {
    sessionStorage.setItem(TOKEN_KEY, value);
  }

  function setUser(account) {
    sessionStorage.setItem(USER_KEY, JSON.stringify({ username: account.username, role: account.role }));
  }

  function clearSession() {
    try {
      sessionStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(USER_KEY);
    } catch {
      // Nothing stored.
    }
    // The cached dataset belongs to the account that is leaving. (A top-level const
    // such as AppState is not a property of globalThis, so check it with typeof.)
    if (typeof AppState !== "undefined") AppState.clear();
  }

  // Only app pages are accepted as a return address, so a crafted link cannot redirect elsewhere.
  function safeNext(value) {
    return PAGES.includes(value) ? value : "index.html";
  }

  function redirectToLogin(reason) {
    const page = window.location.pathname.split("/").pop() || "index.html";
    const params = new URLSearchParams({ next: safeNext(page) });
    if (reason) params.set("reason", reason);
    window.location.replace(`login.html?${params}`);
  }

  function requireLogin() {
    if (isLoggedIn()) return true;
    redirectToLogin();
    return false;
  }

  // Called when the API answers 401: the token is missing, expired or no longer valid.
  function handleUnauthorized() {
    clearSession();
    redirectToLogin("expired");
  }

  function logout() {
    clearSession();
    window.location.replace("login.html?reason=loggedout");
  }

  return { token, user, isLoggedIn, setToken, setUser, clearSession, safeNext, requireLogin, handleUnauthorized, logout };
})();
