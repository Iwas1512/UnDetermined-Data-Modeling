"""Read Databento OPRA.PILLAR definition + statistics files into one clean option chain per day.

What the raw data is (see notebook section 3):
- `definition` files: one record per listed series (root, expiry, strike, call/put).
- `statistics` files: per series and venue, end-of-day summary values.  stat_type 8 / 7 are
  the venue's closing bid / offer (SPXW: Cboe's 16:15 ET snapshot), 6 = cleared volume,
  9 = open interest (in file D it is the open interest at the close of the previous day),
  11 = last trade price.  We keep the LAST record per (series, venue, stat_type).

Raw files are licensed market data and are never committed; set OPRA_DATA_DIR to read them.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import numpy as np
import pandas as pd

from volsurf import black76
from volsurf.forwards import expiry_forwards

ET = ZoneInfo("America/New_York")
FIRST_DATE = dt.date(2025, 10, 24)
LAST_DATE = dt.date(2026, 6, 30)       # project window ends here (later dates reserved for other work)
ROOTS = ("SPXW", "NDXP")
OSI = re.compile(r"^(\w+)\s+(\d{6})([CP])(\d{8})$")
STAT = {8: "bid", 7: "ask", 6: "volume", 9: "oi_prev", 11: "last"}
PLACEHOLDER_ASK = 1e5                  # PHLX posts 200,000.00 as "no offer"


def raw_dir() -> Path:
    return Path(os.environ.get("OPRA_DATA_DIR", Path.home() / "quantdesk-data" / "raw" / "opra"))


def discover_files(root_dir: Path | None = None) -> dict[tuple[str, str], dict[dt.date, Path]]:
    """{(root, schema): {date: file}} from every job's metadata.json under the raw directory."""
    root_dir = root_dir or raw_dir()
    out: dict[tuple[str, str], dict[dt.date, Path]] = {}
    for meta in sorted(root_dir.rglob("metadata.json")):
        q = json.loads(meta.read_text())["query"]
        schema = q["schema"]
        for sym in q["symbols"]:
            r = sym.split(".")[0]
            files = out.setdefault((r, schema), {})
            for f in sorted(meta.parent.glob(f"opra-pillar-*.{schema}.dbn.zst")):
                d = dt.datetime.strptime(f.name.split("-")[2].split(".")[0], "%Y%m%d").date()
                files.setdefault(d, f)
    return out


def trading_dates(files, root: str) -> list[dt.date]:
    ds = set(files[(root, "definition")]) & set(files[(root, "statistics")])
    return sorted(d for d in ds if FIRST_DATE <= d <= LAST_DATE)


def _decode(path: Path) -> pd.DataFrame:
    df = db.DBNStore.from_file(path).to_df(map_symbols=False, pretty_ts=False, price_type="float").reset_index()
    df["_pos"] = np.arange(len(df))
    return df.sort_values(["ts_recv", "_pos"], kind="stable")


def read_definitions(path: Path, root: str) -> pd.DataFrame:
    d = _decode(path).drop_duplicates("instrument_id", keep="last")
    m = d["raw_symbol"].str.extract(OSI)
    out = pd.DataFrame({
        "instrument_id": d["instrument_id"].to_numpy(),
        "symbol": d["raw_symbol"].str.replace(r"\s+", " ", regex=True).to_numpy(),
        "root": m[0].to_numpy(),
        "expiry": pd.to_datetime("20" + m[1], format="%Y%m%d").dt.date.to_numpy(),
        "cp": m[2].to_numpy(),
        "K": m[3].astype(np.int64).to_numpy() / 1000.0,
    })
    return out[out["root"] == root]


def read_statistics(path: Path) -> pd.DataFrame:
    s = _decode(path)
    s = s[s["stat_type"].isin(list(STAT))]
    s = s.drop_duplicates(["instrument_id", "publisher_id", "stat_type"], keep="last")
    wide = s.pivot_table(index=["instrument_id", "publisher_id"], columns="stat_type",
                         values=["price", "quantity"], aggfunc="last")
    v = pd.DataFrame(index=wide.index)
    v["bid"] = wide.get(("price", 8))
    v["ask"] = wide.get(("price", 7))
    v["last"] = wide.get(("price", 11))
    v["volume"] = wide.get(("quantity", 6))
    v["oi_prev"] = wide.get(("quantity", 9))
    v = v.reset_index()
    # Combine venues: best (highest) valid bid, best (lowest) valid offer, summed volume, one OI.
    v.loc[~(v["bid"] > 0), "bid"] = np.nan
    v.loc[~((v["ask"] > 0) & (v["ask"] < PLACEHOLDER_ASK)), "ask"] = np.nan
    g = v.groupby("instrument_id")
    return pd.DataFrame({"bid": g["bid"].max(), "ask": g["ask"].min(), "volume": g["volume"].sum(min_count=1),
                         "oi_prev": g["oi_prev"].max(), "last": g["last"].max(),
                         "n_venues": g["publisher_id"].nunique()}).reset_index()


def year_fraction(d: dt.date, expiry: np.ndarray) -> np.ndarray:
    """Calendar time (ACT/365) from the 16:15 ET snapshot on d to the 16:00 ET PM settlement."""
    t0 = dt.datetime.combine(d, dt.time(16, 15), ET).timestamp()
    t1 = {e: dt.datetime.combine(e, dt.time(16, 0), ET).timestamp() for e in set(expiry)}
    return (np.array([t1[e] for e in expiry]) - t0) / (365.0 * 86400.0)


def load_day(files, root: str, d: dt.date, r_prev: float | None = None, r_fixed: float | None = None):
    """Clean chain for one root-day: quotes, forward, implied vols.  Returns (options, forwards)."""
    defs = read_definitions(files[(root, "definition")][d], root)
    stats = read_statistics(files[(root, "statistics")][d])
    ch = defs.merge(stats, on="instrument_id", how="left")
    ch = ch[ch["expiry"] > d].copy()                       # no closing quote on expiry day
    ch.insert(0, "date", d)
    ch["T"] = year_fraction(d, ch["expiry"].to_numpy())
    ch["two_sided"] = ch["bid"].notna() & ch["ask"].notna() & (ch["ask"] >= ch["bid"])
    ch["mid"] = np.where(ch["two_sided"], 0.5 * (ch["bid"] + ch["ask"]), np.nan)

    fwd = expiry_forwards(ch, r_prev, r_fixed)
    ch = ch.merge(fwd[["expiry", "F", "DF"]], on="expiry", how="left")
    ch = ch[ch["F"].notna()].copy()
    is_call = (ch["cp"] == "C").to_numpy()
    # No-arbitrage bound on the offer: a call is worth less than DF*F, a put less than DF*K.
    bound = np.where(is_call, ch["DF"] * ch["F"], ch["DF"] * ch["K"])
    bad = ch["ask"].to_numpy() >= bound
    ch.loc[bad, ["ask", "mid"]] = np.nan
    ch.loc[bad, "two_sided"] = False

    ch["k"] = np.log(ch["K"] / ch["F"])
    ch["otm"] = np.where(is_call, ch["K"] >= ch["F"], ch["K"] < ch["F"])
    ch["iv"] = black76.implied_vol(ch["mid"].to_numpy(), ch["F"].to_numpy(), ch["K"].to_numpy(),
                                   ch["T"].to_numpy(), ch["DF"].to_numpy(), is_call)
    ch["vega"] = black76.vega(ch["F"].to_numpy(), ch["K"].to_numpy(), ch["T"].to_numpy(),
                              np.where(np.isfinite(ch["iv"]), ch["iv"], 0.2), ch["DF"].to_numpy())
    ch["iv_spread"] = (ch["ask"] - ch["bid"]) / ch["vega"]
    fwd.insert(0, "date", d)
    fwd.insert(1, "root", root)
    cols = ["date", "root", "symbol", "expiry", "T", "cp", "K", "bid", "ask", "mid", "last", "volume",
            "oi_prev", "n_venues", "two_sided", "F", "DF", "k", "otm", "iv", "vega", "iv_spread"]
    return ch[cols].reset_index(drop=True), fwd
