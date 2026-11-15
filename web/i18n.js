/* Localisation resources and adapters for the existing English API templates. */
"use strict";

const I18N = (() => {
  const supported = ["en", "es", "pl"], cache = new Map();
  let language = "en", english = {}, dictionary = {}, exact = new Map(), templates = [];
  const get = (object, path) => path.split(".").reduce((node, key) => node == null ? undefined : node[key], object);
  const escape = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const number = (value, options = {}) => new Intl.NumberFormat(language, Object.assign({ useGrouping: false, maximumFractionDigits: 6 }, options)).format(value);
  function t(key, params = {}) {
    const translated = get(dictionary, key);
    const value = translated === undefined ? get(english, key) : translated;
    if (typeof value !== "string") return key;
    return value.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g, (whole, name) => params[name] == null ? whole : String(params[name]));
  }
  function html(key, params = {}) {
    return t(key, Object.fromEntries(Object.entries(params).map(([name, value]) => [name, escape(value)])));
  }
  async function load(code) {
    if (!cache.has(code)) cache.set(code, fetch(`/static/locales/${code}.json`).then((response) => {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).catch((error) => { cache.delete(code); throw error; }));
    return cache.get(code);
  }
  function flatten(node, prefix = "") {
    return Object.entries(node).flatMap(([name, value]) => {
      const key = prefix ? `${prefix}.${name}` : name;
      return value && typeof value === "object" ? flatten(value, key) : [[key, value]];
    });
  }
  function indexEnglish() {
    exact = new Map(flatten(english).filter(([, value]) => typeof value === "string").map(([key, value]) => [value, key]));
    Object.entries(english.catalog.regions).forEach(([id, region]) => { exact.set(region.name.split(" (")[0], `catalog.regions.${id}.name`); });
    templates = flatten(english).filter(([key, value]) => (/^(answers|errors|jobs|catalog\.customRegion)\./.test(key) || key.startsWith("common.pValue")) && typeof value === "string" && value.includes("{") && !key.startsWith("answers.variables.generic"))
      .map(([key, value]) => {
        const names = [];
        const pattern = value.split(/(\{[A-Za-z][A-Za-z0-9_]*\})/g).map((part) => {
          if (part.startsWith("{")) {
            const name = part.slice(1, -1); names.push(name);
            if (["start", "end", "year"].includes(name)) return "(\\d{4})";
            if (["slope", "totalChange", "ratio", "swing", "relative", "low", "high", "percent", "upPercent", "downPercent", "significantPercent", "agreeing", "total", "effective", "count", "latitude", "longitude", "done", "tiles", "failures", "maxSide", "maxArea", "width", "height", "south", "north", "west", "east"].includes(name)) return "([+−-]?[\\d,.]+|\\?)";
            return "([\\s\\S]*?)";
          }
          return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        }).join("");
        return { key, names, regex: new RegExp(`^${pattern}$`), weight: value.replace(/\{[^}]+\}/g, "").length };
      }).sort((a, b) => b.weight - a.weight);
  }
  // Only API-authored fixed templates pass through this adapter. The DOM uses explicit keys.
  // Values are kept intact when no known source template matches (e.g. a user's area name).
  function text(value, depth = 0) {
    if (typeof value !== "string" || language === "en" || depth > 8) return value;
    const key = exact.get(value);
    if (key) return t(key);
    if (/^[+-]?\d+(?:,\d{3})*(?:\.\d+)?$/.test(value)) {
      return (value.startsWith("+") ? "+" : "") + number(Number(value.replace(/,/g, "")));
    }
    for (const template of templates) {
      const match = template.regex.exec(value);
      if (!match) continue;
      const params = {};
      template.names.forEach((name, index) => { params[name] = text(match[index + 1], depth + 1); });
      return t(template.key, params);
    }
    const separator = /(?<=\.)\s+/.test(value) ? /(?<=\.)\s+/g : /; /g;
    const pieces = value.split(separator);
    if (pieces.length > 1) {
      let index = 0;
      return value.replace(separator, (separator) => `\u0000${separator}\u0000`).split("\u0000")
        .map((piece, i) => i % 2 ? piece : text(pieces[index++], depth + 1)).join("");
    }
    return value;
  }
  function catalog(raw) {
    return Object.assign({}, raw, {
      _raw: raw,
      variables: raw.variables.map((variable) => Object.assign({}, variable, get(dictionary, `catalog.variables.${variable.id}`) || get(english, `catalog.variables.${variable.id}`))),
      regions: raw.regions.map((region) => Object.assign({}, region, get(dictionary, `catalog.regions.${region.id}`) || { name: text(region.name), story: text(region.story) })),
      methods: Object.fromEntries(Object.entries(raw.methods).map(([key, value]) => [key, t(`methods.notes.${key}.text`, { percent: (raw.methods.minimum_data.match(/(\d+)%/) || [])[1] })])),
    });
  }
  function response(path, raw) {
    if (path === "catalog") return catalog(raw);
    if (path === "layers") return raw.map((layer) => Object.assign({}, layer, { _raw: layer, name: get(dictionary, `catalog.regions.${layer.region}.name`) || text(layer.name) }));
    if (path.startsWith("jobs/")) return Object.assign({}, raw, { message: text(raw.message) });
    if (!["analysis", "map", "frame"].includes(path)) return raw;
    const data = Object.assign({}, raw);
    const variable = get(dictionary, `catalog.variables.${raw.variable}`) || get(english, `catalog.variables.${raw.variable}`);
    if (variable) { data.units = variable.units; data.trend_units = variable.trend_units; }
    if (raw.provenance && variable) data.provenance = Object.assign({}, raw.provenance, variable);
    if (raw.verdict) data.verdict = Object.assign({}, raw.verdict, {
      title: t(`verdicts.${raw.verdict.code}.title`),
      text: t(`verdicts.${raw.verdict.code}.${raw.verdict.code === "trend_detected" ? (raw.verdict.methods_agree ? "agree" : "disagree") : "text"}`),
    });
    if (raw.answer) data.answer = Object.assign({}, raw.answer, {
      question: variable ? variable.question : text(raw.answer.question),
      headline: text(raw.answer.headline),
      lines: raw.answer.lines.map((line) => text(line)), how: raw.answer.how.map((line) => text(line)),
      caveat: text(raw.answer.caveat), note: text(raw.answer.note),
    });
    data._raw = raw;
    return data;
  }
  function apply(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
    root.querySelectorAll("[data-i18n-html]").forEach((element) => { element.innerHTML = html(element.dataset.i18nHtml); });
    root.querySelectorAll("[data-i18n-attrs]").forEach((element) => {
      element.dataset.i18nAttrs.split(";").forEach((binding) => {
        const [attribute, key] = binding.split(":");
        element.setAttribute(attribute, t(key));
      });
    });
    document.documentElement.lang = language;
    document.title = t("app.name");
  }
  async function init() {
    english = await load("en"); dictionary = english; indexEnglish();
    let preferred = new URLSearchParams(location.search).get("lang");
    if (!supported.includes(preferred)) {
      try { preferred = localStorage.getItem("atlas.language"); } catch (error) { /* storage is optional */ }
    }
    if (supported.includes(preferred) && preferred !== "en") {
      try { dictionary = await load(preferred); language = preferred; } catch (error) { /* keep English available */ }
    }
    apply();
    const select = document.getElementById("languageSelect"), status = document.getElementById("languageStatus");
    const toggle = document.getElementById("languageToggle"), panel = document.getElementById("languagePanel");
    const setOpen = (open, restoreFocus = false) => {
      if (!toggle || !panel) return;
      panel.hidden = !open; toggle.setAttribute("aria-expanded", String(open));
      if (open) select.focus();
      else if (restoreFocus) toggle.focus();
    };
    if (toggle && panel) {
      toggle.addEventListener("click", () => setOpen(panel.hidden));
      document.getElementById("languageClose").addEventListener("click", () => setOpen(false, true));
      document.addEventListener("pointerdown", (event) => {
        if (!panel.hidden && !panel.contains(event.target) && !toggle.contains(event.target)) setOpen(false);
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !panel.hidden) { event.stopPropagation(); setOpen(false, true); }
      }, true);
      panel.addEventListener("focusout", (event) => {
        if (event.relatedTarget && !panel.contains(event.relatedTarget) && !toggle.contains(event.relatedTarget)) setOpen(false);
      });
    }
    select.value = language;
    select.addEventListener("change", async () => {
      select.disabled = true; status.textContent = "";
      try {
        const next = select.value;
        dictionary = await load(next); language = next;
        try { localStorage.setItem("atlas.language", language); } catch (error) { /* storage is optional */ }
        const url = new URL(location.href); url.searchParams.set("lang", language); history.replaceState(null, "", url);
        apply(); window.dispatchEvent(new Event("languagechange")); setOpen(false, true);
      } catch (error) { select.value = language; status.textContent = t("localisation.loadError"); }
      finally { select.disabled = false; }
    });
  }
  return { init, t, html, text, response, apply, escape, number, get language() { return language; } };
})();

const t = I18N.t, th = I18N.html, esc = I18N.escape;
