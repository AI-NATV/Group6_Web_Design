/* Header tools shared by every page.
 * - Theme (auto, light, dark): a per-browser preference, kept in localStorage.
 * - Account dialog (signed-in pages only): optional display name and phone,
 *   profile picture, About, log out, and account deletion with two confirmations.
 * Every value from the server is escaped before it is placed in the page. */
const Account = (() => {
  const THEME_KEY = "revenue-analytics-theme";
  const AVATAR_TYPES = ["image/png", "image/jpeg", "image/webp"];
  // The server accepts at most 200,000 characters of data URL; 140 KB of image stays under that after base64.
  const MAX_AVATAR_BYTES = 140 * 1024;
  const API_VERSION = "0.6.0";
  const t = (key, variables) => I18n.t(key, variables);
  const el = (id) => document.getElementById(id);
  const escape = (value) => UI.escapeHtml(value);

  // ---------- theme ----------
  function storedTheme() {
    try {
      return localStorage.getItem(THEME_KEY) || "system";
    } catch {
      return "system";
    }
  }

  function applyTheme(choice) {
    const root = document.documentElement;
    if (choice === "light" || choice === "dark") root.dataset.theme = choice;
    else delete root.dataset.theme;
  }

  function nextTheme(choice) {
    return { system: "light", light: "dark", dark: "system" }[choice] || "system";
  }

  function renderThemeButton(button, choice) {
    button.textContent = t(`theme.${choice}`);
    button.dataset.theme = choice;
  }

  function mountThemeButton(status) {
    const button = document.createElement("button");
    button.id = "themeButton";
    button.type = "button";
    button.className = "button-secondary header-button";
    renderThemeButton(button, storedTheme());
    button.addEventListener("click", () => {
      const choice = nextTheme(button.dataset.theme);
      try {
        localStorage.setItem(THEME_KEY, choice);
      } catch {
        // Storage may be blocked; the theme still changes for this page view.
      }
      applyTheme(choice);
      renderThemeButton(button, choice);
    });
    status.prepend(button);
  }

  // ---------- account dialog ----------
  function initials(account) {
    const source = (account.display_name || account.username || "?").trim();
    return escape(source.charAt(0).toUpperCase());
  }

  function avatarMarkup(account) {
    return account.avatar
      ? `<img class="account-avatar" src="${escape(account.avatar)}" alt="">`
      : `<span class="account-avatar account-avatar-fallback" aria-hidden="true">${initials(account)}</span>`;
  }

  function dialogMarkup(account) {
    const role = account.role === "admin" ? `<p class="muted small">${escape(t("account.role"))}: ${escape(t("auth.admin"))}</p>` : "";
    return `
      <div class="account-dialog-head">
        <h2 id="accountTitle">${escape(t("account.title"))}</h2>
        <button id="accountClose" class="button-secondary" type="button">${escape(t("account.close"))}</button>
      </div>
      <div id="accountMessage" aria-live="polite"></div>

      <section class="account-section">
        <div class="account-profile-top">
          <div id="accountAvatarSlot">${avatarMarkup(account)}</div>
          <div>
            <label class="account-file">
              <span>${escape(t("account.avatar"))}</span>
              <input id="accountAvatarInput" type="file" accept="image/png,image/jpeg,image/webp">
            </label>
            <p class="muted small">${escape(t("account.avatarHint"))}</p>
          </div>
        </div>
        ${role}
        <form id="accountProfileForm" class="auth-form" novalidate>
          <label for="accountUsername">${escape(t("account.username"))}</label>
          <input id="accountUsername" type="text" value="${escape(account.username)}" readonly>
          <label for="accountDisplayName">${escape(t("account.displayName"))}</label>
          <input id="accountDisplayName" name="display_name" type="text" maxlength="60" value="${escape(account.display_name || "")}" placeholder="${escape(account.username)}">
          <p class="muted small">${escape(t("account.displayHint"))}</p>
          <label for="accountPhone">${escape(t("account.phone"))}</label>
          <input id="accountPhone" name="phone" type="tel" maxlength="20" autocomplete="tel" value="${escape(account.phone || "")}">
          <button id="accountSave" type="submit">${escape(t("account.save"))}</button>
        </form>
      </section>

      <section class="account-section" aria-labelledby="accountAboutHeading">
        <h3 id="accountAboutHeading">${escape(t("account.about"))}</h3>
        <p>${escape(t("account.aboutText"))}</p>
        <p class="muted small">${escape(t("account.versions"))}: API ${escape(API_VERSION)} · FastAPI 0.162.0 · SQLModel 0.0.48 · pandas 3.0.5 · scikit-learn 1.8.0 · Chart.js 4.5.1</p>
      </section>

      <section class="account-section">
        <button id="accountLogout" class="button-secondary" type="button">${escape(t("auth.logout"))}</button>
      </section>

      <section class="account-section account-danger" aria-labelledby="accountDeleteHeading">
        <h3 id="accountDeleteHeading">${escape(t("account.deleteTitle"))}</h3>
        <p class="muted small">${escape(t("account.deleteText"))}</p>
        <label for="accountDeletePassword">${escape(t("account.password"))}</label>
        <input id="accountDeletePassword" type="password" autocomplete="current-password">
        <button id="accountDeleteStart" class="button-danger" type="button" disabled>${escape(t("account.deleteButton"))}</button>
        <div id="accountDeleteConfirm" class="account-confirm" hidden>
          <p><strong>${escape(t("account.deleteConfirm"))}</strong></p>
          <button id="accountDeleteCancel" class="button-secondary" type="button">${escape(t("account.cancel"))}</button>
          <button id="accountDeleteFinal" class="button-danger" type="button">${escape(t("account.deleteFinal"))}</button>
        </div>
      </section>`;
  }

  function readAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  function refreshHeaderUser() {
    UI.renderUser();
  }

  function openDialog(dialog) {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function mountAccount(status, account) {
    const button = document.createElement("button");
    button.id = "accountButton";
    button.type = "button";
    button.className = "button-secondary header-button";
    button.textContent = t("account.open");

    const dialog = document.createElement("dialog");
    dialog.id = "accountDialog";
    dialog.className = "account-dialog";
    dialog.setAttribute("aria-labelledby", "accountTitle");
    dialog.innerHTML = dialogMarkup(account);

    status.prepend(button);
    document.body.appendChild(dialog);
    bindAccountEvents(button, dialog);
  }

  function bindAccountEvents(button, dialog) {
    button.addEventListener("click", () => openDialog(dialog));
    dialog.addEventListener("click", (event) => {
      // Clicking the backdrop (outside the content box) closes the dialog.
      if (event.target === dialog) closeDialog(dialog);
    });
    dialog.querySelector("#accountClose").addEventListener("click", () => closeDialog(dialog));
    dialog.querySelector("#accountLogout").addEventListener("click", () => Auth.logout());
    dialog.querySelector("#accountProfileForm").addEventListener("submit", (event) => saveProfile(event));
    dialog.querySelector("#accountAvatarInput").addEventListener("change", (event) => saveAvatar(event));

    const password = dialog.querySelector("#accountDeletePassword");
    const start = dialog.querySelector("#accountDeleteStart");
    const confirmBox = dialog.querySelector("#accountDeleteConfirm");
    password.addEventListener("input", () => {
      start.disabled = password.value.length === 0;
      confirmBox.hidden = true;
    });
    start.addEventListener("click", () => { confirmBox.hidden = false; });
    dialog.querySelector("#accountDeleteCancel").addEventListener("click", () => { confirmBox.hidden = true; });
    dialog.querySelector("#accountDeleteFinal").addEventListener("click", () => deleteAccount(dialog));
  }

  function setAccountMessage(dialog, text, type) {
    UI.setMessage(dialog.querySelector("#accountMessage"), text, type);
  }

  async function saveProfile(event) {
    event.preventDefault();
    const dialog = el("accountDialog");
    const name = dialog.querySelector("#accountDisplayName").value.trim();
    const phone = dialog.querySelector("#accountPhone").value.trim();
    try {
      const saved = await Api.updateProfile({ display_name: name || null, phone: phone || null });
      Auth.setUser(saved);
      refreshHeaderUser();
      setAccountMessage(dialog, t("account.saved"), "success");
    } catch (error) {
      setAccountMessage(dialog, error.message, "error");
    }
  }

  async function saveAvatar(event) {
    const dialog = el("accountDialog");
    const file = event.target.files?.[0];
    if (!file) return;
    if (!AVATAR_TYPES.includes(file.type)) {
      setAccountMessage(dialog, t("account.avatarType"), "error");
      event.target.value = "";
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      setAccountMessage(dialog, t("account.avatarSize"), "error");
      event.target.value = "";
      return;
    }
    try {
      const saved = await Api.setAvatar(await readAsDataUrl(file));
      Auth.setUser(saved);
      dialog.querySelector("#accountAvatarSlot").innerHTML = avatarMarkup(saved);
      refreshHeaderUser();
      setAccountMessage(dialog, t("account.avatarSaved"), "success");
    } catch (error) {
      setAccountMessage(dialog, error.message, "error");
    } finally {
      event.target.value = "";
    }
  }

  async function deleteAccount(dialog) {
    const password = dialog.querySelector("#accountDeletePassword").value;
    try {
      await Api.deleteAccount(password);
    } catch (error) {
      setAccountMessage(dialog, error.message, "error");
      return;
    }
    // The server removed the account and its datasets; forget this tab's copy too.
    Auth.clearSession();
    window.location.replace("login.html?reason=deleted");
  }

  // ---------- mount ----------
  function mount() {
    applyTheme(storedTheme());
    const status = document.querySelector(".header-status");
    if (!status) return;
    mountThemeButton(status);
    const account = Auth.user();
    if (Auth.isLoggedIn() && account && account.username) mountAccount(status, account);
  }

  window.addEventListener("DOMContentLoaded", mount);
  return { applyTheme, nextTheme };
})();
