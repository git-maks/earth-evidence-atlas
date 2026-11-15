"""Validation of the statistics engine on synthetic data."""
import numpy as np
import pandas as pd
from scipy import stats as st

from atlas import stats as S

TIMES = pd.date_range("2001-01-01", "2024-12-01", freq="MS").values


def ar1(rng, n, phi, sigma, k=1):
    e = rng.normal(0, sigma, (n, k))
    x = np.zeros((n, k))
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def test_ols_matches_scipy():
    rng = np.random.default_rng(0)
    t = S.decimal_years(TIMES)
    y = 0.03 * t + rng.normal(0, 1, t.size)
    o = S.ols_trend(t, y)
    ref = st.linregress(t, y)
    assert np.isclose(o["slope"][0], ref.slope)
    assert np.isclose(o["se"][0], ref.stderr)


def test_recovers_known_slope_with_seasonality_and_gaps():
    rng = np.random.default_rng(1)
    t = S.decimal_years(TIMES)
    m = S.month_of(TIMES)
    y = 10 * np.sin(2 * np.pi * m / 12) + 0.05 * (t - 2001) + rng.normal(0, 0.2, t.size)
    y[rng.random(t.size) < 0.1] = np.nan
    r = S.analyse_series(TIMES, y)
    assert abs(r["slope"] - 0.5) < 0.05          # per decade
    assert r["ci_low"] < 0.5 < r["ci_high"]
    assert r["p"] < 1e-6 and r["mk_p"] < 1e-6
    assert abs(r["sen_slope"] - 0.5) < 0.05


def test_false_positive_rate_under_autocorrelation():
    """AR(1) noise without trend: naive OLS over-rejects, corrected test should be near 5%."""
    rng = np.random.default_rng(2)
    t = S.decimal_years(TIMES)
    Y = ar1(rng, t.size, 0.6, 1.0, 2000)
    o = S.ols_trend(t, Y)
    rate = (o["p"] < 0.05).mean()
    naive = (2 * st.t.sf(np.abs(o["slope"] / o["se"]), o["n"] - 2) < 0.05).mean()
    assert naive > 0.15
    assert rate < 0.09


def test_seasonal_mk_null_rate():
    rng = np.random.default_rng(3)
    t = S.decimal_years(TIMES)
    Y = rng.normal(0, 1, (t.size, 1000))
    mk = S.seasonal_mann_kendall(np.floor(t).astype(int), S.month_of(TIMES), Y)
    assert 0.02 < (mk["p"] < 0.05).mean() < 0.08


def test_bh_fdr():
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, np.nan])
    sig, thr = S.bh_fdr(p, q=0.05)
    assert sig.tolist() == [True, True, False, False, False, False, False, False, False]
    assert thr == 0.008


def test_area_mean_weights_and_coverage():
    A = np.ones((2, 2, 3))
    A[1] = np.nan
    m, c = S.area_mean(A, np.array([0.0, 60.0]))
    assert m[0] == 1 and np.isnan(m[1]) and c[0] == 1


def test_window_matrix_and_verdict():
    rng = np.random.default_rng(4)
    t = S.decimal_years(TIMES)
    y = 0.08 * (t - 2001) + rng.normal(0, 0.3, t.size)
    r = S.analyse_series(TIMES, y)
    mx = S.window_matrix(TIMES, y, min_len=15)
    assert len([c for c in mx["cells"]]) == 55
    v = S.verdict(r, mx)
    assert v["code"] == "trend_detected"
    flat = rng.normal(0, 1, t.size)
    v2 = S.verdict(S.analyse_series(TIMES, flat), None)
    assert v2["code"] in ("ci_includes_zero", "trend_detected")


def test_prune_custom_regions(tmp_path, monkeypatch):
    """Old or surplus user-made areas are removed with their files; nothing else is touched."""
    import json
    import time
    from atlas import config
    monkeypatch.setattr(config, "CUSTOM_FILE", tmp_path / "custom.json")
    monkeypatch.setattr(config, "CUBE_DIR", tmp_path / "cubes")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    (tmp_path / "cubes").mkdir()
    now = time.time()
    raw = {"c_old": {"name": "old", "bbox": [0, 0, 1, 1], "used": now - 10 * 86400},
           "c_new": {"name": "new", "bbox": [1, 1, 2, 2], "used": now},
           "c_mid": {"name": "mid", "bbox": [2, 2, 3, 3], "used": now - 86400}}
    config.CUSTOM_FILE.write_text(json.dumps(raw))
    for k in raw:
        (tmp_path / "cubes" / f"ndvi__{k}.nc").write_text("x")
    (tmp_path / "cubes" / "ndvi__central_europe.nc").write_text("x")
    dropped = config.prune_custom_regions(max_age_days=7, max_count=1)
    assert sorted(dropped) == ["c_mid", "c_old"]
    assert list(json.loads(config.CUSTOM_FILE.read_text())) == ["c_new"]
    assert sorted(p.name for p in (tmp_path / "cubes").iterdir()) == ["ndvi__c_new.nc", "ndvi__central_europe.nc"]
