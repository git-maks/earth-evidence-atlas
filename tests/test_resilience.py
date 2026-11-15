"""Resilience should only assemble the published analysis of already available data."""
import csv
import io
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from atlas import api
from atlas.config import Region, cube_path

client = TestClient(api.app)


@pytest.mark.parametrize("area", [
    {"region": "central_europe"},
    {"bbox": "-62.123456789,-12.43,-56.07,-8.59"},
])
def test_brief_matches_detective(area):
    region = area.get("region", "amazon_arc")
    if not all(cube_path(var, region).exists() for var in (*api.RESILIENCE_VARIABLES, "precip_gpcp")):
        pytest.skip("regional cubes not built")
    params = dict(start=2004, end=2020, months="12,1,2")
    response = client.get("/api/resilience", params={**area, **params})
    assert response.status_code == 200, response.text
    brief = response.json()
    assert (brief["start"], brief["end"], brief["months"]) == (2004, 2020, [1, 2, 12])
    assert brief["methods"] == api.METHOD_NOTE
    assert [c["variable"] for c in brief["cards"]] == list(api.RESILIENCE_VARIABLES)
    for card in brief["cards"]:
        assert card["status"] == "ready"
        query = dict(params, var=card["variable"], region=card["data_region"])
        if "bbox" in area:
            assert card["analysis_bbox"] == brief["bbox"] == list(map(float, area["bbox"].split(",")))
            query["bbox"] = area["bbox"]
        detective = client.get("/api/analysis", params=query).json()
        for key in ("result", "verdict", "cross_check", "provenance", "trend_units", "cells"):
            assert card[key] == detective[key]
    precipitation = next(c for c in brief["cards"] if c["variable"] == "precip")
    assert precipitation["cross_check"]["variable"] == "precip_gpcp"
    assert precipitation["cross_check_source"]["resolution"]


def test_missing_data_and_exports_never_start_jobs(monkeypatch):
    enqueue = Mock(side_effect=AssertionError("Resilience attempted to start a job"))
    monkeypatch.setattr(api._EXEC, "submit", enqueue)
    register = Mock(side_effect=AssertionError("Resilience attempted to register an area"))
    monkeypatch.setattr(api, "add_custom_region", register)
    # Supply a deterministic read-only catalogue with just one covering cube.
    region = Region("c_fixture", "Stored area", (10, 40, 12, 42), "")
    monkeypatch.setattr(api, "custom_regions", lambda: {region.id: region})
    monkeypatch.setattr(api, "cube_path", lambda var, rid: Mock(exists=lambda: (var, rid) == ("t2m", region.id)))
    dataset = xr.Dataset(coords={"time": np.arange("2006-01", "2023-01", dtype="datetime64[M]")})
    monkeypatch.setattr(api, "load", lambda var, rid: dataset)
    analysis = Mock(return_value=dict(result={"slope": 0.0}, verdict={"code": "ci_includes_zero"},
                                      cross_check=None, provenance={"citation": "fixture"}, trend_units="°C per decade",
                                      cells=2, answer={}))
    monkeypatch.setattr(api, "_analysis", analysis)
    jobs = api.JOBS.copy()

    params = {"bbox": "10.1,40.1,11,41", "months": "6,7,8"}
    brief = client.get("/api/resilience", params=params).json()
    assert brief["years"] == [2006, 2022]
    assert brief["cards"][0]["result"]["slope"] == 0.0
    analysis.assert_called_once_with("t2m", region.id, 2006, 2022, (6, 7, 8), (10.1, 40.1, 11.0, 41.0), 15)
    assert all(c["status"] == "missing_cube" and c["result"] is None for c in brief["cards"][1:])
    json_export = client.get("/api/resilience", params={**params, "format": "json"})
    assert json_export.json() == brief
    assert "attachment" in json_export.headers["Content-Disposition"]
    csv_export = client.get("/api/resilience", params={**params, "format": "csv"})
    assert "attachment" in csv_export.headers["Content-Disposition"]
    lines = csv_export.text.splitlines()
    assert json.loads(next(line for line in lines if line.startswith("# limitations: ")).split(": ", 1)[1]) == brief["limitations"]
    rows = list(csv.DictReader(io.StringIO("\n".join(line for line in lines if not line.startswith("#")))))
    assert float(rows[0]["result.slope"]) == 0.0
    assert rows[1]["result.slope"] == ""

    empty = client.get("/api/resilience", params={"bbox": "-150,0,-149,1"}).json()
    assert empty["years"] is empty["start"] is empty["end"] is None
    assert all(c["result"] is None for c in empty["cards"])
    assert api.JOBS == jobs
    enqueue.assert_not_called()
    register.assert_not_called()


def test_unavailable_common_period_does_not_compute_incompatible_trends(monkeypatch):
    available = {("t2m", "central_europe"), ("lst_day", "central_europe")}
    monkeypatch.setattr(api, "cube_path", lambda var, rid: Mock(exists=lambda: (var, rid) in available))
    times = {"t2m": ("1981-01", "1999-01"), "lst_day": ("2001-01", "2025-01")}
    monkeypatch.setattr(api, "load", lambda var, rid: xr.Dataset(coords={
        "time": np.arange(*times[var], dtype="datetime64[M]"),
    }))
    analysis = Mock(side_effect=AssertionError("expected no common period"))
    monkeypatch.setattr(api, "_analysis", analysis)
    response = client.get("/api/resilience", params={"region": "central_europe"})
    assert response.status_code == 200
    brief = response.json()
    assert brief["years"] is None
    assert [c["status"] for c in brief["cards"]] == ["no_common_period"] * 2 + ["missing_cube"] * 2
    analysis.assert_not_called()


@pytest.mark.skipif(not shutil.which("node"), reason="Node is needed to exercise the frontend fallback")
def test_legacy_server_uses_existing_analyses_and_exports_the_report():
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(["node", "tests/test_resilience_legacy.js"], cwd=root,
                         capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stdout + run.stderr
