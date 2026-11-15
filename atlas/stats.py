"""Trend statistics, vectorised over many pixels.

Methods (all standard; references in docs/METHODS.md):
* Deseasonalised series: subtract each calendar month's mean over the
  analysed period (removes the annual cycle without changing the trend).
* Ordinary least squares slope with an AR(1) effective-sample-size
  correction of the standard error (Santer et al. 2000, J. Geophys. Res.).
* Seasonal Mann–Kendall test with seasonal Sen slope (Hirsch et al. 1982)
  as a rank-based cross-check that does not assume a straight line or
  normally distributed noise.
* Benjamini–Hochberg false discovery rate across map pixels (Wilks 2016,
  BAMS), so a map of many tests does not light up by chance.
"""
from __future__ import annotations

import numpy as np
from scipy import stats as st

MIN_FRACTION = 0.7  # minimum fraction of valid samples for a trend estimate


# ---------------------------------------------------------------- helpers
def decimal_years(times) -> np.ndarray:
    t = np.asarray(times, dtype="datetime64[M]")
    years = t.astype("datetime64[Y]").astype(int) + 1970
    months = t.astype(int) % 12
    return years + (months + 0.5) / 12.0


def month_of(times) -> np.ndarray:
    return np.asarray(times, dtype="datetime64[M]").astype(int) % 12


def deseasonalise(Y: np.ndarray, months: np.ndarray) -> np.ndarray:
    """Y (T, N) -> anomalies relative to each calendar month's mean."""
    A = np.full_like(Y, np.nan, dtype="float64")
    for m in np.unique(months):
        sel = months == m
        with np.errstate(invalid="ignore"), _quiet():
            clim = np.nanmean(Y[sel], axis=0)
        A[sel] = Y[sel] - clim
    return A


class _quiet:
    def __enter__(self):
        import warnings
        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def __exit__(self, *a):
        self._w.__exit__(*a)


# ---------------------------------------------------------------- OLS + AR(1)
def ols_trend(t: np.ndarray, Y: np.ndarray, alpha: float = 0.05) -> dict:
    """OLS slope per column of Y (T, N) with NaNs; slope units = Y units per unit of t.

    Returns dict of arrays (N,): slope, intercept, se, se_adj, ci_low, ci_high,
    p, n, n_eff, r1.
    """
    Y = np.asarray(Y, "float64")
    if Y.ndim == 1:
        Y = Y[:, None]
    t = np.asarray(t, "float64")[:, None]
    V = np.isfinite(Y)
    n = V.sum(0).astype("float64")
    T = np.where(V, t, 0.0)
    Yz = np.where(V, Y, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        tm = T.sum(0) / n
        ym = Yz.sum(0) / n
        dt = np.where(V, t - tm, 0.0)
        dy = np.where(V, Y - ym, 0.0)
        sxx = (dt * dt).sum(0)
        slope = (dt * dy).sum(0) / sxx
        intercept = ym - slope * tm
        res = np.where(V, Y - (intercept + slope * t), np.nan)
        s2 = np.nansum(res ** 2, 0) / (n - 2)
        se = np.sqrt(s2 / sxx)
        # lag-1 autocorrelation of residuals (pairs where both are valid)
        r0 = res[:-1]
        r1_ = res[1:]
        pv = np.isfinite(r0) & np.isfinite(r1_)
        num = np.where(pv, r0 * r1_, 0).sum(0)
        den = np.nansum(res ** 2, 0)
        r1 = np.clip(num / den * n / np.maximum(pv.sum(0), 1), -0.99, 0.99)
        r1p = np.maximum(r1, 0.0)  # negative autocorrelation: no inflation
        n_eff = np.clip(n * (1 - r1p) / (1 + r1p), 3.0, n)
        se_adj = se * np.sqrt((n - 2) / (n_eff - 2))
        df = n_eff - 2
        tstat = slope / se_adj
        p = 2 * st.t.sf(np.abs(tstat), df)
        tc = st.t.ppf(1 - alpha / 2, df)
    return dict(slope=slope, intercept=intercept, se=se, se_adj=se_adj,
                ci_low=slope - tc * se_adj, ci_high=slope + tc * se_adj,
                p=p, n=n, n_eff=n_eff, r1=r1)


# ---------------------------------------------------------------- Mann–Kendall
def seasonal_mann_kendall(years: np.ndarray, months: np.ndarray, Y: np.ndarray,
                          chunk: int = 4096) -> dict:
    """Seasonal Mann–Kendall test and seasonal Sen slope (per year) for Y (T, N).

    Ties are rare for continuous data and are ignored in the variance.
    """
    Y = np.asarray(Y, "float64")
    if Y.ndim == 1:
        Y = Y[:, None]
    N = Y.shape[1]
    S = np.zeros(N)
    VarS = np.zeros(N)
    slopes_all = []
    for m in np.unique(months):
        sel = np.where(months == m)[0]
        yrs = years[sel].astype("float64")
        X = Y[sel]                       # (n_m, N)
        i, j = np.triu_indices(len(sel), 1)
        dyears = yrs[j] - yrs[i]
        n_m = np.isfinite(X).sum(0).astype("float64")
        VarS += n_m * (n_m - 1) * (2 * n_m + 5) / 18.0
        for c0 in range(0, N, chunk):
            D = X[j, c0:c0 + chunk] - X[i, c0:c0 + chunk]   # (pairs, chunk)
            S[c0:c0 + chunk] += np.nansum(np.sign(D), 0)
        slopes_all.append((X, i, j, dyears))
    with np.errstate(invalid="ignore", divide="ignore"):
        Z = np.where(S > 0, (S - 1), np.where(S < 0, S + 1, 0.0)) / np.sqrt(VarS)
        p = 2 * st.norm.sf(np.abs(Z))
    sen = np.full(N, np.nan)
    for c0 in range(0, N, chunk):
        parts = [(X[j, c0:c0 + chunk] - X[i, c0:c0 + chunk]) / dy[:, None]
                 for X, i, j, dy in slopes_all]
        with _quiet():
            sen[c0:c0 + chunk] = np.nanmedian(np.concatenate(parts, 0), 0)
    return dict(S=S, Z=Z, p=p, sen_slope=sen)


# ---------------------------------------------------------------- FDR
def bh_fdr(p: np.ndarray, q: float = 0.10) -> tuple[np.ndarray, float]:
    """Benjamini–Hochberg. Returns (significant mask, p threshold). NaNs never significant."""
    p = np.asarray(p, "float64")
    flat = p.ravel()
    ok = np.isfinite(flat)
    pv = np.sort(flat[ok])
    m = pv.size
    sig = np.zeros(flat.shape, bool)
    if m == 0:
        return sig.reshape(p.shape), 0.0
    crit = q * np.arange(1, m + 1) / m
    below = np.nonzero(pv <= crit)[0]
    thr = float(pv[below[-1]]) if below.size else 0.0
    sig[ok] = flat[ok] <= thr if below.size else False
    return sig.reshape(p.shape), thr


# ---------------------------------------------------------------- regional mean
def area_mean(A: np.ndarray, lat: np.ndarray, min_cover: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """cos(lat)-weighted mean over the spatial axes of A (T, ny, nx); returns (mean, coverage)."""
    w = np.cos(np.radians(lat))[None, :, None] * np.ones_like(A[:1])
    V = np.isfinite(A)
    wsum = (w * V).sum((1, 2))
    tot = w.sum()
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(V, A * w, 0).sum((1, 2)) / wsum
    cover = wsum / tot
    m[cover < min_cover] = np.nan
    return m, cover


# ---------------------------------------------------------------- analysis bundles
def analyse_series(times, y, alpha=0.05, per=10.0) -> dict:
    """Full analysis of one monthly series (already restricted to chosen months)."""
    t = decimal_years(times)
    mo = month_of(times)
    yrs = np.floor(t).astype(int)
    a = deseasonalise(np.asarray(y, "float64")[:, None], mo)[:, 0]
    frac = float(np.isfinite(a).mean()) if a.size else 0.0
    o = ols_trend(t, a, alpha)
    mk = seasonal_mann_kendall(yrs, mo, a[:, None])
    g = lambda d, k: float(d[k][0])  # noqa: E731
    return dict(
        anomaly=a, t=t, valid_fraction=frac,
        n_years=int(np.unique(yrs[np.isfinite(a)]).size),
        slope=g(o, "slope") * per, ci_low=g(o, "ci_low") * per, ci_high=g(o, "ci_high") * per,
        p=g(o, "p"), n=int(o["n"][0]), n_eff=g(o, "n_eff"), r1=g(o, "r1"),
        intercept=g(o, "intercept"),
        mk_p=g(mk, "p"), mk_z=g(mk, "Z"), sen_slope=g(mk, "sen_slope") * per,
    )


def window_matrix(times, y, min_len: int = 15, alpha=0.05, per=10.0) -> dict:
    """Trend for every (start year, end year) window of at least min_len years."""
    t = decimal_years(times)
    yrs = np.floor(t).astype(int)
    mo = month_of(times)
    y = np.asarray(y, "float64")
    y0, y1 = int(yrs.min()), int(yrs.max())
    step = max(1, int(np.ceil((y1 - y0 + 2 - min_len) / 20)))  # keep the matrix readable (≤ ~20×20)
    starts = list(range(y0, y1 - min_len + 2, step))
    ends = sorted(range(y1, y0 + min_len - 2, -step))
    cells = []
    for s in starts:
        for e in ends:
            if e - s + 1 < min_len:
                continue
            sel = (yrs >= s) & (yrs <= e)
            a = deseasonalise(y[sel][:, None], mo[sel])[:, 0]
            if np.isfinite(a).mean() < MIN_FRACTION:
                cells.append(dict(start=s, end=e, slope=None, p=None, ci_low=None, ci_high=None))
                continue
            o = ols_trend(t[sel], a, alpha)
            cells.append(dict(start=s, end=e, slope=float(o["slope"][0]) * per, p=float(o["p"][0]),
                              ci_low=float(o["ci_low"][0]) * per, ci_high=float(o["ci_high"][0]) * per))
    return dict(starts=starts, ends=ends, min_len=min_len, step=step, cells=cells)


def verdict(res: dict, matrix: dict | None, alpha=0.05) -> dict:
    """Plain-language verdict. Never claims causes, never claims 'no change'."""
    if res["valid_fraction"] < MIN_FRACTION or res.get("n_years", 99) < 8:
        return dict(code="insufficient_data", title="Not enough data",
                    text="Too many gaps or too few years. Try a longer period or a bigger area.")
    sig = res["p"] < alpha and (res["ci_low"] > 0 or res["ci_high"] < 0)
    agree = res["mk_p"] < alpha and np.sign(res["sen_slope"]) == np.sign(res["slope"])
    robust = None
    if matrix:
        vals = [c for c in matrix["cells"] if c["slope"] is not None]
        if vals:
            same = sum(1 for c in vals if np.sign(c["slope"]) == np.sign(res["slope"]))
            sigsame = sum(1 for c in vals if np.sign(c["slope"]) == np.sign(res["slope"]) and c["p"] < alpha)
            robust = dict(windows=len(vals), same_sign=same, same_sign_significant=sigsame)
    if not sig:
        return dict(code="ci_includes_zero", title="No clear trend",
                    text="The range of likely slopes includes zero. That is not proof of no change.",
                    methods_agree=bool(res["mk_p"] >= alpha), robustness=robust)
    if robust and robust["same_sign"] < 0.8 * robust["windows"]:
        return dict(code="depends_on_period", title="Depends on the period",
                    text="Significant here, but many other start/end years disagree. Be careful.",
                    methods_agree=bool(agree), robustness=robust)
    return dict(code="trend_detected", title="Trend detected",
                text=("Significant at 5%, corrected for autocorrelation."
                      + (" Mann–Kendall agrees." if agree else " Mann–Kendall does not confirm it – check outliers.")),
                methods_agree=bool(agree), robustness=robust)
