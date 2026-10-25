const $ = (id) => document.getElementById(id);

const ui = {
  pillDevice: $("pill-device"),
  pillWs: $("pill-ws"),
  pillBind: $("pill-bind"),
  deviceState: $("device-state"),
  valA: $("val-a"),
  valB: $("val-b"),
  limA: $("lim-a"),
  limB: $("lim-b"),
  sliderA: $("slider-a"),
  sliderB: $("slider-b"),
  qrInput: $("qr-input"),
  qrDrop: $("qr-drop"),
  qrFile: $("qr-file"),
  clientId: $("client-id"),
  targetId: $("target-id"),
  wsUrl: $("ws-url"),
  cfgLimA: $("cfg-lim-a"),
  cfgLimB: $("cfg-lim-b"),
  cfgRatio: $("cfg-ratio"),
  log: $("log"),
  errLine: $("err-line"),
  clock: $("clock"),
  btnDeviceConnect: $("btn-device-connect"),
  btnDeviceDisconnect: $("btn-device-disconnect"),
};

let dragging = { A: false, B: false };
let lastStatus = null;
let decoding = false;
let scope = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const data = await res.json();
      msg = data.detail || JSON.stringify(data);
    } catch (_) {}
    throw new Error(I18N.translateMaybe(msg));
  }
  return res.json();
}

function setPill(el, text, mode) {
  el.textContent = text;
  el.className = "pill " + (mode || "off");
}

// Wrap async click/change handlers so server errors reach the error line
// instead of becoming unhandled rejections.
function guard(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      ui.errLine.textContent = e.message;
    }
  };
}

function flash(el, cls = "flash") {
  if (!el) return;
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
}

function renderStatus(s) {
  lastStatus = s;
  const on = I18N.t("status.on");
  const off = I18N.t("status.off");
  const yes = I18N.t("status.yes");
  const no = I18N.t("status.no");

  setPill(
    ui.pillDevice,
    I18N.t("status.device", { state: s.deviceConnected ? on : s.deviceConnecting ? "…" : off }),
    s.deviceConnected ? "on" : s.deviceConnecting ? "warn" : "off"
  );
  setPill(
    ui.pillWs,
    I18N.t("status.ws", { state: s.wsConnected ? on : off }),
    s.wsConnected ? "on" : "off"
  );
  setPill(
    ui.pillBind,
    I18N.t("status.bind", { state: s.wsBound ? yes : no }),
    s.wsBound ? "on" : s.wsConnected ? "warn" : "off"
  );

  if (s.deviceConnected) {
    ui.deviceState.textContent = I18N.t("device.stateOn");
    ui.deviceState.className = "device-state on";
  } else if (s.deviceConnecting) {
    ui.deviceState.textContent = I18N.t("device.stateConnecting");
    ui.deviceState.className = "device-state warn";
  } else {
    ui.deviceState.textContent = I18N.t("device.stateOff");
    ui.deviceState.className = "device-state";
  }

  ui.btnDeviceConnect.disabled = !!s.deviceConnecting;
  ui.btnDeviceConnect.classList.toggle("loading", !!s.deviceConnecting);

  if (!dragging.A) {
    ui.sliderA.max = s.limitA;
    ui.sliderA.value = s.strengthA;
    ui.valA.textContent = s.strengthA;
  }
  if (!dragging.B) {
    ui.sliderB.max = s.limitB;
    ui.sliderB.value = s.strengthB;
    ui.valB.textContent = s.strengthB;
  }

  ui.limA.textContent = s.limitA;
  ui.limB.textContent = s.limitB;
  ui.clientId.textContent = s.clientId || "—";
  ui.targetId.textContent = s.targetId || "—";
  ui.wsUrl.textContent = s.wsUrl || "—";

  const err = s.lastError || s.deviceError || "";
  ui.errLine.textContent = I18N.translateMaybe(err);

  const focused = document.activeElement?.id;
  if (!["qr-input", "cfg-lim-a", "cfg-lim-b", "cfg-ratio"].includes(focused)) {
    if (!ui.qrInput.value && s.qrContent) ui.qrInput.value = s.qrContent;
    ui.cfgLimA.value = s.limitA;
    ui.cfgLimB.value = s.limitB;
    ui.cfgRatio.value = s.waveConvertRatio;
  }

  ui.log.innerHTML = (s.logs || [])
    .slice()
    .reverse()
    .map((line) => `<div>${escapeHtml(I18N.formatLog(line))}</div>`)
    .join("");

  if (scope) scope.update(s);
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function refresh() {
  try {
    const s = await api("/api/status");
    renderStatus(s);
  } catch (e) {
    ui.errLine.textContent = e.message;
  }
}

async function setStrength(channel, value, mode = "set") {
  const s = await api("/api/strength", {
    method: "POST",
    body: JSON.stringify({ channel, value: Number(value), mode }),
  });
  renderStatus(s);
}

function bindSlider(slider, channel, valueEl) {
  slider.addEventListener("pointerdown", () => {
    dragging[channel] = true;
  });
  slider.addEventListener("pointerup", guard(async () => {
    dragging[channel] = false;
    await setStrength(channel, slider.value, "set");
  }));
  slider.addEventListener("input", () => {
    valueEl.textContent = slider.value;
    if (lastStatus && scope) {
      scope.update({
        ...lastStatus,
        strengthA: channel === "A" ? Number(slider.value) : lastStatus.strengthA,
        strengthB: channel === "B" ? Number(slider.value) : lastStatus.strengthB,
      });
    }
  });
  slider.addEventListener("change", guard(async () => {
    dragging[channel] = false;
    await setStrength(channel, slider.value, "set");
  }));
}

async function uploadQrImage(file) {
  if (!file || !file.type.startsWith("image/")) {
    ui.errLine.textContent = I18N.t("error.not_image");
    return;
  }
  if (decoding) return;
  decoding = true;
  ui.qrDrop.classList.add("busy");
  try {
    const form = new FormData();
    form.append("file", file, file.name || "qr.png");
    const data = await api("/api/qr/image", { method: "POST", body: form });
    ui.qrInput.value = data.qrContent;
    renderStatus(data.status);
    flash(ui.qrDrop, "success-flash");
  } catch (e) {
    ui.errLine.textContent = e.message;
    flash(ui.qrDrop, "error-flash");
  } finally {
    decoding = false;
    ui.qrDrop.classList.remove("busy");
  }
}

function bindDropzone() {
  const zone = ui.qrDrop;
  const fileInput = ui.qrFile;
  const setDrag = (on) => zone.classList.toggle("dragover", on);

  ["dragenter", "dragover"].forEach((evt) => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      setDrag(true);
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (evt === "dragleave") setDrag(false);
    });
  });

  zone.addEventListener("drop", (e) => {
    setDrag(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) uploadQrImage(file);
  });

  zone.addEventListener("click", () => fileInput.click());
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) uploadQrImage(file);
    fileInput.value = "";
  });

  window.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) uploadQrImage(file);
        return;
      }
    }
  });
}

function tickClock() {
  const locale = I18N.locale === "zh" ? "zh-CN" : "en-US";
  ui.clock.textContent = new Date().toLocaleTimeString(locale);
}

async function bootstrap() {
  await I18N.init();
  I18N.onChange(() => {
    if (lastStatus) renderStatus(lastStatus);
    tickClock();
  });

  scope = WaveScope.mount({
    canvasA: $("wave-a"),
    canvasB: $("wave-b"),
    metaA: $("wave-meta-a"),
    metaB: $("wave-meta-b"),
  });

  bindSlider(ui.sliderA, "A", ui.valA);
  bindSlider(ui.sliderB, "B", ui.valB);
  bindDropzone();

  document.querySelectorAll("[data-delta]").forEach((btn) => {
    btn.addEventListener("click", guard(async () => {
      const ch = btn.dataset.ch;
      const delta = Number(btn.dataset.delta);
      await setStrength(ch, Math.abs(delta), delta >= 0 ? "add" : "sub");
    }));
  });

  document.querySelectorAll("[data-set]").forEach((btn) => {
    btn.addEventListener("click", guard(async () => {
      await setStrength(btn.dataset.ch, Number(btn.dataset.set), "set");
    }));
  });

  $("btn-stop").addEventListener("click", guard(async () => {
    const s = await api("/api/emergency-stop", { method: "POST", body: "{}" });
    renderStatus(s);
    flash($("btn-stop"), "flash");
  }));

  ui.btnDeviceConnect.addEventListener("click", async () => {
    try {
      ui.btnDeviceConnect.classList.add("loading");
      const s = await api("/api/device/connect", { method: "POST", body: "{}" });
      renderStatus(s);
    } catch (e) {
      ui.errLine.textContent = e.message;
    }
  });

  ui.btnDeviceDisconnect.addEventListener("click", async () => {
    try {
      const s = await api("/api/device/disconnect", { method: "POST", body: "{}" });
      renderStatus(s);
    } catch (e) {
      ui.errLine.textContent = e.message;
    }
  });

  $("btn-upload").addEventListener("click", () => ui.qrFile.click());

  $("btn-scan").addEventListener("click", async () => {
    try {
      const data = await api("/api/qr/scan", { method: "POST", body: "{}" });
      ui.qrInput.value = data.qrContent;
      renderStatus(data.status);
      flash(ui.qrDrop, "success-flash");
    } catch (e) {
      ui.errLine.textContent = e.message;
    }
  });

  $("btn-connect").addEventListener("click", async () => {
    try {
      const data = await api("/api/ws/connect", {
        method: "POST",
        body: JSON.stringify({ qrContent: ui.qrInput.value.trim() }),
      });
      renderStatus(data.status);
    } catch (e) {
      ui.errLine.textContent = e.message;
    }
  });

  $("btn-disconnect").addEventListener("click", guard(async () => {
    const s = await api("/api/ws/disconnect", { method: "POST", body: "{}" });
    renderStatus(s);
  }));

  $("btn-save").addEventListener("click", async () => {
    try {
      const s = await api("/api/config", {
        method: "POST",
        body: JSON.stringify({
          qrContent: ui.qrInput.value.trim(),
          limitA: Number(ui.cfgLimA.value),
          limitB: Number(ui.cfgLimB.value),
          waveConvertRatio: Number(ui.cfgRatio.value),
        }),
      });
      renderStatus(s);
    } catch (e) {
      ui.errLine.textContent = e.message;
    }
  });

  await refresh();
  setInterval(refresh, 800);
  setInterval(tickClock, 1000);
  tickClock();
}

bootstrap();
