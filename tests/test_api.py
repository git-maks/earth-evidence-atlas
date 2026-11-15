"""API smoke tests on the built data cubes."""
import pytest
from fastapi.testclient import TestClient

from atlas.api import app
from atlas.config import VARIABLES, cube_path

c = TestClient(app)
BUILT = [(v, r) for v in VARIABLES for r in VARIABLES[v].regions if cube_path(v, r).exists()]


def test_catalog():
    j = c.get("/api/catalog").json()
    assert {v["id"] for v in j["variables"]} == set(VARIABLES)


@pytest.mark.parametrize("var,region", BUILT)
def test_analysis_and_map(var, region):
    a = c.get("/api/analysis", params=dict(var=var, region=region))
    assert a.status_code == 200, a.text
    j = a.json()
    assert j["result"]["ci_low"] <= j["result"]["slope"] <= j["result"]["ci_high"]
    assert j["verdict"]["code"] in {"trend_detected", "ci_includes_zero", "depends_on_period",
                                    "significance_depends_on_period", "insufficient_data"}
    m = c.get("/api/map", params=dict(var=var, region=region)).json()
    assert m["summary"]["significant_fdr"] <= m["summary"]["cells_with_trend"]


def test_season_subset_and_bbox():
    if not cube_path("lst_day", "central_europe").exists():
        pytest.skip("cube not built")
    j = c.get("/api/analysis", params=dict(var="lst_day", region="central_europe", months="6,7,8",
                                           start=2005, end=2020, bbox="19,49.5,20.5,50.5")).json()
    assert j["months"] == [6, 7, 8] and j["start"] == 2005 and j["cells"] > 0
    assert len(j["series"]["dates"]) == 16 * 3


def test_bad_input():
    assert c.get("/api/analysis", params=dict(var="nope", region="world")).status_code == 404
    assert c.get("/api/analysis", params=dict(var="t2m", region="central_europe", months="13")).status_code == 400


def test_exports():
    if not cube_path("t2m", "central_europe").exists():
        pytest.skip("cube not built")
    r = c.get("/api/export.csv", params=dict(var="t2m", region="central_europe"))
    assert r.status_code == 200 and r.text.startswith("# Earth Evidence Atlas export")
    assert c.get("/api/export.json", params=dict(var="t2m", region="central_europe")).json()["provenance"]["citation"]


def test_simulation_is_labelled():
    assert "SIMULATION" in c.get("/api/simulate").json()["label"]
    assert "SIMULATION" in c.get("/api/simulate_many", params=dict(runs=50)).json()["label"]


def test_level_shift_example_and_batch_intervals():
    params = dict(seed=11, years=10, phi=0.25, sigma=0.35)
    step = c.get("/api/simulate", params={**params, "scenario": "step"}).json()
    noise = c.get("/api/simulate", params=params).json()
    before, after = step["segments"]
    assert step["change_date"] == after["dates"][0] == "2006-01"
    assert before["dates"] + after["dates"] == step["dates"]
    assert step["values"][:60] == noise["values"][:60]
    assert step["values"][60:] == pytest.approx([v + 1.75 for v in noise["values"][60:]], abs=1e-6)
    assert step["corrected_p"] < 0.05
    assert all(segment["ci_low"] < 0 < segment["ci_high"] for segment in step["segments"])

    batch = c.get("/api/simulate_many", params=dict(runs=200, years=10, phi=0.7)).json()
    for method in ("naive", "corrected"):
        low, high = batch[f"{method}_interval"]
        assert 0 <= low < batch[f"{method}_significant"] / 200 < high <= 1


@pytest.mark.skipif(not cube_path("precip", "amazon_arc").exists(), reason="Amazon rainfall cube not built")
def test_amazon_rainfall_distinguishes_significance_from_confirmation():
    result = c.get("/api/analysis", params=dict(var="precip", region="amazon_arc")).json()
    assert result["verdict"]["code"] == "trend_detected"
    assert result["result"]["slope"] < 0
    # the headline now reports what the independent GPCP record (satellites + gauges) says for the same area
    assert result["cross_check"]["variable"] == "precip_gpcp"
    assert result["answer"]["headline"] in {"Less rainfall in both MERRA-2 and GPCP.",
                                            "Less rainfall in MERRA-2 and GPCP, by different amounts.",
                                            "MERRA-2 and GPCP point the same way, but only one is significant."}
    assert result["answer"]["source_url"] == "https://doi.org/10.1175/JCLI-D-16-0570.1"


def test_independent_dataset_check_and_validation():
    """Results come with an independent dataset for the same area and years (stations vs reanalysis,
    satellites + gauges vs reanalysis); the Methods page gets live validation rows."""
    if not (cube_path("t2m", "central_europe").exists() and cube_path("gistemp", "central_europe").exists()):
        pytest.skip("cubes not built")
    j = c.get("/api/analysis", params=dict(var="t2m", region="central_europe")).json()
    cc = j["cross_check"]
    assert cc["variable"] == "gistemp" and cc["start"] >= 1981
    assert cc["agreement"] in {"agree", "same_direction_different_size", "one_significant", "neither_significant",
                               "disagree", "unclear"}
    assert any(line.startswith("Independent check with NASA GISTEMP") for line in j["answer"]["lines"])
    v = c.get("/api/validation").json()
    assert v["cross_checks"] and {"agreement", "difference_p"} <= set(v["cross_checks"][0])
    assert v["calibration"]["target"] == 0.05


def test_gpcp_precipitation_is_available_for_any_area():
    if not cube_path("precip_gpcp", "world").exists():
        pytest.skip("GPCP not built")
    j = c.get("/api/analysis", params=dict(var="precip_gpcp", region="world", bbox="14,49,24,55")).json()
    assert j["start"] == 1988 and j["result"]["slope"] is not None


def test_agreement_categories():
    from atlas.api import _agreement
    r = lambda s, p: dict(slope=s, p=p)  # noqa: E731
    assert _agreement(r(0.5, 0.01), r(0.4, 0.01), 0.6) == "agree"
    assert _agreement(r(0.5, 0.01), r(0.2, 0.01), 0.01) == "same_direction_different_size"
    assert _agreement(r(0.5, 0.01), r(0.2, 0.3), 0.2) == "one_significant"
    assert _agreement(r(-0.1, 0.6), r(0.3, 0.001), 0.001) == "disagree"
    assert _agreement(r(-0.1, 0.6), r(0.1, 0.7), 0.5) == "unclear"
