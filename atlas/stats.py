"""Trend statistics, vectorised over many pixels.

Methods (all standard; references in README "Metody statystyczne" and the Methods tab):
* Deseasonalised series: subtract each calendar month's mean over the
  analysed period (removes the annual cycle without changing the trend).
* Ordinary least squares slope of the anomalies.
* Significance and 95% interval from two memory corrections, combined as an
  intersection–union test (Berger 1982): a trend is called significant only if
  both agree.
  - Month to month: AR(1) noise with the lag correlation estimated only from
    pairs that are really one sampling step apart, corrected for its
    small-sample bias after detrending (E[r] ≈ rho − (2 + 4 rho)/n; Marriott &
    Pope 1954, checked by Monte Carlo), and an exact variance inflation of the
    OLS slope for the actual sampling pattern (seasons, gaps). For a complete
    monthly series this reduces to n_eff = n(1 − rho)/(1 + rho) (Santer et al.
    2000).
  - Year to year: the same test on season-year means, which captures slow
    variability that a month-to-month AR(1) misses.
* Rank-based cross-check: seasonal Mann–Kendall with the Hirsch & Slack (1984)
  covariance correction between seasons (with their missing-value form), and
  Mann–Kendall on season-year means with the Hamed & Rao (1998) variance
  correction; the larger p is reported. Seasonal Sen slope (Sen 1968; Hirsch et
  al. 1982).
* Benjamini–Hochberg false discovery rate across map pixels (Wilks 2016,
  BAMS), so a map of many tests does not light up by chance.

Calibration on synthetic series (tests/test_stats.py and the Monte Carlo study
described in README): false-alarm rate at most about 5% for AR(1) memory up to
0.9, with seasons and gaps; the old single-scale tests reached 7–8% (OLS) and
up to 65% (seasonal Mann–Kendall without the dependence correction).
"""
from __future__ import annotations

import numpy as np
from scipy import stats as st
from scipy.signal import lfilter

MIN_FRACTION = 0.7          # minimum fraction of valid samples for a trend estimate
YEAR_MIN_FRACTION = 0.5     # a season-year mean needs at least half of its expected months
DIRECTION_STABLE = 0.8      # share of other periods with the same sign for a "stable" direction
SIGNIFICANCE_STABLE = 0.5   # share of long other periods that are also significant
LONG_WINDOW_SHARE = 0.75    # "long" = at least this share of the analysed span
SHORT_RECORD_YEARS = 15     # below this, slow natural swings cannot be told apart from a trend


# ---------------------------------------------------------------- helpers
def decimal_years(times) -> np.ndarray:
    t = np.asarray(times, dtype="datetime64[M]")
    years = t.astype("datetime64[Y]").astype(int) + 1970
    months = t.astype(int) % 12
    return years + (months + 0.5) / 12.0


def month_of(times) -> np.ndarray:
    return np.asarray(times, dtype="datetime64[M]").astype(int) % 12


def month_index(t) -> np.ndarray:
    """Decimal years from decimal_years() -> integer month count (exact position on a monthly grid)."""
    return np.rint(np.asarray(t, "float64") * 12 - 0.5).astype(np.int64)


def season_years(k: np.ndarray) -> np.ndarray:
    """Season-year of each sample (k = month_index). December joins the following year when the
    selected months wrap the year end (e.g. Dec–Feb), so a winter is kept together."""
    mo = k % 12 + 1
    ms = np.unique(mo)
    wrap = 12 in ms and 1 in ms and ms.size < 12
    return k // 12 + ((mo == 12) & wrap)


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
def _lag_autocorrelation(res: np.ndarray, k: np.ndarray) -> tuple[np.ndarray, int, np.ndarray]:
    """Autocorrelation of residual columns at the smallest sampling step L (1 month for consecutive
    months, 12 for yearly means), using only pairs exactly L months apart. Returns (r_L, L, pairs)."""
    d = np.diff(k)
    steps = d[d > 0]
    L = int(steps.min()) if steps.size else 1
    pair = d == L
    a, b = res[:-1][pair], res[1:][pair]
    ok = np.isfinite(a) & np.isfinite(b)
    npairs = ok.sum(0)
    num = np.where(ok, a * b, 0.0).sum(0)
    den = np.nansum(res ** 2, 0)
    n = np.isfinite(res).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = num / den * n / np.maximum(npairs, 1)
    return np.where(npairs > 0, r, 0.0), L, npairs


def _slope_variance_inflation(k: np.ndarray, W: np.ndarray, rho: np.ndarray) -> np.ndarray:
    """Var(OLS slope | AR(1) noise) / Var(OLS slope | white noise) for the actual sampling k.

    W (T, N): OLS slope weights (t_i - mean t) / Sxx, zero where a value is missing. rho (N,): lag
    correlation for one month. Uses the exact quadratic form sum_ij w_i w_j rho^|k_i - k_j|,
    evaluated with an O(T) recursion."""
    T, N = W.shape
    cross = np.zeros(N)
    if N <= 64:
        # few columns (single series, period matrix): place the weights on the full monthly grid and run
        # the same recursion acc_j = rho (acc_{j-1} + w_{j-1}) as a linear filter, one column at a time
        grid = np.zeros(int(k[-1] - k[0]) + 1)
        pos = k - k[0]
        for c in range(N):
            r = float(rho[c])
            grid[:] = 0.0
            grid[pos] = W[:, c]
            acc = lfilter([0.0, r], [1.0, -r], grid)
            cross[c] = float((grid * acc).sum())
    else:
        acc = np.zeros(N)
        for j in range(1, T):
            acc = (acc + W[j - 1]) * rho ** float(k[j] - k[j - 1])
            cross += W[j] * acc
    with np.errstate(invalid="ignore", divide="ignore"):
        v = 1.0 + 2.0 * cross / (W ** 2).sum(0)
    return np.maximum(np.where(np.isfinite(v), v, 1.0), 1.0)   # never smaller than white noise


def ols_trend(t: np.ndarray, Y: np.ndarray, alpha: float = 0.05) -> dict:
    """OLS slope per column of Y (T, N) with NaNs and an AR(1) memory correction (one time scale).

    t are decimal years on a monthly grid (decimal_years). Slope units = Y units per year.
    Returns dict of arrays (N,): slope, intercept, se, se_adj, ci_low, ci_high, p, n, n_eff, r1
    (raw lag-one-month correlation), rho (bias-corrected, used), df, tstat, vif.
    """
    Y = np.asarray(Y, "float64")
    if Y.ndim == 1:
        Y = Y[:, None]
    t = np.asarray(t, "float64")
    k = month_index(t)
    tt = t[:, None]
    V = np.isfinite(Y)
    n = V.sum(0).astype("float64")
    T = np.where(V, tt, 0.0)
    Yz = np.where(V, Y, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        tm = T.sum(0) / n
        ym = Yz.sum(0) / n
        dt = np.where(V, tt - tm, 0.0)
        dy = np.where(V, Y - ym, 0.0)
        sxx = (dt * dt).sum(0)
        slope = (dt * dy).sum(0) / sxx
        intercept = ym - slope * tm
        res = np.where(V, Y - (intercept + slope * tt), np.nan)
        s2 = np.nansum(res ** 2, 0) / (n - 2)
        se = np.sqrt(s2 / sxx)
        rL, L, _ = _lag_autocorrelation(res, k)
        # small-sample bias after removing mean and trend: E[r] ≈ rho − (2 + 4 rho)/n -> invert.
        # Corrected on the sampling step L, then expressed per month; negative memory is not used
        # to shrink the error (conservative).
        rLc = np.clip(np.where(np.isfinite(rL), (rL + 2.0 / n) / (1.0 - 4.0 / n), 0.0), 0.0, 0.99)
        rho = rLc ** (1.0 / L) if L > 1 else rLc
        r1 = (np.where(rL > 0, rL, 0.0) ** (1.0 / L)) if L > 1 else np.clip(rL, -0.99, 0.99)
        vif = _slope_variance_inflation(k, dt / sxx, rho)
        n_eff = np.clip(n / vif, 3.0, n)
        se_adj = se * np.sqrt((n - 2) / (n_eff - 2))
        df = n_eff - 2
        tstat = slope / se_adj
        p = 2 * st.t.sf(np.abs(tstat), df)
        tc = st.t.ppf(1 - alpha / 2, df)
    return dict(slope=slope, intercept=intercept, se=se, se_adj=se_adj,
                ci_low=slope - tc * se_adj, ci_high=slope + tc * se_adj,
                p=p, n=n, n_eff=n_eff, r1=r1, rho=rho, df=df, tstat=tstat, vif=vif)


def season_year_means(t: np.ndarray, Y: np.ndarray, min_fraction: float = YEAR_MIN_FRACTION):
    """Mean of each column of Y (T, N) per season-year. A season-year needs at least min_fraction
    of the usual number of samples. Returns (years (Ny,), means (Ny, N))."""
    Y = np.asarray(Y, "float64")
    if Y.ndim == 1:
        Y = Y[:, None]
    sy = season_years(month_index(t))
    years = np.unique(sy)
    usual = float(np.median([(sy == y).sum() for y in years])) if years.size else 0.0
    out = np.full((years.size, Y.shape[1]), np.nan)
    for i, y in enumerate(years):
        X = Y[sy == y]
        V = np.isfinite(X)
        cnt = V.sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            m = np.where(V, X, 0.0).sum(0) / cnt
        out[i] = np.where(cnt >= min_fraction * usual, m, np.nan)
    return years.astype("float64"), out


def _year_t(years: np.ndarray) -> np.ndarray:
    """Season-years as decimal years on the monthly grid (mid-July), 12 months apart."""
    return years + 6.5 / 12.0


def trend_test(t: np.ndarray, Y: np.ndarray, alpha: float = 0.05) -> dict:
    """OLS slope with two memory corrections, combined as an intersection–union test.

    The monthly-scale AR(1) test and the same test on season-year means are both computed; the
    reported p is the larger one and the interval is the union of both intervals, so "significant"
    means significant on both time scales. Returns the monthly dict plus p_month, p_year, n_year,
    n_eff_year, rho_year (one-year lag), binding ('month' / 'year')."""
    m = ols_trend(t, Y, alpha)
    years, A = season_year_means(t, Y)
    nan = np.full_like(m["p"], np.nan)
    if years.size >= 3:
        a = ols_trend(_year_t(years), A, alpha)
        valid = a["n"] >= 5           # fewer than 5 yearly means: the yearly test is not informative
        p_year = np.where(valid, a["p"], nan)
        lo_y = np.where(valid, a["ci_low"], nan)
        hi_y = np.where(valid, a["ci_high"], nan)
        n_year, n_eff_year = a["n"], np.where(valid, a["n_eff"], nan)
        rho_year = np.where(valid, a["rho"] ** 12, nan)
    else:
        p_year = lo_y = hi_y = n_eff_year = rho_year = nan
        n_year = np.zeros_like(m["n"])
    out = dict(m)
    out.update(p_month=m["p"], p_year=p_year, n_year=n_year, n_eff_year=n_eff_year,
               rho_year=rho_year,
               p=np.fmax(m["p"], p_year),
               ci_low=np.fmin(m["ci_low"], lo_y), ci_high=np.fmax(m["ci_high"], hi_y),
               binding=np.where(np.nan_to_num(p_year, nan=-1.0) > m["p"], "year", "month"))
    return out


# ---------------------------------------------------------------- Mann–Kendall
def _season_table(k: np.ndarray, Y: np.ndarray):
    """(rows = season-years, seasons, N) table of Y (T, N); NaN where a month is missing."""
    sy = season_years(k)
    mo = k % 12
    rows, seasons = np.unique(sy), np.unique(mo)
    X = np.full((rows.size, seasons.size, Y.shape[1]), np.nan)
    X[np.searchsorted(rows, sy), np.searchsorted(seasons, mo)] = Y
    return X, rows


def seasonal_mann_kendall(years: np.ndarray, months: np.ndarray, Y: np.ndarray,
                          chunk: int = 512) -> dict:
    """Seasonal Mann–Kendall S with the Hirsch & Slack (1984) covariance correction between seasons
    (their missing-value form, after Dietz & Killeen 1981), and the seasonal Sen slope (per year).

    years, months: calendar year and month index (0–11) of each row of Y (T, N); rows in time order.
    The variance is never taken smaller than under independence (conservative). Ties are rare for
    continuous data and are ignored in the variance."""
    Y = np.asarray(Y, "float64")
    if Y.ndim == 1:
        Y = Y[:, None]
    k = np.asarray(years, np.int64) * 12 + np.asarray(months, np.int64)
    N = Y.shape[1]
    S = np.zeros(N)
    VarS = np.zeros(N)
    for c0 in range(0, N, chunk):
        X, _ = _season_table(k, Y[:, c0:c0 + chunk])          # (n, p, c)
        n, p, c = X.shape
        ng = np.isfinite(X).sum(0).astype("float64")          # (p, c)
        i, j = np.triu_indices(n, 1)
        D = np.nan_to_num(np.sign(X[j] - X[i]))                # (pairs, p, c)
        S[c0:c0 + c] = D.sum((0, 1))
        var_ind = (ng * (ng - 1) * (2 * ng + 5) / 18.0).sum(0)
        R = 0.5 * (ng[None] + 1 + np.nan_to_num(np.sign(X[:, None] - X[None, :])).sum(1))  # (n, p, c)
        cov = np.zeros(c)
        for g in range(p):
            for h in range(g + 1, p):
                K = (D[:, g] * D[:, h]).sum(0)
                cov += 2 * (K + 4 * (R[:, g] * R[:, h]).sum(0) - n * (ng[g] + 1) * (ng[h] + 1)) / 3.0
        VarS[c0:c0 + c] = np.maximum(var_ind + cov, var_ind)
    with np.errstate(invalid="ignore", divide="ignore"):
        Z = np.where(S > 0, (S - 1), np.where(S < 0, S + 1, 0.0)) / np.sqrt(VarS)
        p = 2 * st.norm.sf(np.abs(Z))
    sen = np.full(N, np.nan)
    yrs = np.asarray(years, "float64")
    mos = np.asarray(months)
    for c0 in range(0, N, chunk):
        parts = []
        for m in np.unique(mos):
            sel = np.where(mos == m)[0]
            i, j = np.triu_indices(len(sel), 1)
            dyears = yrs[sel][j] - yrs[sel][i]
            X = Y[sel, c0:c0 + chunk]
            parts.append((X[j] - X[i]) / dyears[:, None])
        with _quiet():
            sen[c0:c0 + chunk] = np.nanmedian(np.concatenate(parts, 0), 0)
    return dict(S=S, Z=Z, p=p, sen_slope=sen, var_S=VarS)


def yearly_mann_kendall(years: np.ndarray, A: np.ndarray, rho_year: np.ndarray) -> dict:
    """Mann–Kendall on season-year means A (Ny, N) with the Hamed & Rao (1998) variance correction.
    The rank autocorrelation at lag k is taken from the AR(1) model with one-year correlation
    rho_year: rho_s(k) = (6/pi) asin(rho_year^k / 2) (normal-theory relation)."""
    A = np.asarray(A, "float64")
    N = A.shape[1]
    p = np.full(N, np.nan)
    Z = np.full(N, np.nan)
    for c in range(N):
        x = A[:, c][np.isfinite(A[:, c])]
        n = x.size
        r = float(rho_year[c]) if np.isfinite(rho_year[c]) else np.nan
        if n < 5 or not np.isfinite(r):
            continue
        i, j = np.triu_indices(n, 1)
        S = np.sign(x[j] - x[i]).sum()
        var = n * (n - 1) * (2 * n + 5) / 18.0
        lag = np.arange(1, n - 2)
        rs = (6 / np.pi) * np.arcsin(max(r, 0.0) ** lag / 2)
        factor = 1 + 2 / (n * (n - 1) * (n - 2)) * ((n - lag) * (n - lag - 1) * (n - lag - 2) * rs).sum()
        var *= max(factor, 1.0)
        Z[c] = (S - np.sign(S)) / np.sqrt(var) if S else 0.0
        p[c] = 2 * st.norm.sf(abs(Z[c]))
    return dict(p=p, Z=Z)


def mann_kendall_test(t: np.ndarray, Y: np.ndarray) -> dict:
    """Rank-based cross-check with both memory corrections; reports the larger p (intersection–union)."""
    Y = np.asarray(Y, "float64")
    if Y.ndim == 1:
        Y = Y[:, None]
    k = month_index(t)
    sk = seasonal_mann_kendall(k // 12, k % 12, Y)
    years, A = season_year_means(t, Y)
    tt = trend_test(t, Y) if years.size >= 3 else None
    yk = yearly_mann_kendall(years, A, tt["rho_year"]) if tt is not None else dict(p=np.full(Y.shape[1], np.nan))
    return dict(S=sk["S"], Z=sk["Z"], sen_slope=sk["sen_slope"], p_seasonal=sk["p"], p_year=yk["p"],
                p=np.fmax(sk["p"], yk["p"]))


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
    o = trend_test(t, a, alpha)
    mk = mann_kendall_test(t, a[:, None])
    g = lambda d, k: float(d[k][0])  # noqa: E731
    return dict(
        anomaly=a, t=t, valid_fraction=frac,
        n_years=int(np.unique(yrs[np.isfinite(a)]).size),
        slope=g(o, "slope") * per, ci_low=g(o, "ci_low") * per, ci_high=g(o, "ci_high") * per,
        p=g(o, "p"), p_month=g(o, "p_month"), p_year=g(o, "p_year"), binding=str(o["binding"][0]),
        n=int(o["n"][0]), n_eff=g(o, "n_eff"), n_year=int(o["n_year"][0]), n_eff_year=g(o, "n_eff_year"),
        r1=g(o, "r1"), rho=g(o, "rho"), rho_year=g(o, "rho_year"),
        intercept=g(o, "intercept"),
        mk_p=g(mk, "p"), mk_p_seasonal=g(mk, "p_seasonal"), mk_p_year=g(mk, "p_year"),
        mk_z=g(mk, "Z"), sen_slope=g(mk, "sen_slope") * per,
    )


def window_matrix(times, y, min_len: int = 15, alpha=0.05, per=10.0) -> dict:
    """Trend for every (start year, end year) window of at least min_len years (same test as the
    headline result). Windows overlap, so they are not independent repetitions."""
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
            o = trend_test(t[sel], a, alpha)
            cells.append(dict(start=s, end=e, slope=float(o["slope"][0]) * per, p=float(o["p"][0]),
                              ci_low=float(o["ci_low"][0]) * per, ci_high=float(o["ci_high"][0]) * per))
    return dict(starts=starts, ends=ends, min_len=min_len, step=step, cells=cells)


def verdict(res: dict, matrix: dict | None, alpha=0.05) -> dict:
    """Plain-language verdict. Never claims causes, never claims 'no change'.

    Keeps three things apart: significance for this period, whether other periods give the same
    direction, and whether they are also significant."""
    short = res.get("n_years", 99) < SHORT_RECORD_YEARS
    if res["valid_fraction"] < MIN_FRACTION or res.get("n_years", 99) < 8:
        return dict(code="insufficient_data", title="Not enough data",
                    text="Too many gaps or too few years. Try a longer period or a bigger area.",
                    short_record=short)
    sig = res["p"] < alpha and (res["ci_low"] > 0 or res["ci_high"] < 0)
    agree = res["mk_p"] < alpha and np.sign(res["sen_slope"]) == np.sign(res["slope"])
    robust = None
    if matrix:
        vals = [c for c in matrix["cells"] if c["slope"] is not None]
        if vals:
            sign = np.sign(res["slope"])
            same = sum(1 for c in vals if np.sign(c["slope"]) == sign)
            sigsame = sum(1 for c in vals if np.sign(c["slope"]) == sign and c["p"] < alpha)
            # Significance is judged on long windows only (>= 3/4 of the analysed span): short windows
            # have little power even for a real trend, so their share would mostly measure length.
            span = max(c["end"] for c in vals) - min(c["start"] for c in vals) + 1
            long_min = max(matrix.get("min_len", 1), int(np.ceil(LONG_WINDOW_SHARE * span)))
            long = [c for c in vals if c["end"] - c["start"] + 1 >= long_min] or vals
            long_sig = sum(1 for c in long if np.sign(c["slope"]) == sign and c["p"] < alpha)
            robust = dict(windows=len(vals), same_sign=same, same_sign_significant=sigsame,
                          long_min_years=long_min, long_windows=len(long), long_significant=long_sig)
    common = dict(methods_agree=bool(agree), robustness=robust, short_record=short)
    if not sig:
        return dict(code="ci_includes_zero", title="No clear trend",
                    text="The range of likely slopes includes zero. That is not proof of no change.",
                    **dict(common, methods_agree=bool(res["mk_p"] >= alpha)))
    if robust and robust["same_sign"] < DIRECTION_STABLE * robust["windows"]:
        return dict(code="depends_on_period", title="Depends on the period",
                    text="Significant here, but many other start/end years disagree. Be careful.", **common)
    if robust and robust["long_significant"] < SIGNIFICANCE_STABLE * robust["long_windows"]:
        return dict(code="significance_depends_on_period", title="Direction holds, significance varies",
                    text=("Significant here, and most other start/end years point the same way, but fewer than "
                          "half of the long periods (at least three quarters of this one) are significant. "
                          "The result depends on the exact start and end years."), **common)
    return dict(code="trend_detected", title="Trend detected",
                text=("Significant at 5% after correcting for memory in the data."
                      + (" A rank-based test (Mann–Kendall) gives the same result." if agree else
                         " The rank-based Mann–Kendall test does not reach 5% – check outliers and the period.")),
                **common)
