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
    """AR(1) noise without trend: naive OLS over-rejects, the corrected test stays near 5%."""
    rng = np.random.default_rng(2)
    t = S.decimal_years(TIMES)
    for phi in (0.3, 0.6, 0.9):
        Y = ar1(rng, t.size, phi, 1.0, 1500)
        o = S.trend_test(t, Y)
        naive = (2 * st.t.sf(np.abs(o["slope"] / o["se"]), o["n"] - 2) < 0.05).mean()
        assert naive > 0.1, phi
        assert (o["p"] < 0.05).mean() < 0.07, phi
        assert (o["p_month"] < 0.05).mean() < 0.08, phi   # each scale is calibrated on its own


def test_seasons_and_gaps_keep_the_false_alarm_rate():
    """Summer-only months and 20% random gaps: memory is estimated from pairs really one month apart."""
    rng = np.random.default_rng(5)
    keep = np.isin(S.month_of(TIMES), [5, 6, 7])          # Jun–Aug
    t = S.decimal_years(TIMES)[keep]
    Y = ar1(rng, TIMES.size, 0.7, 1.0, 1500)[keep]
    Y[rng.random(Y.shape) < 0.2] = np.nan
    o = S.trend_test(t, Y)
    assert (o["p"] < 0.05).mean() < 0.07


def test_slow_variability_is_caught_by_the_yearly_scale():
    """Fast AR(1) plus a slow decade-scale component: a month-to-month correction alone is fooled
    often; the yearly scale removes most of these false alarms (the residual is a known limit)."""
    rng = np.random.default_rng(6)
    t = S.decimal_years(TIMES)
    fast = ar1(rng, t.size, 0.5, np.sqrt(1 - 0.5 ** 2), 1500)
    slow = ar1(rng, t.size, 0.97, np.sqrt(1 - 0.97 ** 2), 1500)
    Y = np.sqrt(0.8) * fast + np.sqrt(0.2) * slow
    o = S.trend_test(t, Y)
    month_only, both = (o["p_month"] < 0.05).mean(), (o["p"] < 0.05).mean()
    assert month_only > 0.2 and both < 0.16 and both < month_only / 2


def test_variance_inflation_matches_ar1_theory_and_bias_correction():
    """Complete monthly series: exact inflation -> (1 + rho)/(1 - rho); bias-corrected rho is unbiased."""
    t = S.decimal_years(pd.date_range("1981-01-01", "2025-12-01", freq="MS").values)
    w = (t - t.mean()) / ((t - t.mean()) ** 2).sum()
    v = S._slope_variance_inflation(S.month_index(t), w[:, None], np.array([0.6]))[0]
    assert abs(v / (1.6 / 0.4) - 1) < 0.02
    rng = np.random.default_rng(7)
    o = S.ols_trend(S.decimal_years(TIMES), ar1(rng, TIMES.size, 0.6, 1.0, 2000))
    assert abs(o["rho"].mean() - 0.6) < 0.015 and o["r1"].mean() < o["rho"].mean()


def test_seasonal_mk_null_rate():
    """Without the dependence correction the seasonal Mann–Kendall test called ~39% of trendless AR(1)
    series (phi = 0.7) significant. Both corrected scales must stay near 5% with and without memory."""
    rng = np.random.default_rng(3)
    t = S.decimal_years(TIMES)
    white = S.seasonal_mann_kendall(np.floor(t).astype(int), S.month_of(TIMES), rng.normal(0, 1, (t.size, 600)))
    assert 0.02 < (white["p"] < 0.05).mean() < 0.08
    for phi in (0.3, 0.7, 0.9):
        mk = S.mann_kendall_test(t, ar1(rng, t.size, phi, 1.0, 600))
        assert (mk["p"] < 0.05).mean() < 0.08, phi


def test_mk_detects_a_real_trend():
    rng = np.random.default_rng(8)
    t = S.decimal_years(TIMES)
    Y = ar1(rng, t.size, 0.3, 1.0, 200) + 0.08 * (t - t.mean())[:, None]
    assert (S.mann_kendall_test(t, Y)["p"] < 0.05).mean() > 0.9


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
    # same direction everywhere but rarely significant -> the verdict says so instead of "trend detected"
    weak = dict(mx, cells=[dict(c, p=0.5) for c in mx["cells"]])
    assert S.verdict(r, weak)["code"] == "significance_depends_on_period"
    assert S.verdict(dict(r, n_years=12), mx)["short_record"] is True


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


def test_inflation_filter_and_recursion_paths_agree():
    """The per-column linear-filter path (single series) and the vectorised recursion (maps) are identical."""
    rng = np.random.default_rng(9)
    keep = np.isin(S.month_of(TIMES), [11, 0, 1])          # Dec–Feb: irregular sampling steps
    k = S.month_index(S.decimal_years(TIMES)[keep])
    W = rng.normal(size=(k.size, 70))
    W[rng.random(W.shape) < 0.2] = 0.0
    rho = rng.uniform(0, 0.95, 70)
    many = S._slope_variance_inflation(k, W, rho)
    one = np.array([S._slope_variance_inflation(k, W[:, [c]], rho[[c]])[0] for c in range(70)])
    assert np.allclose(many, one, rtol=1e-12)


def test_modis_quality_rules():
    """MOD13A1 pixel reliability and MOD11A2 QC_Day bit rules (product user guides)."""
    from atlas.sources.modis_pc import _lst_ok, _ndvi_ok
    assert _ndvi_ok(np.array([0, 1, 2, 3, 255], np.uint8)).tolist() == [True, True, False, False, False]
    # 0 good; 17/65/81: other quality with LST error <= 2 K; 129/145: error <= 3 K; 2/3: not produced
    codes = np.array([0, 17, 65, 81, 129, 145, 2, 3], np.uint8)
    assert _lst_ok(codes).tolist() == [True, True, True, True, False, False, False, False]
