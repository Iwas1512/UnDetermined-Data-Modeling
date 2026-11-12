"""Step 2: fit an SVI smile (and the quadratic baseline) to every root-day-expiry.

Also runs a strike-holdout test: every third quote (sorted by strike) is held out, both models
are re-fit on the rest and scored on the held-out quotes.

Writes data/processed/svi_<ROOT>.parquet (one row per root, date, expiry).
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volsurf import svi  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
MIN_QUOTES = 8
MAX_T = 1.0
MAX_ABS_X = 8.0               # |k| / sqrt(T) cap: drops strikes > 8 "standard deviations" out
MAX_IV_SPREAD = 0.15          # quotes wider than 15 vol points carry no information


def select_quotes(g: pd.DataFrame) -> pd.DataFrame:
    T = g["T"].iloc[0]
    q = g[g["otm"] & g["two_sided"] & g["iv"].notna() & (g["iv_spread"] < MAX_IV_SPREAD)
          & (np.abs(g["k"]) / np.sqrt(T) <= MAX_ABS_X)]
    return q.sort_values("K")


def rmse(a):
    return float(np.sqrt(np.mean(np.square(a))))


def fit_day(args):
    root, d, g_day = args
    rows = []
    for e, g in g_day.groupby("expiry", sort=True):
        T = float(g["T"].iloc[0])
        if T > MAX_T:
            continue
        q = select_quotes(g)
        if len(q) < MIN_QUOTES:
            continue
        k, iv, sp = q["k"].to_numpy(), q["iv"].to_numpy(), q["iv_spread"].to_numpy()
        p = svi.fit_svi(k, iv, T, sp)
        c = svi.fit_quadratic(k, iv, T, sp)
        res_s = svi.iv_svi(p, k, T) - iv
        res_q = svi.iv_quadratic(c, k, T) - iv
        # strike holdout: every third quote
        hold = np.zeros(len(q), bool)
        hold[1::3] = True
        p_cv = svi.fit_svi(k[~hold], iv[~hold], T, sp[~hold])
        c_cv = svi.fit_quadratic(k[~hold], iv[~hold], T, sp[~hold])
        cv_s = svi.iv_svi(p_cv, k[hold], T) - iv[hold]
        cv_q = svi.iv_quadratic(c_cv, k[hold], T) - iv[hold]
        kg = np.linspace(k.min(), k.max(), 200)
        g_min = float(np.min(svi.durrleman_g(p, kg)))
        dk = 1e-4
        rows.append({
            "root": root, "date": d, "expiry": e, "T": T, "F": float(g["F"].iloc[0]), "n_quotes": len(q),
            "k_min": float(k.min()), "k_max": float(k.max()),
            "a": p[0], "b": p[1], "rho": p[2], "m": p[3], "s": p[4],
            "atm_iv": float(svi.iv_svi(p, 0.0, T)),
            "atm_skew": float((svi.iv_svi(p, dk, T) - svi.iv_svi(p, -dk, T)) / (2 * dk)),
            "rmse_svi": rmse(res_s), "rmse_quad": rmse(res_q),
            "inside_svi": float(np.mean(np.abs(res_s) <= 0.5 * sp)),
            "inside_quad": float(np.mean(np.abs(res_q) <= 0.5 * sp)),
            "cv_rmse_svi": rmse(cv_s), "cv_rmse_quad": rmse(cv_q),
            "butterfly_g_min": g_min, "butterfly_ok": g_min >= 0,
            "oi_put": float(g.loc[g["cp"] == "P", "oi"].sum()), "oi_call": float(g.loc[g["cp"] == "C", "oi"].sum()),
            "vol_put": float(g.loc[g["cp"] == "P", "volume"].sum()),
            "vol_call": float(g.loc[g["cp"] == "C", "volume"].sum()),
        })
    return rows


def main() -> None:
    for root in sys.argv[1:] or ("SPXW", "NDXP"):
        t0 = time.time()
        o = pd.read_parquet(DATA / f"options_{root}.parquet")
        jobs = [(root, d, g) for d, g in o.groupby("date", sort=True)]
        with ProcessPoolExecutor(max_workers=16) as ex:
            rows = [r for day in ex.map(fit_day, jobs, chunksize=2) for r in day]
        out = pd.DataFrame(rows)
        out.to_parquet(DATA / f"svi_{root}.parquet", index=False)
        print(f"{root}: {len(out):,} smile fits, median RMSE svi {out.rmse_svi.median():.4f} "
              f"quad {out.rmse_quad.median():.4f}; holdout svi {out.cv_rmse_svi.median():.4f} "
              f"quad {out.cv_rmse_quad.median():.4f}; butterfly-free {out.butterfly_ok.mean():.1%}; "
              f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
