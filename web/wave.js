/**
 * Real-time oscilloscope-style visualization of DGLab V2 (X,Y,Z) waves.
 * Lightweight: ~30fps, fewer samples, no shadowBlur.
 */
const WaveScope = (() => {
  const HISTORY_MS = 2000;
  const SAMPLE_MS = 8;
  const TARGET_FPS = 30;
  const FRAME_MS = 1000 / TARGET_FPS;

  function normalizeSteps(raw) {
    if (!Array.isArray(raw) || raw.length === 0) return [[5, 95, 20]];
    return raw.map((item) => {
      if (Array.isArray(item)) {
        return [
          Math.max(1, Number(item[0]) || 1),
          Math.max(0, Number(item[1]) || 0),
          Math.max(0, Number(item[2]) || 0),
        ];
      }
      return [5, 95, 20];
    });
  }

  function cycleDuration(steps) {
    let sum = 0;
    for (let i = 0; i < steps.length; i++) sum += steps[i][0] + steps[i][1];
    return sum || 100;
  }

  function sampleAt(steps, tMs, strength, limit) {
    const cycle = cycleDuration(steps);
    let t = tMs % cycle;
    if (t < 0) t += cycle;
    for (let i = 0; i < steps.length; i++) {
      const x = steps[i][0];
      const y = steps[i][1];
      const z = steps[i][2];
      if (t < x) {
        const zNorm = z > 40 ? 1 : z / 40;
        const sNorm = limit > 0 ? Math.min(1, strength / limit) : 0;
        return sNorm * (0.25 + 0.75 * zNorm);
      }
      t -= x;
      if (t < y) return 0;
      t -= y;
    }
    return 0;
  }

  function createChannel(canvas, color) {
    const ctx = canvas.getContext("2d", { alpha: false });
    const state = {
      steps: [[5, 95, 20]],
      strength: 0,
      limit: 50,
      color,
      history: new Float32Array(Math.ceil(HISTORY_MS / SAMPLE_MS)),
      histLen: 0,
      histWrite: 0,
      lastTs: performance.now(),
      phaseMs: 0,
      cssW: 0,
      cssH: 0,
    };

    const maxSamples = state.history.length;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      state.cssW = Math.max(1, rect.width);
      state.cssH = Math.max(1, rect.height);
      canvas.width = Math.max(1, Math.floor(state.cssW * dpr));
      canvas.height = Math.max(1, Math.floor(state.cssH * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function setData({ wave, strength, limit }) {
      state.steps = normalizeSteps(wave);
      state.strength = Number(strength) || 0;
      state.limit = Math.max(1, Number(limit) || 50);
    }

    function meta() {
      const steps = state.steps;
      const cycle = cycleDuration(steps);
      return {
        steps: steps.length,
        cycleMs: Math.round(cycle),
        freqHz: cycle > 0 ? 1000 / cycle : 0,
        xyz: steps[0] || [5, 95, 20],
        strength: state.strength,
      };
    }

    function pushSample(v) {
      state.history[state.histWrite] = v;
      state.histWrite = (state.histWrite + 1) % maxSamples;
      if (state.histLen < maxSamples) state.histLen++;
    }

    function tick(now) {
      const dt = Math.min(50, now - state.lastTs);
      state.lastTs = now;
      state.phaseMs += dt;

      let remain = dt;
      while (remain > 0) {
        const step = remain > SAMPLE_MS ? SAMPLE_MS : remain;
        const v = sampleAt(
          state.steps,
          state.phaseMs - remain,
          state.strength,
          state.limit
        );
        pushSample(v);
        remain -= step;
      }
    }

    function draw() {
      const w = state.cssW;
      const h = state.cssH;
      if (w <= 0 || h <= 0) return;

      ctx.fillStyle = "#050505";
      ctx.fillRect(0, 0, w, h);

      // sparse grid
      ctx.strokeStyle = "rgba(255,255,255,0.04)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, h * 0.5);
      ctx.lineTo(w, h * 0.5);
      ctx.moveTo(w * 0.5, 0);
      ctx.lineTo(w * 0.5, h);
      ctx.stroke();

      const mid = h * 0.72;
      const n = state.histLen;
      if (n < 2) return;

      const amp = h * 0.55;
      const start = (state.histWrite - n + maxSamples) % maxSamples;

      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const idx = (start + i) % maxSamples;
        const x = (i / (n - 1)) * w;
        const y = mid - state.history[idx] * amp;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = state.color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    resize();
    return { resize, setData, tick, draw, meta };
  }

  function mount({ canvasA, canvasB, metaA, metaB }) {
    const chA = createChannel(canvasA, "#6ea8fe");
    const chB = createChannel(canvasB, "#3dd68c");
    let raf = 0;
    let lastFrame = 0;
    let metaTick = 0;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function formatMeta(m, labelEl) {
      if (!labelEl) return;
      const [x, y, z] = m.xyz;
      labelEl.textContent = `steps ${m.steps} · ${m.cycleMs}ms · ~${m.freqHz.toFixed(1)}Hz · XYZ(${x},${y},${z}) · S=${m.strength}`;
    }

    function frame(now) {
      raf = requestAnimationFrame(frame);
      if (now - lastFrame < FRAME_MS) return;
      lastFrame = now;
      chA.tick(now);
      chB.tick(now);
      chA.draw();
      chB.draw();
      metaTick++;
      if (metaTick % 6 === 0) {
        formatMeta(chA.meta(), metaA);
        formatMeta(chB.meta(), metaB);
      }
    }

    function update(status) {
      if (!status) return;
      chA.setData({ wave: status.waveA, strength: status.strengthA, limit: status.limitA });
      chB.setData({ wave: status.waveB, strength: status.strengthB, limit: status.limitB });
    }

    function start() {
      cancelAnimationFrame(raf);
      if (reduced) {
        const now = performance.now();
        chA.tick(now);
        chB.tick(now);
        chA.draw();
        chB.draw();
        formatMeta(chA.meta(), metaA);
        formatMeta(chB.meta(), metaB);
        return;
      }
      raf = requestAnimationFrame(frame);
    }

    function stop() {
      cancelAnimationFrame(raf);
    }

    let resizeTimer = 0;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        chA.resize();
        chB.resize();
      }, 100);
    });

    start();
    return {
      update,
      start,
      stop,
      resize: () => {
        chA.resize();
        chB.resize();
      },
    };
  }

  return { mount };
})();

window.WaveScope = WaveScope;
