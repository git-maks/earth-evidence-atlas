"""Build a standalone, offline HTML pitch from recorded application evidence and figures."""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def data_uri(path: Path) -> str:
    mime = {".png": "image/png", ".svg": "image/svg+xml", ".ttf": "font/ttf"}[path.suffix]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def number(value, digits=3, signed=False):
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


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
    rows = []
    for variable in catalog["variables"]:
        rows.append(f'<tr><td><strong>{html.escape(variable["name"])}</strong><span>{html.escape(variable["product"])}</span></td>'
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
    resource_index = json.loads((ROOT / "formalne/materialy/odnosniki_resources.json").read_text())
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
    template = (HERE / "deck.template.html").read_text()
    replacements = {
        "FONT": data_uri(ROOT / "web/fonts/nasalization.ttf"),
        "ICON_SPRITE": (ROOT / "web/icons.svg").read_text().replace('<svg xmlns="http://www.w3.org/2000/svg">', '<svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true">', 1),
        "AIR_SLOPE": number(r["slope"], signed=True),
        "AIR_LOW": number(r["ci_low"]), "AIR_HIGH": number(r["ci_high"]),
        "AIR_SEN": number(r["sen_slope"], signed=True),
        "AIR_MONTHS": str(r["n"]), "AIR_EFFECTIVE": str(round(r["n_eff"])),
        "AIR_SAME": str(robustness["same_sign"]), "AIR_WINDOWS": str(robustness["windows"]),
        "AIR_SIGNIFICANT_WINDOWS": str(robustness["same_sign_significant"]),
        "NDVI_ANNUAL": number(annual["slope"], signed=True), "NDVI_ANNUAL_P": number(annual["p"], 4),
        "NDVI_SUMMER": number(summer["slope"], signed=True), "NDVI_SUMMER_P": number(summer["p"]),
        "NDVI_ANNUAL_LOW": number(annual["ci_low"]), "NDVI_ANNUAL_HIGH": number(annual["ci_high"]),
        "NDVI_SUMMER_LOW": number(summer["ci_low"]), "NDVI_SUMMER_HIGH": number(summer["ci_high"]),
        "NAIVE_PERCENT": number(100 * batch["naive_significant"] / batch["runs"], 1),
        "CORRECTED_PERCENT": number(100 * batch["corrected_significant"] / batch["runs"], 1),
        "NAIVE_COUNT": str(batch["naive_significant"]), "CORRECTED_COUNT": str(batch["corrected_significant"]),
        "RUNS": str(batch["runs"]),
        "SPIKE_WITH": number(spikes["slope"], signed=True),
        "SPIKE_WITHOUT": number(spikes["original"]["slope"], signed=True),
        "CAPTURED_LAB": html.escape(evidence["simulation_spikes"]["captured_at"][:19].replace("T", " ") + " Europe/Warsaw"),
        "DATASET_COUNT": str(len(catalog["variables"])),
        "DATASET_ROWS": "".join(rows), "SOURCE_CARDS": "".join(source_cards), "PROOF_ROWS": "".join(proof_rows),
        "RESOURCE_LINKS": resource_links,
        "CAPTURED": html.escape(evidence["captured_at"][:19].replace("T", " ") + " Europe/Warsaw"),
        "REVISION": html.escape(evidence["git_revision"][:8]),
        "ORIGINAL_BRIEF": html.escape((ROOT / "formalne/zrodla/opis_wyzwania.txt").read_text()),
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
    target = HERE / "earth-evidence-atlas.html"
    target.write_text(output)
    print(f"Built {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
