# Reading the Market's Volatility Forecast — CS 418, Team UIC Traders

Implied-volatility surfaces for S&P 500 (SPXW) and Nasdaq-100 (NDXP) index options, built from Databento OPRA
end-of-day data (24 Oct 2025 – 30 Jun 2026), and what they say about implied vs. realized volatility.

**Progress report:** [`notebooks/progress_report.ipynb`](notebooks/progress_report.ipynb) ·
PDF: [`progress_report.pdf`](notebooks/progress_report.pdf) (figures only) /
[`progress_report_with_code.pdf`](notebooks/progress_report_with_code.pdf)<br>
**Interactive viewer (first version):** [`app/surface_viewer.html`](app/surface_viewer.html). Download it and open it in a
browser (it is self-contained; Plotly loads from a CDN).

## Layout

| path | what |
|---|---|
| `src/volsurf/data.py` | read OPRA `definition` + `statistics` files → one clean option chain per day |
| `src/volsurf/forwards.py` | forward price and discount factor per expiry from put–call parity |
| `src/volsurf/black76.py` | Black–76 price / vega / vectorized implied-vol solver |
| `src/volsurf/svi.py` | SVI smile fit, quadratic baseline, butterfly-arbitrage check |
| `scripts/01_prepare_data.py` | raw → `data/processed/options_*.parquet`, `forwards_*.parquet` |
| `scripts/02_fit_surfaces.py` | SVI + baseline fits with strike hold-out → `svi_*.parquet` |
| `scripts/03_build_features.py` | daily surface features, realized vol, modelling table → `daily.parquet`, `samples.parquet` |
| `scripts/04_build_viewer.py` | `app/surface_viewer.html` |
| `notebooks/progress_report.ipynb` | the report (EDA, visualizations, ML analyses) |

## Reproduce

```bash
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -r requirements.txt
set OPRA_DATA_DIR=<folder with the Databento OPRA job folders>   # export on macOS/Linux
python scripts/01_prepare_data.py
python scripts/02_fit_surfaces.py
python scripts/03_build_features.py
python scripts/04_build_viewer.py
jupyter nbconvert --to notebook --execute --inplace notebooks/progress_report.ipynb
```

## Data

The raw OPRA files and the processed quote tables are licensed market data and are **not committed** (`data/` is
git-ignored). Source: Databento `OPRA.PILLAR`, schemas `definition` and `statistics`, parents `SPXW.OPT` and `NDXP.OPT`,
one file per trading day.
