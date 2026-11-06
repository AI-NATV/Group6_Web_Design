const LoginPage = (() => {
  const t = (key, variables) => I18n.t(key, variables);
  const el = (id) => document.getElementById(id);
  const params = new URLSearchParams(window.location.search);
  const next = Auth.safeNext(params.get("next"));

  // Mirrors the server rule; the server still validates every request.
  function emailError(email) {
    if (email.length > 254) return t("auth.emailTooLong");
    if (!/^[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,}$/i.test(email)) return t("auth.emailInvalid");
    return "";
  }

  function passwordError(password) {
    if (password.length < 8) return t("auth.passwordShort");
    // bcrypt only uses the first 72 bytes; accented letters take more than one byte.
    if (new TextEncoder().encode(password).length > 72) return t("auth.passwordLong");
    return "";
  }

  async function signIn(email, password) {
    const { access_token: token } = await Api.login(email, password);
    Auth.clearSession(); // drop anything cached for a previous account
    Auth.setToken(token);
    Auth.setUser(await Api.me());
    window.location.replace(next);
  }

  async function submit(form, button, busyKey, idleKey, task) {
    form.querySelectorAll("input, button").forEach((control) => { control.disabled = true; });
    button.textContent = t(busyKey);
    try {
      await task();
    } catch (error) {
      UI.setMessage("authMessage", error.message, "error");
      form.querySelectorAll("input, button").forEach((control) => { control.disabled = false; });
      button.textContent = t(idleKey);
    }
  }

  function onLogin(event) {
    event.preventDefault();
    const email = el("loginEmail").value.trim();
    const password = el("loginPassword").value;
    if (!email || !password) {
      UI.setMessage("authMessage", t("auth.required"), "error");
      return;
    }
    submit(event.target, el("loginButton"), "auth.signingIn", "auth.signIn", () => signIn(email, password));
  }

  function onRegister(event) {
    event.preventDefault();
    const email = el("registerEmail").value.trim();
    const password = el("registerPassword").value;
    const error = emailError(email) || passwordError(password)
      || (password !== el("registerConfirm").value ? t("auth.mismatch") : "");
    if (error) {
      UI.setMessage("authMessage", error, "error");
      return;
    }
    submit(event.target, el("registerButton"), "auth.creating", "auth.registerButton", async () => {
      await Api.register(email, password);
      await signIn(email, password);
    });
  }

  function initialise() {
    if (Auth.isLoggedIn()) {
      window.location.replace(next);
      return;
    }
    if (params.get("reason") === "expired") UI.setMessage("authMessage", t("auth.expired"), "warning");
    if (params.get("reason") === "loggedout") UI.setMessage("authMessage", t("auth.loggedOut"));
    if (params.get("reason") === "deleted") UI.setMessage("authMessage", t("auth.deleted"));
    UI.checkApiStatus();
    el("loginForm")?.addEventListener("submit", onLogin);
    el("registerForm")?.addEventListener("submit", onRegister);
  }

  return { initialise };
})();

window.addEventListener("DOMContentLoaded", LoginPage.initialise);
