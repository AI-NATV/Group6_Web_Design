const FeedbackForm = (() => {
  function initialise() {
    const form = document.getElementById("feedbackForm");
    if (!form) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = document.getElementById("feedbackSubmit");
      const payload = {
        full_name: document.getElementById("feedbackName").value.trim(),
        email: document.getElementById("feedbackEmail").value.trim(),
        message: document.getElementById("feedbackMessageText").value.trim(),
      };
      button.disabled = true;
      button.textContent = I18n.t("feedback.sending");
      UI.setMessage("feedbackStatus", "");
      try {
        await Api.submitFeedback(payload);
        form.reset();
        UI.setMessage("feedbackStatus", I18n.t("feedback.success"), "success");
      } catch (error) {
        UI.setMessage("feedbackStatus", `${I18n.t("feedback.error")} ${error.message}`, "error");
      } finally {
        button.disabled = false;
        button.textContent = I18n.t("feedback.submit");
      }
    });
  }

  return { initialise };
})();

window.addEventListener("DOMContentLoaded", FeedbackForm.initialise);
