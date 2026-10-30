const UI = (() => {
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
    }[character]));
  }

  function setMessage(target, text = "", type = "success") {
    const element = typeof target === "string" ? document.getElementById(target) : target;
    if (!element) return;
    element.innerHTML = text ? `<div class="message ${type}" role="alert">${escapeHtml(text)}</div>` : "";
  }

  function formatNumber(value) {
    return new Intl.NumberFormat(I18n.language() === "vi" ? "vi-VN" : "en-US", { maximumFractionDigits: 2 }).format(value);
  }

  function renderDatasetIndicator() {
    const indicator = document.getElementById("activeDataset");
    if (!indicator) return;
    const dataset = AppState.activeDataset();
    indicator.textContent = dataset
      ? `${dataset.filename} · ${I18n.t("common.rows", { count: formatNumber(dataset.rows) })}`
      : I18n.t("status.noDataset");
    indicator.classList.toggle("has-dataset", Boolean(dataset));
  }

  async function checkApiStatus() {
    const element = document.getElementById("apiStatus");
    if (!element) return;
    try {
      await Api.health();
      element.textContent = I18n.t("status.connected");
      element.className = "status ok";
    } catch {
      element.textContent = I18n.t("status.offline");
      element.className = "status bad";
    }
  }

  function renderUser() {
    const indicator = document.getElementById("currentUser");
    const account = Auth.user();
    if (!indicator || !account) return;
    const role = account.role === "admin" ? ` · ${I18n.t("auth.admin")}` : "";
    indicator.textContent = `${I18n.t("auth.signedInAs", { name: account.username })}${role}`;
    indicator.title = indicator.textContent; // full text when the header shortens it
    indicator.hidden = false;
  }

  async function refreshUser() {
    try {
      // Also confirms the token is still valid; a 401 sends the user to the login page.
      Auth.setUser(await Api.me());
      renderUser();
    } catch {
      // Offline: keep the stored name; the API status badge already reports the problem.
    }
  }

  /* Returns false (and redirects to the login page) when nobody is logged in. */
  function initialiseShell(activePage) {
    if (!Auth.requireLogin()) return false;
    document.querySelectorAll("[data-page]").forEach((link) => {
      const isActive = link.dataset.page === activePage;
      link.classList.toggle("active", isActive);
      if (isActive) link.setAttribute("aria-current", "page");
    });
    const logout = document.getElementById("logoutButton");
    logout.hidden = false;
    logout.addEventListener("click", Auth.logout);
    renderUser();
    renderDatasetIndicator();
    checkApiStatus();
    refreshUser();
    return true;
  }

  function showDatasetRequired(target, feature) {
    const element = typeof target === "string" ? document.getElementById(target) : target;
    element.innerHTML = `<section class="empty-state"><h2>${escapeHtml(I18n.t("empty.title"))}</h2><p>${escapeHtml(I18n.t("empty.body", { feature }))}</p><a class="button-link" href="index.html">${escapeHtml(I18n.t("empty.goData"))}</a></section>`;
  }

  return { escapeHtml, setMessage, formatNumber, renderDatasetIndicator, checkApiStatus, initialiseShell, showDatasetRequired };
})();
