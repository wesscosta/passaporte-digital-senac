/* Atualiza o código sem recarregar a tela ou interromper o foco da equipe. */
(function () {
  "use strict";
  const root = document.querySelector("[data-station]");
  if (!root) return;
  const image = root.querySelector(".station-qr");
  const code = root.querySelector(".station-code");
  const status = root.querySelector("[data-station-status]");
  let timer = null;
  let loading = false;

  function schedule(delay) {
    clearTimeout(timer);
    if (!document.hidden) timer = setTimeout(refresh, Math.max(1000, Math.min(Number(delay) || 15000, 61000)));
  }

  function markStale(message) {
    image.hidden = true;
    code.textContent = "------";
    root.classList.add("is-stale");
    status.textContent = message;
  }

  async function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    const controller = new AbortController();
    const timeout = setTimeout(function () { controller.abort(); }, 8000);
    try {
      const response = await fetch(window.location.href, {
        credentials: "same-origin", cache: "no-store", signal: controller.signal
      });
      if (!response.ok || response.redirected) throw new Error("Resposta indisponível");
      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const fresh = doc.querySelector("[data-station]");
      const freshImage = fresh && fresh.querySelector(".station-qr");
      const freshCode = fresh && fresh.querySelector(".station-code");
      if (!fresh || !freshImage || !freshCode ||
          !freshImage.getAttribute("src").startsWith("data:image/svg+xml;base64,") ||
          !/^\d{6}$/.test(freshCode.textContent.trim())) throw new Error("Resposta inválida");
      image.src = freshImage.getAttribute("src");
      code.textContent = freshCode.textContent.trim();
      image.hidden = false;
      root.classList.remove("is-stale");
      status.textContent = "Código atualizado automaticamente.";
      schedule(fresh.dataset.refreshMs);
    } catch (_) {
      markStale("Não foi possível atualizar. Verifique a conexão ou atualize a página.");
      schedule(15000);
    } finally {
      clearTimeout(timeout);
      loading = false;
    }
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      clearTimeout(timer);
    } else {
      markStale("Atualizando código…");
      refresh();
    }
  });
  window.addEventListener("pagehide", function () { clearTimeout(timer); });
  schedule(root.dataset.refreshMs);
})();

