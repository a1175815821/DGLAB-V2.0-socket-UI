/**
 * Lightweight i18n runtime.
 * Add a language: create web/i18n/<code>.json and register it in web/i18n/index.json
 */
const I18N = (() => {
  const STORAGE_KEY = "dglab.locale";
  const BASE = "/static/i18n";

  let catalog = {};
  let locale = "en";
  let meta = { default: "en", locales: [] };
  const listeners = new Set();

  function detectLocale(supportedCodes) {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && supportedCodes.includes(saved)) return saved;

    const candidates = [
      ...(navigator.languages || []),
      navigator.language,
      navigator.userLanguage,
    ].filter(Boolean);

    for (const raw of candidates) {
      const lower = String(raw).toLowerCase();
      const exact = supportedCodes.find((c) => c.toLowerCase() === lower);
      if (exact) return exact;
      const prefix = lower.split("-")[0];
      const byPrefix = supportedCodes.find((c) => c.toLowerCase().startsWith(prefix));
      if (byPrefix) return byPrefix;
    }
    return meta.default || "en";
  }

  function interpolate(template, params = {}) {
    return String(template).replace(/\{(\w+)\}/g, (_, key) => {
      if (params[key] === undefined || params[key] === null) return `{${key}}`;
      return String(params[key]);
    });
  }

  function resolveParams(params = {}) {
    const out = {};
    for (const [k, v] of Object.entries(params || {})) {
      if (typeof v === "string" && catalog[v] !== undefined) {
        out[k] = catalog[v];
      } else {
        out[k] = v;
      }
    }
    return out;
  }

  function t(key, params) {
    if (!key) return "";
    const value = catalog[key];
    if (value === undefined) return key;
    return interpolate(value, resolveParams(params));
  }


  function apply(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      if (!key) return;
      el.textContent = t(key);
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      if (!key) return;
      el.setAttribute("placeholder", t(key));
    });
    root.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const key = el.getAttribute("data-i18n-title");
      if (!key) return;
      el.setAttribute("title", t(key));
    });
    root.querySelectorAll("[data-i18n-aria]").forEach((el) => {
      const key = el.getAttribute("data-i18n-aria");
      if (!key) return;
      el.setAttribute("aria-label", t(key));
    });

    const titleKey = document.documentElement.getAttribute("data-i18n-title-key");
    if (titleKey) document.title = t(titleKey);
    document.documentElement.lang = locale === "zh" ? "zh-CN" : locale;

    document.querySelectorAll("[data-locale]").forEach((btn) => {
      const active = btn.getAttribute("data-locale") === locale;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  async function loadCatalog(code) {
    const entry = meta.locales.find((l) => l.code === code);
    const file = entry?.file || `${code}.json`;
    const res = await fetch(`${BASE}/${file}`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`Failed to load locale: ${code}`);
    return res.json();
  }

  async function setLocale(code, { persist = true } = {}) {
    const supported = meta.locales.map((l) => l.code);
    if (!supported.includes(code)) code = meta.default || "en";
    catalog = await loadCatalog(code);
    locale = code;
    if (persist) localStorage.setItem(STORAGE_KEY, code);
    apply();
    listeners.forEach((fn) => fn(locale));
    return locale;
  }

  async function init() {
    const res = await fetch(`${BASE}/index.json`, { cache: "no-cache" });
    if (!res.ok) throw new Error("Failed to load i18n index");
    meta = await res.json();
    const supported = (meta.locales || []).map((l) => l.code);
    const initial = detectLocale(supported);
    await setLocale(initial, { persist: !!localStorage.getItem(STORAGE_KEY) });

    document.querySelectorAll("[data-locale]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.getAttribute("data-locale");
        if (code) setLocale(code);
      });
    });

    return locale;
  }

  function onChange(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function translateMaybe(value, params) {
    if (value == null || value === "") return "";
    const str = String(value);
    if (catalog[str] !== undefined) return t(str, params);
    return str;
  }

  function formatLog(entry) {
    if (entry == null) return "";
    if (typeof entry === "string") return translateMaybe(entry);
    if (typeof entry === "object") {
      const key = entry.key || entry.message;
      if (!key) return "";
      if (catalog[key] !== undefined) return t(key, entry.params || {});
      return String(key);
    }
    return String(entry);
  }

  return {
    init,
    t,
    apply,
    setLocale,
    onChange,
    formatLog,
    translateMaybe,
    get locale() {
      return locale;
    },
    get meta() {
      return meta;
    },
  };
})();

window.I18N = I18N;
