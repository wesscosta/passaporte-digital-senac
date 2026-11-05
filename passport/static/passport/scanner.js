/* Leitura local: nenhum quadro de vídeo é enviado ao servidor. */
(function () {
  "use strict";

  function validateQrText(raw, origin) {
    try {
      const url = new URL(raw, origin);
      if (url.origin !== origin || url.username || url.password || url.search || url.hash) return null;
      if (!/^\/visitar\/[1-9]\d*\/\d{6}\/$/.test(url.pathname)) return null;
      return url.pathname;
    } catch (_) {
      return null;
    }
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { validateQrText };
  }
  if (typeof document === "undefined") return;

  const root = document.querySelector("[data-qr-scanner]");
  if (!root) return;

  const startButton = root.querySelector("[data-scanner-start]");
  const stopButton = root.querySelector("[data-scanner-stop]");
  const stage = root.querySelector("[data-camera-stage]");
  const video = root.querySelector("[data-camera-video]");
  const canvas = root.querySelector("[data-camera-canvas]");
  const status = root.querySelector("[data-scanner-status]");
  let stream = null;
  let frameId = null;
  let running = false;
  let generation = 0;
  let lastFrame = 0;
  let decoderPromise = null;
  let lastInvalid = "";

  function setStatus(text, isError) {
    status.textContent = text;
    status.classList.toggle("is-error", Boolean(isError));
  }

  function stopTracks(media) {
    if (media) media.getTracks().forEach(function (track) { track.stop(); });
  }

  function stopScanner(returnFocus) {
    generation += 1;
    running = false;
    if (frameId !== null) cancelAnimationFrame(frameId);
    frameId = null;
    stopTracks(stream);
    stream = null;
    video.pause();
    video.srcObject = null;
    stage.hidden = true;
    stopButton.hidden = true;
    startButton.hidden = false;
    startButton.disabled = false;
    if (returnFocus) startButton.focus();
  }

  function loadFallback() {
    if (typeof window.jsQR === "function") return Promise.resolve(window.jsQR);
    if (!decoderPromise) {
      decoderPromise = new Promise(function (resolve, reject) {
        const script = document.createElement("script");
        script.src = root.dataset.decoderUrl;
        script.async = true;
        script.onload = function () {
          if (typeof window.jsQR === "function") resolve(window.jsQR);
          else reject(new Error("Leitor indisponível"));
        };
        script.onerror = function () {
          script.remove();
          reject(new Error("Leitor indisponível"));
        };
        document.head.appendChild(script);
      }).catch(function (error) {
        decoderPromise = null;
        throw error;
      });
    }
    return decoderPromise;
  }

  function fallbackReader(jsQR) {
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("Leitor indisponível");
    return {
      kind: "fallback",
      read: function () {
        if (!video.videoWidth || !video.videoHeight) return null;
        const scale = Math.min(1, 960 / Math.max(video.videoWidth, video.videoHeight));
        canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
        canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
        const result = jsQR(pixels.data, pixels.width, pixels.height, { inversionAttempts: "attemptBoth" });
        return result ? result.data : null;
      }
    };
  }

  async function getReader() {
    if ("BarcodeDetector" in window) {
      try {
        const formats = await window.BarcodeDetector.getSupportedFormats();
        if (formats.includes("qr_code")) {
          const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
          return {
            kind: "native",
            read: async function () {
              const results = await detector.detect(video);
              return results.length ? results[0].rawValue : null;
            }
          };
        }
      } catch (_) {
        // Alguns navegadores expõem a API, mas não oferecem QR code.
      }
    }
    return fallbackReader(await loadFallback());
  }

  async function tick(now, token, reader) {
    if (!running || token !== generation) return;
    if (now - lastFrame < 180 || video.readyState < 2) {
      frameId = requestAnimationFrame(function (time) { tick(time, token, reader); });
      return;
    }
    lastFrame = now;
    try {
      const raw = await reader.read();
      if (!running || token !== generation) return;
      if (raw) {
        const destination = validateQrText(raw, window.location.origin);
        if (destination) {
          stopScanner(false);
          setStatus("QR code reconhecido. Abrindo confirmação…", false);
          window.location.assign(destination);
          return;
        }
        if (raw !== lastInvalid) {
          lastInvalid = raw;
          setStatus("Este não é um QR code deste passaporte. Aponte para a tela do estande.", true);
        }
      }
    } catch (_) {
      if (!running || token !== generation) return;
      if (reader.kind === "native") {
        try {
          setStatus("Preparando leitor alternativo…", false);
          const fallback = fallbackReader(await loadFallback());
          if (!running || token !== generation) return;
          setStatus("Aponte para o QR code do estande.", false);
          frameId = requestAnimationFrame(function (time) { tick(time, token, fallback); });
          return;
        } catch (_) {
          // A orientação abaixo mantém o código manual acessível.
        }
      }
      stopScanner(false);
      setStatus("Não foi possível ler o QR code. Tente novamente ou digite o código.", true);
      return;
    }
    frameId = requestAnimationFrame(function (time) { tick(time, token, reader); });
  }

  async function startScanner() {
    const token = ++generation;
    startButton.disabled = true;
    stopButton.hidden = false;
    setStatus("Solicitando acesso à câmera…", false);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" } }
      });
      if (token !== generation) {
        stopTracks(media);
        return;
      }
      stream = media;
      video.srcObject = stream;
      stage.hidden = false;
      await video.play();
      if (token !== generation) return;
      setStatus("Preparando leitor…", false);
      const reader = await getReader();
      if (token !== generation) return;
      running = true;
      lastFrame = 0;
      lastInvalid = "";
      startButton.hidden = true;
      setStatus("Aponte para o QR code do estande.", false);
      frameId = requestAnimationFrame(function (time) { tick(time, token, reader); });
    } catch (error) {
      if (token !== generation) return;
      stopScanner(false);
      if (error && (error.name === "NotAllowedError" || error.name === "SecurityError")) {
        setStatus("A câmera não foi autorizada. Você pode digitar o código abaixo.", true);
      } else if (error && error.name === "NotFoundError") {
        setStatus("Nenhuma câmera foi encontrada. Você pode digitar o código abaixo.", true);
      } else {
        setStatus("Não foi possível abrir o leitor. Tente novamente ou digite o código abaixo.", true);
      }
    }
  }

  if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("Câmera indisponível neste navegador. Digite o código abaixo ou use a câmera do celular.", true);
  } else {
    startButton.hidden = false;
    startButton.addEventListener("click", startScanner);
    stopButton.addEventListener("click", function () {
      stopScanner(true);
      setStatus("Câmera fechada. Você pode abrir novamente ou digitar o código.", false);
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden && (stream || !stopButton.hidden)) {
      stopScanner(false);
      setStatus("Câmera pausada. Abra novamente quando voltar ao passaporte.", false);
    }
  });
  window.addEventListener("pagehide", function () { stopScanner(false); });
})();

