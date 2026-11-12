"""SVI smile fits (Gatheral's raw SVI) and a quadratic baseline.

Raw SVI gives total implied variance w = sigma^2 T as a function of log-moneyness k = ln(K/F):
    w(k) = a + b * ( rho (k - m) + sqrt((k - m)^2 + s^2) )
We fit in sqrt(T)-scaled coordinates (x = k / sqrt(T), v = w / T = sigma^2), which is the same
family with a = T a', b = sqrt(T) b', m = sqrt(T) m', s = sqrt(T) s'.  That makes one set of
starting values work for a 1-day and a 1-year expiry.  Residuals are measured in implied vol and
divided by half the bid-ask spread (in vol), with a soft-L1 loss, so a quote is "fit" when the
model sits inside its spread.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

LB = np.array([-1.0, 1e-6, -0.999, -5.0, 1e-4])
UB = np.array([4.0, 5.0, 0.999, 5.0, 10.0])
STARTS = [(0.1, -0.6, 0.0, 0.2), (0.3, -0.3, 0.0, 0.8), (0.05, -0.9, 0.2, 0.1), (0.2, 0.0, 0.0, 0.4)]
MIN_SPREAD = 0.005                    # floor on the vol spread used as the residual scale


def w_svi(p, k):
    a, b, rho, m, s = p
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + s * s))


def to_raw(q, T):
    a, b, rho, m, s = q
    rt = np.sqrt(T)
    return np.array([a * T, b * rt, rho, m * rt, s * rt])


def iv_svi(p, k, T):
    return np.sqrt(np.maximum(w_svi(p, k), 1e-12) / T)


def _fit_scaled(x, iv, scale):
    v = iv * iv
    best = None
    for b, rho, m, s in STARTS:
        a0 = max(np.min(v) - b * s * np.sqrt(1 - rho * rho), -0.5)
        q0 = np.clip([a0, b, rho, m, s], LB + 1e-9, UB - 1e-9)

        def res(q):
            return (np.sqrt(np.maximum(w_svi(q, x), 1e-12)) - iv) / scale

        r = least_squares(res, q0, bounds=(LB, UB), loss="soft_l1", f_scale=1.0, x_scale="jac", max_nfev=400)
        if best is None or r.cost < best.cost:
            best = r
    return best.x


def fit_svi(k, iv, T, iv_spread):
    """Raw SVI params for one expiry (arrays of OTM quotes)."""
    x = k / np.sqrt(T)
    scale = np.maximum(0.5 * iv_spread, MIN_SPREAD / 2)
    return to_raw(_fit_scaled(x, iv, scale), T)


def fit_quadratic(k, iv, T, iv_spread):
    """Baseline: sigma(x) = c0 + c1 x + c2 x^2 in x = k / sqrt(T), same weights (weighted least squares)."""
    x = k / np.sqrt(T)
    wts = 1.0 / np.maximum(0.5 * iv_spread, MIN_SPREAD / 2)
    return np.polyfit(x, iv, 2, w=wts)


def iv_quadratic(c, k, T):
    return np.polyval(c, k / np.sqrt(T))


def durrleman_g(p, k):
    """Butterfly-arbitrage function; the smile is free of butterfly arbitrage where g(k) >= 0."""
    a, b, rho, m, s = p
    r = np.sqrt((k - m) ** 2 + s * s)
    w = w_svi(p, k)
    w1 = b * (rho + (k - m) / r)
    w2 = b * s * s / r ** 3
    return (1 - k * w1 / (2 * w)) ** 2 - (w1 * w1 / 4) * (1 / w + 0.25) + w2 / 2
