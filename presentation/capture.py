"""Freeze read-only API responses and their source hashes for the presentation.

Run against a freshly started private test server. No data downloads or cube
rebuilds are requested. Rebuild the HTML only after refreshing the figures too.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SOURCES = (
    "atlas/stats.py", "atlas/answers.py", "atlas/api.py", "atlas/config.py",
    "atlas/sources/modis_pc.py", "atlas/sources/gpcp.py", "web/app.js",
    "web/globe.js", "web/globe-similarity.js", "web/index.html",
    "web/resilience.js", "web/resilience.css", "atlas/sources/power.py", "atlas/sources/gistemp.py",
)
CASES = {
    "air_europe": {"var": "t2m", "region": "central_europe"},
    "world": {"var": "gistemp", "region": "world"},
    "ndvi_annual": {"var": "ndvi", "region": "central_europe"},
    "ndvi_summer": {"var": "ndvi", "region": "central_europe", "months": "6,7,8"},
    "surface_amazon": {"var": "lst_day", "region": "amazon_arc"},
    "surface_india": {"var": "lst_day", "region": "nw_india"},
    "terra_europe": {"var": "lst_day", "region": "central_europe", "start": 2003, "end": 2024},
    "aqua_europe": {"var": "lst_day_aqua", "region": "central_europe", "start": 2003, "end": 2024},
    "ndvi_india": {"var": "ndvi", "region": "nw_india"},
    "soil_europe": {"var": "soil_root", "region": "central_europe"},
    "rain_europe": {"var": "precip", "region": "central_europe"},
    "rain_amazon": {"var": "precip", "region": "amazon_arc"},
    "gpcp_amazon": {"var": "precip_gpcp", "region": "amazon_arc"},
}


def hashes(project_root):
    return {name: hashlib.sha256((project_root / name).read_bytes()).hexdigest() for name in SOURCES}


def get(base, endpoint, params=None):
    with urlopen(base + endpoint + ("?" + urlencode(params) if params else ""), timeout=180) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8776")
    parser.add_argument("--project-root", type=Path, required=True,
                        help="Separate application checkout matching the running test API.")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    before = hashes(project_root)
    result = {
        "captured_at": datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="seconds"),
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project_root, text=True).strip(),
        "source_sha256": before,
        "api_base_url": args.base_url,
        "capture_note": "Actual local API responses and the current client outlier function; frozen evidence. "
                        "No downloads or cube rebuilds. Git revision plus source hashes identify the captured worktree.",
        "catalog": get(args.base_url, "/api/catalog"),
    }

    def analysis(item):
        key, params = item
        return key, {"endpoint": "/api/analysis", "params": params,
                     "response": get(args.base_url, "/api/analysis", params)}

    with ThreadPoolExecutor(max_workers=3) as pool:
        result["analyses"] = dict(pool.map(analysis, CASES.items()))
    result["validation"] = get(args.base_url, "/api/validation")
    batch = dict(runs=200, years=10, phi=0.7, seed=1000)
    result["simulation_batch"] = dict(endpoint="/api/simulate_many", params=batch,
                                       response=get(args.base_url, "/api/simulate_many", batch))
    app_source = (project_root / "web/app.js").read_text()
    seed = int(re.search(r"spikeSeed = (\d+)", app_source)[1])
    years = int(re.search(r"seed: spikeSeed, years: (\d+)", app_source)[1])
    params = dict(seed=seed, years=years, phi=0.25, sigma=0.35)
    original = get(args.base_url, "/api/simulate", params)
    function = re.search(r"function addSpikes\(s\) \{[\s\S]*?\n\}", app_source)[0]
    script = function + "\nprocess.stdout.write(JSON.stringify(addSpikes(JSON.parse(require('fs').readFileSync(0,'utf8')))));"
    spikes = subprocess.run(["node", "-e", script], input=json.dumps(original), capture_output=True,
                            text=True, check=True, timeout=30)
    result["simulation_spikes"] = dict(endpoint="/api/simulate plus current client addSpikes()", params=params,
        response=json.loads(spikes.stdout), frontend_sha256=before["web/app.js"], captured_at=result["captured_at"])
    result["resilience_check"] = {"endpoint": "/api/resilience", "params": {"region": "central_europe"},
                                  "response": get(args.base_url, "/api/resilience", {"region": "central_europe"})}
    if hashes(project_root) != before:
        raise RuntimeError("Source changed during capture. Restart the test server and capture again.")
    (HERE / "evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Captured {len(result['analyses'])} analyses, validation, simulations and Resilience.")
    for key in ("air_europe", "ndvi_annual", "ndvi_summer", "rain_amazon"):
        a = result["analyses"][key]["response"]
        print(key, a["result"]["slope"], a["result"]["ci_low"], a["result"]["ci_high"],
              a["result"]["p"], a["verdict"]["code"])
    print("Batch:", result["simulation_batch"]["response"])


if __name__ == "__main__":
    main()
