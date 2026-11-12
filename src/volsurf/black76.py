"""Black-76 prices, vega and a vectorised implied-volatility solver.

Index options are priced off the forward F (from put-call parity), so dividends and
rates never have to be estimated separately:  C = DF * (F N(d1) - K N(d2)).
"""

from __future__ import annotations

import numpy as np
from scipy.special import ndtr

SQRT_2PI = np.sqrt(2.0 * np.pi)


def _d1(F, K, T, sigma):
    sT = sigma * np.sqrt(T)
    return (np.log(F / K) + 0.5 * sT * sT) / sT, sT


def price(F, K, T, sigma, DF, is_call):
    """Discounted Black-76 price; arrays broadcast."""
    d1, sT = _d1(F, K, T, sigma)
    d2 = d1 - sT
    call = F * ndtr(d1) - K * ndtr(d2)
    put = K * ndtr(-d2) - F * ndtr(-d1)
    return DF * np.where(is_call, call, put)


def vega(F, K, T, sigma, DF):
    """dPrice/dsigma (per 1.00 of vol)."""
    d1, _ = _d1(F, K, T, sigma)
    return DF * F * np.exp(-0.5 * d1 * d1) / SQRT_2PI * np.sqrt(T)


def implied_vol(px, F, K, T, DF, is_call, lo=1e-4, hi=5.0, iters=80):
    """Bisection on sigma, fully vectorised.  NaN where the price is outside the no-arbitrage range."""
    px, F, K, T, DF = (np.asarray(a, dtype=float) for a in (px, F, K, T, DF))
    is_call = np.asarray(is_call, dtype=bool)
    undisc = px / DF
    intrinsic = np.where(is_call, np.maximum(F - K, 0.0), np.maximum(K - F, 0.0))
    upper = np.where(is_call, F, K)
    ok = (undisc > intrinsic + 1e-12) & (undisc < upper) & (T > 0)
    a = np.full(px.shape, lo)
    b = np.full(px.shape, hi)
    for _ in range(iters):
        m = 0.5 * (a + b)
        too_high = price(F, K, T, m, 1.0, is_call) > undisc
        b = np.where(too_high, m, b)
        a = np.where(too_high, a, m)
    iv = 0.5 * (a + b)
    iv[~ok] = np.nan
    iv[(iv <= lo * 1.01) | (iv >= hi * 0.99)] = np.nan
    return iv
