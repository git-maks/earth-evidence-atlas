"""Build a standalone, offline HTML pitch from recorded application evidence and figures."""
from __future__ import annotations

import base64
import html
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs"


def data_uri(path: Path) -> str:
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ttf": "font/ttf"}[path.suffix]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def number(value, digits=3, signed=False):
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def p_label(value):
    return "p < 0.001" if value < 0.001 else f"p = {value:.3f}"


def main():
    evidence = json.loads((HERE / "evidence.json").read_text())
    cases = evidence["analyses"]
    air = cases["air_europe"]["response"]
    annual = cases["ndvi_annual"]["response"]["result"]
    summer = cases["ndvi_summer"]["response"]["result"]
    batch = evidence["simulation_batch"]["response"]
    spikes = evidence["simulation_spikes"]["response"]
    r, robustness = air["result"], air["verdict"]["robustness"]
    catalog = evidence["catalog"]
    check = air["cross_check"]
    assert annual["ci_low"] > 0 and summer["ci_low"] < 0 < summer["ci_high"], "Update the seasonal teaching narrative."
    assert r["slope"] > 0 and check["slope"] > 0, "Update the temperature teaching narrative."
    labels = {
        "ndvi": ("Vegetation greenness", "MOD13A1 V061 · Terra"),
        "lst_day": ("Surface temperature · morning", "MOD11A2 V061 · Terra"),
        "lst_day_aqua": ("Surface temperature · afternoon", "MYD11A2 V061 · Aqua"),
        "t2m": ("Air temperature at 2 m", "POWER T2M · MERRA-2"),
        "precip": ("Precipitation · reanalysis", "POWER PRECTOTCORR · MERRA-2"),
        "precip_gpcp": ("Precipitation · satellite/gauge", "GPCP V2.3 · NASA / NOAA"),
        "soil_root": ("Root-zone soil wetness", "POWER GWETROOT · MERRA-2"),
        "gistemp": ("Surface temperature anomaly", "GISTEMP V4 · GHCN + ERSST"),
    }
    rows = []
    for variable in catalog["variables"]:
        name, product = labels.get(variable["id"], (variable["name"], variable["product"]))
        rows.append(f'<tr><td><strong>{html.escape(name)}</strong><span>{html.escape(product)}</span></td>'
                    f'<td>{variable["years"][0]}–{variable["years"][1]}</td><td>{html.escape(variable["resolution"])}</td>'
                    f'<td>{html.escape(variable["kind"])}</td></tr>')
    source_cards = []
    for variable in catalog["variables"]:
        caveats = "".join(f'<li>{html.escape(c)}</li>' for c in variable["caveats"])
        source_cards.append(f'<article class="source-card"><h3>{html.escape(variable["name"])}</h3>'
                            f'<p>{html.escape(variable["definition"])}</p><p><b>Product:</b> {html.escape(variable["product"])}<br>'
                            f'<b>Provider:</b> {html.escape(variable["provider"])}<br><b>Period:</b> {variable["years"][0]}–{variable["years"][1]}<br>'
                            f'<b>Units:</b> {html.escape(variable["units"])}; trend: {html.escape(variable["trend_units"])}</p>'
                            f'<p><a href="{html.escape(variable["url"], quote=True)}" target="_blank" rel="noopener">{html.escape(variable["citation"])}</a></p>'
                            f'<p><b>Licence:</b> {html.escape(variable["license"])}</p><ul>{caveats}</ul></article>')
    resource_index = json.loads((INPUTS / "challenge-resources.json").read_text())
    resource_links = "".join(f'<li><a href="{html.escape(item["url"], quote=True)}" target="_blank" rel="noopener">{html.escape(item["title"])}</a></li>' for item in resource_index["resources"])
    proof_rows = []
    for key, case in cases.items():
        a, p = case["response"], case["params"]
        v = next(v for v in catalog["variables"] if v["id"] == a["variable"])
        result = a["result"]
        p_value = "&lt; 0.001" if result["p"] < .001 else number(result["p"])
        proof_rows.append(f'<tr><td>{html.escape(key)}</td><td>{html.escape(v["name"])}</td><td>{html.escape(a["region"])}<br>{a["start"]}–{a["end"]}<br>months: {html.escape(str(a["months"]))}</td>'
                          f'<td>{number(result["slope"], signed=True)}<br>{html.escape(a["trend_units"])}</td><td>[{number(result["ci_low"])}; {number(result["ci_high"])}]</td><td>{p_value}</td>'
                          f'<td>{html.escape(a["verdict"]["title"])}</td></tr>')
    methods = "".join(f'<li><b>{html.escape(key.replace("_", " ").capitalize())}:</b> {html.escape(value)}</li>'
                      for key, value in catalog["methods"].items())
    region_names = {v["id"]: v["name"].split(" (")[0] for v in catalog["regions"]}
    variable_names = {v["id"]: v["name"] for v in catalog["variables"]}
    validation_rows = []
    for row in evidence["validation"]["cross_checks"]:
        validation_rows.append(
            f'<tr><td>{html.escape(region_names[row["region"]])}<br>{row["start"]}–{row["end"]}</td>'
            f'<td>{html.escape(variable_names[row["variable"]])}<br>{number(row["slope"], signed=True)}; {html.escape(p_label(row["p"]))}</td>'
            f'<td>{html.escape(variable_names[row["other"]])}<br>{number(row["other_slope"], signed=True)}; {html.escape(p_label(row["other_p"]))}</td>'
            f'<td>{html.escape(p_label(row["difference_p"]))}<br>{html.escape(row["trend_units"])}</td></tr>')
    quality_rows = "".join(f'<li>{html.escape(variable_names[row["variable"]])}, {html.escape(region_names[row["region"]])}: '
        f'{100 * row["kept_share"]:.1f}% of valid-range pixel observations retained. {html.escape(row["rule"])}</li>'
        for row in evidence["validation"]["quality"] if row["kept_share"] is not None)
    deployment = json.loads((HERE / "deployment-check.json").read_text())
    checked = datetime.fromisoformat(deployment["checked_at"]).astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M %Z")
    public_resilience = deployment["checks"].get("/api/resilience?region=central_europe", {})
    rollout = ("The Resilience endpoint was accessible on the public demo." if public_resilience.get("status") == 200 else
               "The public Resilience UI loaded all four cards through its compatibility fallback; the dedicated endpoint returned 404."
               if deployment.get("public_resilience_ui", {}).get("four_cards_loaded") else
               "Resilience passed locally; public availability has not been confirmed.")
    deployment_note = html.escape(f"Public demo checked {checked}. {rollout} The deck records the current local API and UI, with source hashes; it does not restart or deploy the public server. The public demo server was taken offline after the hackathon.")
    template = (HERE / "deck.template.html").read_text()
    replacements = {
        "FONT": data_uri(INPUTS / "nasalization.ttf"),
        "FAVICON": data_uri(HERE / "favicon.svg"),
        "ICON_SPRITE": (INPUTS / "icons.svg").read_text().replace('<svg xmlns="http://www.w3.org/2000/svg">', '<svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true">', 1),
        "AIR_SLOPE": number(r["slope"], signed=True),
        "AIR_LOW": number(r["ci_low"]), "AIR_HIGH": number(r["ci_high"]),
        "AIR_SEN": number(r["sen_slope"], signed=True),
        "AIR_P": html.escape(p_label(r["p"])),
        "AIR_CHECK_SLOPE": number(check["slope"], signed=True),
        "AIR_CHECK_LOW": number(check["ci_low"]), "AIR_CHECK_HIGH": number(check["ci_high"]),
        "AIR_MONTHS": str(r["n"]), "AIR_EFFECTIVE": str(round(r["n_eff"])),
        "AIR_SAME": str(robustness["same_sign"]), "AIR_WINDOWS": str(robustness["windows"]),
        "AIR_SIGNIFICANT_WINDOWS": str(robustness["same_sign_significant"]),
        "NDVI_ANNUAL": number(annual["slope"], signed=True), "NDVI_ANNUAL_P": html.escape(p_label(annual["p"])),
        "NDVI_SUMMER": number(summer["slope"], signed=True), "NDVI_SUMMER_P": html.escape(p_label(summer["p"])),
        "NDVI_ANNUAL_LOW": number(annual["ci_low"]), "NDVI_ANNUAL_HIGH": number(annual["ci_high"]),
        "NDVI_SUMMER_LOW": number(summer["ci_low"]), "NDVI_SUMMER_HIGH": number(summer["ci_high"]),
        "NAIVE_PERCENT": number(100 * batch["naive_significant"] / batch["runs"], 1),
        "CORRECTED_PERCENT": number(100 * batch["corrected_significant"] / batch["runs"], 1),
        "NAIVE_COUNT": str(batch["naive_significant"]), "CORRECTED_COUNT": str(batch["corrected_significant"]),
        "RUNS": str(batch["runs"]),
        "SPIKE_WITH": number(spikes["slope"], signed=True),
        "SPIKE_WITHOUT": number(spikes["original"]["slope"], signed=True),
        "SPIKE_YEARS": str(evidence["simulation_spikes"]["params"]["years"]),
        "SPIKE_SEED": str(evidence["simulation_spikes"]["params"]["seed"]),
        "CAPTURED_LAB": html.escape(evidence["simulation_spikes"]["captured_at"][:19].replace("T", " ") + " Europe/Warsaw"),
        "DATASET_COUNT": str(len(catalog["variables"])),
        "DATASET_ROWS": "".join(rows), "SOURCE_CARDS": "".join(source_cards), "PROOF_ROWS": "".join(proof_rows),
        "METHODS_LIST": methods, "VALIDATION_ROWS": "".join(validation_rows), "QUALITY_ROWS": quality_rows,
        "DEPLOYMENT_NOTE": deployment_note,
        "RESOURCE_LINKS": resource_links,
        "CAPTURED": html.escape(evidence["captured_at"][:19].replace("T", " ") + " Europe/Warsaw"),
        "REVISION": html.escape(evidence["git_revision"][:8]),
        "ORIGINAL_BRIEF": html.escape((INPUTS / "challenge-brief.txt").read_text()),
        "EVIDENCE_JSON": json.dumps(evidence, ensure_ascii=False).replace("<", "\\u003c"),
    }
    for path in (HERE / "assets").iterdir():
        replacements["ASSET_" + path.stem.upper().replace("-", "_")] = data_uri(path)
    def replace(match):
        key = match.group(1)
        assert key in replacements, f"Missing template value: {key}"
        return replacements[key]
    output = re.sub(r"@@([A-Z_]+)@@", replace, template)
    assert "@@" not in output
    target = HERE / "index.html"
    target.write_text(output)
    print(f"Built {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
