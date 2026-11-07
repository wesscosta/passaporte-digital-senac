/* Atualiza o código sem recarregar a tela ou interromper o foco da equipe. */
(function () {
  "use strict";
  const root = document.querySelector("[data-station]");
  if (!root) return;
  const image = root.querySelector(".station-qr");
  const code = root.querySelector(".station-code");
  const status = root.querySelector("[data-station-status]");
  const countdown = root.querySelector("[data-station-timer]");
  const seconds = root.querySelector("[data-station-seconds]");
  const progress = root.querySelector("[data-station-progress]");
  let timer = null;
  let deadline = 0;
  let loading = false;

  function tick() {
    if (document.hidden) return;
    const remaining = Math.max(0, deadline - performance.now());
    progress.value = Math.min(60000, remaining);
    seconds.textContent = Math.ceil(remaining / 1000) + " s";
    if (remaining > 0) {
      timer = setTimeout(tick, Math.min(1000, remaining));
    } else {
      status.textContent = "Atualizando código…";
      // Aguarda a troca de janela no servidor antes de buscar o novo QR.
      timer = setTimeout(refresh, 250);
    }
  }

  function schedule(delay) {
    clearTimeout(timer);
    if (document.hidden) return;
    const duration = Math.max(1, Math.min(Number(delay) || 15000, 60000));
    deadline = performance.now() + duration;
    countdown.hidden = false;
    status.textContent = "Atualização automática a cada minuto.";
    tick();
  }

  function markStale(message) {
    image.hidden = true;
    code.textContent = "------";
    countdown.hidden = true;
    root.classList.add("is-stale");
    status.textContent = message;
  }

  async function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    const requestStarted = performance.now();
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
      const source = freshImage && freshImage.getAttribute("src");
      const freshDelay = fresh && Number(fresh.dataset.refreshMs);
      if (!fresh || !source || !source.startsWith("data:image/svg+xml;base64,") ||
          !freshCode || !/^\d{6}$/.test(freshCode.textContent.trim()) ||
          !Number.isFinite(freshDelay) || freshDelay < 1 || freshDelay > 60000) {
        throw new Error("Resposta inválida");
      }
      if (document.hidden) return;
      image.src = source;
      code.textContent = freshCode.textContent.trim();
      image.hidden = false;
      root.classList.remove("is-stale");
      // Desconta o tempo da requisição para não exibir uma contagem atrasada.
      schedule(Math.max(1, freshDelay - (performance.now() - requestStarted)));
    } catch (_) {
      if (document.hidden) return;
      markStale("Não foi possível atualizar. Verifique a conexão ou atualize a página.");
      clearTimeout(timer);
      timer = setTimeout(refresh, 15000);
    } finally {
      clearTimeout(timeout);
      loading = false;
    }
  }

  function resume() {
    if (!document.hidden) {
      markStale("Atualizando código…");
      refresh();
    }
  }
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) clearTimeout(timer);
    else resume();
  });
  window.addEventListener("pagehide", function () { clearTimeout(timer); });
  window.addEventListener("pageshow", function (event) { if (event.persisted) resume(); });
  schedule(root.dataset.refreshMs);
})();

