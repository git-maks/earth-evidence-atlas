"""API smoke tests on the built data cubes (AI-generated with Claude)."""
import pytest
from fastapi.testclient import TestClient

from atlas.api import app
from atlas.config import VARIABLES, cube_path

c = TestClient(app)
BUILT = [(v, r) for v in VARIABLES for r in VARIABLES[v].regions if cube_path(v, r).exists()]


def test_catalog():
    j = c.get("/api/catalog").json()
    assert {v["id"] for v in j["variables"]} == set(VARIABLES)
    assert "ai_disclosure" in j


@pytest.mark.parametrize("var,region", BUILT)
def test_analysis_and_map(var, region):
    a = c.get("/api/analysis", params=dict(var=var, region=region))
    assert a.status_code == 200, a.text
    j = a.json()
    assert j["result"]["ci_low"] <= j["result"]["slope"] <= j["result"]["ci_high"]
    assert j["verdict"]["code"] in {"trend_detected", "ci_includes_zero", "depends_on_period", "insufficient_data"}
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
