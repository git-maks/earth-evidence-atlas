import math
from types import SimpleNamespace

import pytest

from atlas import api
from atlas.sources import power


@pytest.mark.parametrize("bbox, expected_lat, expected_lon", [
    ((10.3, 44.6, 13.1, 45.9), [45.0, 45.5], [10.5, 11, 11.5, 12, 12.5, 13]),
    ((44.6, 10.3, 45.9, 13.1), [10.5, 11, 11.5, 12, 12.5, 13], [45.0, 45.5]),
    ((10.3, 44.6, 13.1, 44.7), [44.5], [10.5, 11, 11.5, 12, 12.5, 13]),
    ((179.6, 88.6, 179.9, 89.0), [89.0], [179.5]),
])
def test_power_pads_download_and_keeps_selected_grid(monkeypatch, bbox, expected_lat, expected_lon):
    def monthly_data(client, params):
        s, n = params["latitude-min"], params["latitude-max"]
        w, e = params["longitude-min"], params["longitude-max"]
        assert -90 <= s <= bbox[1] < bbox[3] <= n <= 90
        assert -180 <= w <= bbox[0] < bbox[2] <= e <= 180
        assert 2 <= n - s <= 10 and 2 <= e - w <= 10
        return {"features": [
            {"geometry": {"coordinates": [lon / 2, lat / 2]},
             "properties": {"parameter": {"T2M": {"198101": 10}}}}
            for lat in range(math.ceil(s * 2), math.floor(n * 2) + 1)
            for lon in range(math.ceil(w * 2), math.floor(e * 2) + 1)
        ]}

    monkeypatch.setattr(power, "get_region", lambda _: SimpleNamespace(bbox=bbox))
    monkeypatch.setattr(power, "_get", monthly_data)
    monkeypatch.setattr(power, "write_cube", lambda var, region, values, times, lat, lon, **attrs: (lat, lon))
    assert power.fetch("t2m", "test", log=lambda _: None) == (expected_lat, expected_lon)


def test_download_failure_keeps_upstream_error_in_server_log(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise RuntimeError("upstream response with technical details")

    monkeypatch.setattr(power, "fetch", fail)
    monkeypatch.setitem(api.JOBS, "test", dict(var="t2m", region="test", started=0))
    api._run_job("test")
    job = api.job_status("test")
    assert job["status"] == "error"
    assert job["message"] == "Could not download data for this area. Try again or select another area."
    assert "upstream response with technical details" in caplog.text
