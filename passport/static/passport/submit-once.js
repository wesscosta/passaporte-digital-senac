/* Evita o reenvio acidental (toque duplo) de formulários marcados com data-submit-once. O servidor continua decidindo. */
(function () {
  "use strict";
  document.querySelectorAll("form[data-submit-once]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.submitting === "1") {
        event.preventDefault();
        return;
      }
      form.dataset.submitting = "1";
      form.querySelectorAll("button[type=submit]").forEach(function (button) { button.setAttribute("aria-disabled", "true"); });
    });
  });
  // Ao voltar pelo histórico (bfcache), libera o formulário novamente.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll("form[data-submit-once]").forEach(function (form) {
      delete form.dataset.submitting;
      form.querySelectorAll("button[type=submit]").forEach(function (button) { button.removeAttribute("aria-disabled"); });
    });
  });
})();
