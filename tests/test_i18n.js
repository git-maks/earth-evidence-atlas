/* Run via pytest or pass English analysis fixtures on stdin. No browser or build step required. */
"use strict";
const assert = require("assert"), fs = require("fs"), vm = require("vm");
const source = fs.readFileSync("web/i18n.js", "utf8");
const fixtures = JSON.parse(fs.readFileSync(0, "utf8") || "[]");

async function runtime(preferred, failLanguage) {
  let handler;
  const stored = {}, select = { value: preferred, addEventListener(event, callback) { handler = callback; } };
  const status = {};
  const context = {
    Intl, URL, URLSearchParams, Event: function () {},
    location: { search: preferred ? `?lang=${preferred}` : "", href: "http://localhost/" },
    localStorage: { getItem(key) { return stored[key]; }, setItem(key, value) { stored[key] = value; } },
    history: { replaceState() {} }, window: { dispatchEvent() {} },
    document: { documentElement: {}, querySelectorAll() { return []; }, getElementById(id) { return id === "languageSelect" ? select : id === "languageStatus" ? status : null; } },
    fetch: async (path) => {
      if (path.endsWith(`/${failLanguage}.json`)) throw Error("unavailable");
      return { ok: true, json: async () => JSON.parse(fs.readFileSync("web" + path.replace("/static", ""), "utf8")) };
    },
  };
  vm.createContext(context);
  vm.runInContext(source + "\nthis.api = I18N;", context);
  await context.api.init();
  return { api: context.api, select, status, stored, switch: async (code) => { select.value = code; await handler(); } };
}

(async () => {
  for (const language of ["es", "pl"]) {
    const { api } = await runtime(language);
    assert.strictEqual(api.language, language);
    assert.strictEqual(api.text("A user's custom Mann–Kendall area"), "A user's custom Mann–Kendall area");
    assert(!api.text("How sure: 20 of 40 other start/end periods give the same direction, 12 of them also significant; a rank-based test (Mann–Kendall) gives the same result.").includes("rank-based test"));
    assert(!api.text("How sure: 20 of 40 other start/end periods give the same direction; the rank-based Mann–Kendall test does not reach 5%.").includes("the rank-based"));
    const distribution = api.text("Across the map, 98% of grid cells went up and 2% went down; 86% show a significant trend after correcting for many tests. Fastest warming: around 81°N, 73°E, +0.616 °C per decade.");
    assert(!/Across the map|Fastest warming|show a significant/.test(distribution), distribution);
    assert(!api.html("errors.analysisFailed", { message: '<img src=x onerror="alert(1)">' }).includes("<img"));
    assert(api.html("errors.analysisFailed", { message: "<script>" }).includes("&lt;script&gt;"));
    for (const raw of fixtures) {
      const before = JSON.stringify(raw), result = api.response("analysis", raw);
      assert.strictEqual(JSON.stringify(result.result), JSON.stringify(raw.result));
      assert.strictEqual(JSON.stringify(result.series), JSON.stringify(raw.series));
      assert.strictEqual(JSON.stringify(raw), before, "source response was mutated");
      for (const line of result.answer.lines.concat(result.answer.how, result.answer.headline, result.answer.caveat, result.answer.note)) {
        assert(!/\{[A-Za-z]+\}|per decade|the rank-based|same direction|of grid cells|usual level|valid data|no AI|in the selected area|months|the same area|They agree|They disagree|but not both|Over \d+ years|yearly means|Short record|Same direction|also corrected/.test(line), `${language}: ${line}`);
      }
      assert.notStrictEqual(result.answer.headline, raw.answer.headline);
    }
  }
  const fallback = await runtime("pl", "pl");
  assert.strictEqual(fallback.api.language, "en", "initial load failure must keep English");
  await fallback.switch("pl");
  assert.strictEqual(fallback.api.language, "en");
  assert.strictEqual(fallback.select.value, "en");
  assert(fallback.status.textContent);
  const switching = await runtime("en");
  await switching.switch("pl");
  assert.strictEqual(switching.api.language, "pl");
  assert.strictEqual(switching.stored["atlas.language"], "pl");
  await switching.switch("es");
  assert.strictEqual(switching.api.language, "es");
  assert.strictEqual(switching.stored["atlas.language"], "es");
  console.log(`Localisation runtime passed: ${fixtures.length} answer variants in Polish and Spanish, value preservation, fallback and persistence.`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
