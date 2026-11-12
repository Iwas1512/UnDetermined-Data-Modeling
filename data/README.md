# Data

Derived tables from Databento OPRA end-of-day data for SPXW and NDXP index options, 24 Oct 2025 – 30 Jun 2026
(170 trading days). They are built by `scripts/01`–`03` and read by `notebooks/progress_report.ipynb` and
`scripts/04_build_viewer.py`.

| file | rows | one row per | main columns |
|---|---|---|---|
| `processed/forwards_{SPXW,NDXP}.parquet` | 6,690 / 5,574 | date × expiry | `F` forward, `DF` discount factor, `r_day` parity rate, `method` |
| `processed/svi_{SPXW,NDXP}.parquet` | 6,672 / 5,574 | date × expiry (fitted smile) | SVI params `a b rho m s`, `atm_iv`, `atm_skew`, fit errors (`rmse_*`, `cv_rmse_*`), butterfly check, OI / volume totals |
| `processed/daily.parquet` | 340 | date × index | constant-maturity IVs `iv7…iv90`, `skew30`, index level `S`, returns, realized vols `rv5 rv21`, `rv30_fwd` (next-30-day realized) |
| `processed/samples.parquet` | 10,135 | index × date × expiry | the ML table: SVI fit + daily features + `rv_to_expiry`, label `overestimate` |

Volatilities are annualized decimals (0.15 = 15%); `T` is in years (ACT/365); `k` = ln(K/F).

**Not committed:** the per-option quote tables `processed/options_{SPXW,NDXP}.parquet` (4.6 M rows of closing bid/ask,
volume and open interest) and the raw OPRA files. They are licensed exchange data, and the SPX table is over GitHub's
100 MB file limit. Without them the notebook still runs end to end: the cells that need quotes (sample rows, the
cleaning funnel, the EDA figures) print a note and skip, and the smile figure shows the SVI fits without the quote bars.
Everything else — surfaces, implied vs. realized, all ML analyses, and `scripts/04_build_viewer.py` — runs from the tables here.
