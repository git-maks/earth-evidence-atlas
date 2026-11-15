/* Exercise the real tab when the static files are newer than the running API. */
"use strict";
const assert = require("assert"), fs = require("fs"), vm = require("vm");
const source = fs.readFileSync("web/resilience.js", "utf8");
const ids = ["t2m", "lst_day", "precip", "soil_root"];

function setup(detail) {
  const calls = [], nodes = {}, exports = {};
  let report, exportId = 0;
  function $(selector) {
    if (!nodes[selector]) nodes[selector] = {
      href: "", dataset: {}, classList: { contains: () => true },
      querySelectorAll: () => [], closest: () => ({}), replaceChildren() {}, setAttribute() {},
      dispatchEvent(event) { report = event.detail.report; },
    };
    return nodes[selector];
  }
  function BrowserURL(...args) { return new URL(...args); }
  BrowserURL.createObjectURL = (blob) => {
    const id = "blob:" + exportId++;
    exports[id] = blob.content;
    return id;
  };
  BrowserURL.revokeObjectURL = (id) => { delete exports[id]; };
  const context = vm.createContext({
    $, ALL: "1,2,3,4,5,6,7,8,9,10,11,12", MIN_PERIOD_SPAN: 4, URLSearchParams, URL: BrowserURL,
    Blob: function ([content]) { this.content = content; }, CustomEvent: function (name, options) { Object.assign(this, options); },
    location: { href: "http://atlas.test/" }, history: { replaceState() {} },
    Option: function () {}, AbortController: function () { this.abort = () => {}; },
    CAT: { regions: [{ id: "central_europe", bbox: [14, 49, 24, 55], name: "Central Europe" }], available: {},
      variables: ids.map((id) => ({ id, years: id === "lst_day" ? [2001, 2024] : [1981, 2025], caveats: [] })),
      methods: {} },
    t: (value) => value, esc: String, ic: String, fmtP: String,
    I18N: { response: (path, card) => card, number: String },
    available: (variable) => variable !== "soil_root", savedPlaces: () => [],
    coversPlace: (outer, inner) => outer[0] <= inner[0] && outer[1] <= inner[1] && outer[2] >= inner[2] && outer[3] >= inner[3],
    sameBox: (a, b) => a.every((coordinate, index) => coordinate === b[index]),
    api: async (path, query) => {
      calls.push([path, Object.fromEntries(query)]);
      if (path === "resilience") throw Object.assign(new Error(detail), { status: 404, detail });
      assert.strictEqual(path, "analysis");
      return { _raw: { result: { slope: 0.123456 }, verdict: { code: "ci_includes_zero" },
        provenance: { citation: "fixture" }, cross_check: null, trend_units: "units per decade", cells: 1 } };
    },
  });
  vm.runInContext(source + "\nthis.module = Resilience;", context);
  return { load: () => context.module.enter(), open: (hash) => context.module.restore(new URLSearchParams(hash)),
    calls, nodes, exports, get report() { return report; } };
}

(async () => {
  const legacy = setup("Not Found");
  await legacy.load();
  assert.strictEqual(legacy.nodes["#resilience"].dataset.state, "ready");
  assert.deepStrictEqual(legacy.calls.map(([path]) => path), ["resilience", "analysis", "analysis", "analysis"]);
  for (const [, params] of legacy.calls.slice(1)) {
    assert.strictEqual(params.start, "2001");
    assert.strictEqual(params.end, "2024");
    assert.strictEqual(params.region, "central_europe");
  }
  const report = JSON.parse(JSON.stringify(legacy.report));
  assert.strictEqual(report.cards[0].result.slope, 0.123456);
  assert.strictEqual(report.cards[3].status, "missing_cube");
  assert.strictEqual(report.cards[3].result, null);
  assert.deepStrictEqual(JSON.parse(legacy.exports[legacy.nodes["#resilience-json"].href]), report);
  assert(legacy.exports[legacy.nodes["#resilience-csv"].href].includes("result.slope"));

  await legacy.open("bbox=-150,0,-149,1");
  assert.strictEqual(legacy.nodes["#resilience"].dataset.state, "empty");
  assert.strictEqual(legacy.report.years, null);
  assert(legacy.report.cards.every((card) => card.result === null));
  assert.strictEqual(legacy.calls.length, 4);

  const unknown = setup("unknown region");
  await unknown.load();
  assert.strictEqual(unknown.nodes["#resilience"].dataset.state, "error");
  assert.deepStrictEqual(unknown.calls.map(([path]) => path), ["resilience"]);
})().catch((error) => { console.error(error); process.exitCode = 1; });
