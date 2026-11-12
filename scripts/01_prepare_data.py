"""Step 1: raw OPRA files -> cleaned option chains with forwards and implied vols (parquet).

    OPRA_DATA_DIR=<raw opra dir> python scripts/01_prepare_data.py

Writes data/processed/options_<ROOT>.parquet and forwards_<ROOT>.parquet for SPXW and NDXP.
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
warnings.filterwarnings("ignore", message=".*inplace.*")

from volsurf.data import ROOTS, discover_files, load_day, trading_dates  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "processed"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = discover_files()
    spx_rate: dict = {}
    for root in ROOTS:                    # SPXW first: its parity rate is reused for NDXP
        t0 = time.time()
        dates = trading_dates(files, root)
        opts, fwds, r_prev = [], [], None
        for d in dates:
            o, f = load_day(files, root, d, r_prev, spx_rate.get(d) if root != "SPXW" else None)
            r_prev = float(f["r_day"].iloc[0])
            if root == "SPXW":
                spx_rate[d] = r_prev
            opts.append(o)
            fwds.append(f)
        o = pd.concat(opts, ignore_index=True)
        f = pd.concat(fwds, ignore_index=True)
        # Open interest: file D carries the OI at the close of the PREVIOUS trading day, so the OI at
        # the close of day D comes from the next file.  (The last day has none.)
        nxt = dict(zip(dates[:-1], dates[1:]))
        oi = o[["date", "symbol", "oi_prev"]].copy()
        oi["date"] = oi["date"].map({v: k for k, v in nxt.items()})
        oi = oi.dropna(subset=["date"]).rename(columns={"oi_prev": "oi"})
        o = o.merge(oi, on=["date", "symbol"], how="left").drop(columns="oi_prev")
        o.to_parquet(OUT / f"options_{root}.parquet", index=False)
        f.to_parquet(OUT / f"forwards_{root}.parquet", index=False)
        n_iv = int(o["iv"].notna().sum())
        print(f"{root}: {len(dates)} days {dates[0]}..{dates[-1]}, {len(o):,} series-days, "
              f"{n_iv:,} with IV, {len(f):,} expiry-days, {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
