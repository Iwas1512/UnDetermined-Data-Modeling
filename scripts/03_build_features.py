"""Step 3: daily surface features, realized volatility, and the (date, expiry) modelling table.

Underlying level: the forward of the nearest expiry times its discount factor (about the index
level at 16:15 ET).  Realized variance to an expiry is the sum of squared daily log changes of
that level from the trade date to the expiry date, so implied and realized are on the same clock.

Writes data/processed/daily.parquet and data/processed/samples.parquet.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from volsurf import svi  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "processed"
TENORS = {"iv7": 7, "iv30": 30, "iv60": 60, "iv90": 90}
K95, K105 = np.log(0.95), np.log(1.05)


def interp_total_var(fits: pd.DataFrame, k: float, T: float) -> float:
    """Total variance at log-moneyness k, linear in T between the bracketing expiries' SVI smiles."""
    Ts = fits["T"].to_numpy()
    w = np.array([svi.w_svi(r, k) for r in fits[["a", "b", "rho", "m", "s"]].to_numpy()])
    if T < Ts[0] or T > Ts[-1]:
        return np.nan
    return float(np.interp(T, Ts, w))


def calendar_violations(fits: pd.DataFrame, rel_tol: float = 0.0) -> float:
    """Share of adjacent expiry pairs where total variance falls with maturity somewhere on their common k range
    (by more than rel_tol of the shorter expiry's total variance)."""
    P = fits[["a", "b", "rho", "m", "s"]].to_numpy()
    bad = []
    for i in range(len(fits) - 1):
        lo = max(fits["k_min"].iloc[i], fits["k_min"].iloc[i + 1])
        hi = min(fits["k_max"].iloc[i], fits["k_max"].iloc[i + 1])
        if hi <= lo:
            continue
        kg = np.linspace(lo, hi, 50)
        w1 = svi.w_svi(P[i], kg)
        bad.append(bool(np.any(svi.w_svi(P[i + 1], kg) < w1 * (1 - rel_tol) - 1e-9)))
    return float(np.mean(bad)) if bad else np.nan


def build(root: str):
    fw = pd.read_parquet(DATA / f"forwards_{root}.parquet")
    fits = pd.read_parquet(DATA / f"svi_{root}.parquet").sort_values(["date", "T"])
    opts = pd.read_parquet(DATA / f"options_{root}.parquet", columns=["date", "cp", "oi", "volume"])

    near = fw.sort_values("T").groupby("date").first()
    level = (near["F"] * near["DF"]).rename("S").sort_index()
    dates = list(level.index)
    ret = np.log(level).diff().rename("ret")
    cal = pd.Series(pd.to_datetime(dates), index=dates)

    pc = opts.groupby(["date", "cp"])[["oi", "volume"]].sum().unstack("cp")
    rows = []
    for d, g in fits.groupby("date", sort=True):
        g = g.reset_index(drop=True)
        r = {"date": d}
        for name, days in TENORS.items():
            w = interp_total_var(g, 0.0, days / 365)
            r[name] = np.sqrt(w / (days / 365)) if np.isfinite(w) else np.nan
        T30 = 30 / 365
        w95, w105 = interp_total_var(g, K95, T30), interp_total_var(g, K105, T30)
        r["iv30_95"] = np.sqrt(w95 / T30) if np.isfinite(w95) else np.nan
        r["iv30_105"] = np.sqrt(w105 / T30) if np.isfinite(w105) else np.nan
        r["calendar_viol"] = calendar_violations(g)
        r["calendar_viol_5pct"] = calendar_violations(g, 0.05)
        r["butterfly_ok"] = g["butterfly_ok"].mean()
        r["n_expiries"] = len(g)
        rows.append(r)
    daily = pd.DataFrame(rows).set_index("date")
    daily["skew30"] = daily["iv30_95"] - daily["iv30_105"]
    daily["S"] = level
    daily["ret"] = ret
    # trailing realized vol (calendar-day annualisation, matching the ACT/365 option clock)
    for n in (5, 21):
        ss = (ret ** 2).rolling(n).sum()
        span = (cal - cal.shift(n)).dt.days
        daily[f"rv{n}"] = np.sqrt(ss * 365 / span)
        daily[f"ret{n}"] = np.log(level / level.shift(n))
    daily["drawdown21"] = level / level.rolling(21, min_periods=1).max() - 1
    daily["pc_oi"] = pc[("oi", "P")] / pc[("oi", "C")]
    daily["pc_volume"] = pc[("volume", "P")] / pc[("volume", "C")]
    # forward-looking 30-calendar-day realized vol (the thing iv30 forecasts)
    fwd = []
    for i, d in enumerate(dates):
        end = pd.Timestamp(d) + pd.Timedelta(days=30)
        j = max(jj for jj in range(i, len(dates)) if pd.Timestamp(dates[jj]) <= end)
        if pd.Timestamp(dates[-1]) < end or j == i:
            fwd.append(np.nan)
            continue
        ss = float((ret.iloc[i + 1:j + 1] ** 2).sum())
        fwd.append(np.sqrt(ss * 365 / (pd.Timestamp(dates[j]) - pd.Timestamp(d)).days))
    daily["rv30_fwd"] = fwd
    daily.insert(0, "root", root)

    # (date, expiry) samples: implied ATM vol to expiry vs realized to expiry
    pos = {d: i for i, d in enumerate(dates)}
    cum = np.concatenate([[0.0], np.cumsum(ret.fillna(0).to_numpy()[1:] ** 2)])  # cum[i] = sum r^2 up to date i
    s = fits[fits["expiry"].isin(pos)].copy()
    i0 = s["date"].map(pos).to_numpy()
    i1 = s["expiry"].map(pos).to_numpy()
    s["rv_total_var"] = cum[i1] - cum[i0]
    s["iv_total_var"] = s["atm_iv"] ** 2 * s["T"]
    s["rv_to_expiry"] = np.sqrt(s["rv_total_var"] / s["T"])
    s["overestimate"] = (s["rv_total_var"] < s["iv_total_var"]).astype(int)
    s["days"] = s["T"] * 365
    s = s.merge(daily.drop(columns=["root"]).reset_index(), on="date", how="left")
    return daily.reset_index(), s


def main() -> None:
    dailies, samples = [], []
    for root in ("SPXW", "NDXP"):
        d, s = build(root)
        dailies.append(d)
        samples.append(s)
        print(f"{root}: {len(d)} days, {len(s):,} (date, expiry) samples, "
              f"overestimate rate {s['overestimate'].mean():.1%}, mean iv30 {d['iv30'].mean():.3f}, "
              f"mean rv30_fwd {d['rv30_fwd'].mean():.3f}")
    pd.concat(dailies, ignore_index=True).to_parquet(DATA / "daily.parquet", index=False)
    pd.concat(samples, ignore_index=True).to_parquet(DATA / "samples.parquet", index=False)


if __name__ == "__main__":
    main()
