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
    // Greet with the optional display name; without one, the email address is used.
    indicator.textContent = `${I18n.t("auth.signedInAs", { name: account.display_name || account.email })}${role}`;
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

  function isRequiredValueMissing(control) {
    if (control.type === "file") return control.files.length === 0;
    if (control.type === "checkbox" || control.type === "radio") return !control.checked;
    return control.value.trim() === "";
  }

  function setRequiredError(control, missing) {
    const error = document.getElementById(control.dataset.requiredErrorId);
    if (!error) return;
    error.hidden = !missing;
    error.textContent = missing ? I18n.t("validation.required") : "";
    if (missing) {
      control.setAttribute("aria-invalid", "true");
    } else {
      control.removeAttribute("aria-invalid");
    }
  }

  function initializeRequiredFields(root = document) {
    root.querySelectorAll("form").forEach((form) => {
      if (form.dataset.requiredValidationInitialized) return;
      form.dataset.requiredValidationInitialized = "true";
      form.dataset.nativeValidation = String(!form.noValidate);
      form.noValidate = true;

      const requiredControls = Array.from(form.querySelectorAll("input[required], select[required], textarea[required]"));
      requiredControls.forEach((control, index) => {
        const label = control.labels?.[0] || control.closest("label");
        if (label && !label.querySelector(".required-indicator")) {
          const labelText = label.querySelector(":scope > span") || label;
          const indicator = document.createElement("span");
          indicator.className = "required-indicator";
          indicator.setAttribute("aria-hidden", "true");
          indicator.textContent = "*";
          labelText.append(indicator);
        }

        const error = document.createElement("span");
        error.className = "field-error";
        error.id = `${control.id || `required-field-${index}`}-required-error`;
        error.hidden = true;
        error.setAttribute("role", "alert");
        control.dataset.requiredErrorId = error.id;
        if (control.type === "file" && label?.classList.contains("file-picker")) {
          label.after(error);
        } else {
          control.after(error);
        }
        const descriptions = (control.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
        if (!descriptions.includes(error.id)) descriptions.push(error.id);
        control.setAttribute("aria-describedby", descriptions.join(" "));

        ["input", "change"].forEach((eventName) => {
          control.addEventListener(eventName, () => {
            if (!isRequiredValueMissing(control)) setRequiredError(control, false);
          });
        });
      });

      form.addEventListener("submit", (event) => {
        const missing = requiredControls.filter(isRequiredValueMissing);
        requiredControls.forEach((control) => setRequiredError(control, missing.includes(control)));
        if (missing.length) {
          event.preventDefault();
          event.stopImmediatePropagation();
          missing[0].focus();
          return;
        }

        if (form.dataset.nativeValidation === "true") {
          const invalidControl = Array.from(form.elements).find((control) => control.willValidate && !control.validity.valid);
          if (invalidControl) {
            event.preventDefault();
            event.stopImmediatePropagation();
            invalidControl.reportValidity();
          }
        }
      }, true);

      form.addEventListener("reset", () => {
        window.setTimeout(() => requiredControls.forEach((control) => setRequiredError(control, false)));
      });
    });
  }

  window.addEventListener("DOMContentLoaded", () => initializeRequiredFields());

  return { escapeHtml, setMessage, formatNumber, renderDatasetIndicator, renderUser, checkApiStatus, initialiseShell, showDatasetRequired, initializeRequiredFields };
})();
