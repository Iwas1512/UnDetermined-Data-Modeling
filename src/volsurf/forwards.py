"""Forward price and discount factor per expiry from put-call parity.

For European index options  C(K) - P(K) = DF * (F - K):  a straight line in K with slope -DF and
intercept DF*F.  We regress call-minus-put mids on strike near the money, drop outliers (4 MAD),
and read F and DF off the fit.  For short expiries (T < 0.1y) the slope is too flat to pin DF, so
DF = exp(-r T) with r the day's rate from the longer expiries, and F = median(K + (C - P) / DF).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_NEAR = 20          # strikes nearest the money used in the fit
MIN_PAIRS = 5
MAD_K, MAD_FLOOR = 4.0 * 1.4826, 0.05
LONG_T = 0.1
R_DEFAULT = 0.04


def _pairs(g: pd.DataFrame):
    c = g[(g["cp"] == "C") & g["two_sided"]].set_index("K")["mid"]
    p = g[(g["cp"] == "P") & g["two_sided"]].set_index("K")["mid"]
    both = c.index.intersection(p.index)
    K = np.asarray(both, dtype=float)
    y = (c.loc[both] - p.loc[both]).to_numpy(dtype=float)
    if len(K) == 0:
        return K, y
    F0 = K[np.argmin(np.abs(y))] + y[np.argmin(np.abs(y))]
    near = np.argsort(np.abs(K - F0))[:N_NEAR]
    return K[near], y[near]


def _robust_line(K, y):
    keep = np.ones(len(K), bool)
    for _ in range(2):
        b, a = np.polyfit(K[keep], y[keep], 1)
        res = y - (a + b * K)
        mad = max(np.median(np.abs(res[keep] - np.median(res[keep]))) * MAD_K, MAD_FLOOR)
        new = np.abs(res) <= mad
        if new.sum() < MIN_PAIRS or (new == keep).all():
            break
        keep = new
    return a, b, int(keep.sum())


def expiry_forwards(ch: pd.DataFrame, r_prev: float | None = None, r_fixed: float | None = None) -> pd.DataFrame:
    """r_fixed: use this day rate instead of estimating it (NDX uses the SPX parity rate: same risk-free rate,
    but NDXP's long-dated quotes are too thin to pin it down)."""
    rows, pairs = [], {}
    for e, g in ch.groupby("expiry", sort=True):
        K, y = _pairs(g)
        pairs[e] = (K, y, float(g["T"].iloc[0]))
    # 1) day's rate from long expiries
    rs = []
    for e, (K, y, T) in pairs.items():
        if T >= LONG_T and len(K) >= MIN_PAIRS:
            a, b, n = _robust_line(K, y)
            DF = -b
            if 0.5 < DF < 1.05 and DF > 0:
                rs.append(-np.log(DF) / T)
    r_day = float(np.median(rs)) if rs else (r_prev if r_prev is not None else R_DEFAULT)
    if r_fixed is not None:
        r_day = r_fixed
    # 2) forward per expiry
    for e, (K, y, T) in pairs.items():
        if len(K) < MIN_PAIRS:
            continue
        if T >= LONG_T:
            a, b, n = _robust_line(K, y)
            DF, method = -b, "ols"
            F = a / DF if DF > 0 else np.nan
            if not (0.5 < DF < 1.05) or abs(DF - np.exp(-r_day * T)) > 0.02:
                DF, method = np.exp(-r_day * T), "rate"
                F = float(np.median(K + y / DF))
        else:
            DF, method, n = np.exp(-r_day * T), "rate", len(K)
            F = float(np.median(K + y / DF))
        if np.isfinite(F) and F > 0:
            rows.append({"expiry": e, "T": T, "F": F, "DF": DF, "n_pairs": n, "method": method, "r_day": r_day})
    return pd.DataFrame(rows)
