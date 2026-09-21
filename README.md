# Mitsubishi Electric Demand Forecasting — Python Pipeline

This is the offline half of the forecasting dashboard: it loads the raw
sales-order data, engineers monthly features, trains and backtests models
at both category and item level, produces a recursive FY2025 forecast
(hybrid: item-level ML for high-volume SKUs + top-down allocation for the
long tail), and exports a single JSON payload that the dashboard
(HTML/React artifact) reads. It also builds the dashboard's HTML file
directly.

## Requirements

```
pip install pandas numpy scikit-learn
```

No LightGBM is required. The original notebook used LightGBM; this
pipeline uses scikit-learn's `HistGradientBoostingRegressor` instead
(same family — histogram-based gradient boosted trees, native
categorical support) because the build environment here had no
internet access to install LightGBM. If you have LightGBM available,
you can drop it in as a near-identical replacement — the feature set
and validation logic don't need to change.

## A calibration bug worth knowing about (see `forecasting_utils.py`)

Both targets (units, revenue) are trained on a log1p-transformed scale
since they're non-negative and right-skewed. Naively back-transforming
predictions with `expm1()` is a **biased** estimator of the mean
(Jensen's inequality): mild at the category level (~5-10%
underprediction) but severe at the item level (~53% underprediction,
confirmed by an in-sample calibration check). Two fixes are used,
chosen per granularity based on what was empirically most stable:

- **Category-level model**: Duan's smearing correction (multiply the
  naive back-transformed prediction by a factor derived from training
  residuals). Works well here — smearing factors stayed in the
  1.0–1.2 range.
- **Item-level model**: Poisson loss instead (`loss="poisson"` in
  `HistGradientBoostingRegressor`), which models the mean directly via
  a log-link with no manual back-transform. Smearing was tested first
  but was numerically unstable at the item level — a few outlier
  residuals inflated the correction factor to >12x, causing wild
  overprediction. Poisson loss avoided that entirely.

## Input files expected (same folder)

- `MitsubishiModel.csv` — raw sales order lines (FY2021–FY2025)
- `Customer_xlsx_-_Customer.csv` — customer master (for industry join)
- `Item_xlsx_-_Item.csv` — item master (not currently used directly)

## Run order

```
python phase1_features.py       # -> monthly_features.csv (category-level)
python phase2_model.py          # -> backtest_fy24.csv, backtest_metrics.json
python phase3_forecast.py       # -> fy2025_forecast.csv (category-level recursive forecast)
python phase5_item_features.py  # -> item_monthly_features.csv (item-level, 948 qualifying items)
python phase6_item_model.py     # -> item_backtest_fy24.csv, item_backtest_metrics.json
python phase6d_fair_comparison.py  # -> fair_hybrid_comparison.json (hybrid vs. direct validation)
python phase7_item_forecast.py  # -> item_fy2025_forecast_full.csv (hybrid FY2025 forecast)
python phase4_export.py         # -> dashboard_data.json (uses the hybrid forecast as primary)
python build_dashboard.py       # -> dashboard_final.html (reads app.js + dashboard_data.json)
```

Optional / exploratory (not required for the final pipeline, but kept
since they document the investigation that led to the final design):
`phase6b_topdown_test.py`, `phase6c_reconciliation_test.py`.

Each script writes its output as a CSV/JSON in the working directory,
which later scripts read — run them in order after refreshing
`MitsubishiModel.csv` with a new export each quarter.

## What each file does

| File | Purpose |
|---|---|
| `forecasting_utils.py` | Shared model helpers: `make_model` / `fit_with_smearing` / `predict_smeared` (category-level) and `make_poisson_model` / `fit_predict_poisson` (item-level). |
| `phase1_features.py` | Merges sales + customer data, aggregates to **monthly × Product Category 1**, builds calendar features, lag/rolling features, the FY2023 regime-shift flag, and category historical averages (train-only, no leakage). |
| `phase2_model.py` | Category-level out-of-time backtest (train FY21–22 → validate FY23; retrain FY21–23 → test FY24), with the smearing correction. |
| `phase3_forecast.py` | Retrains the category-level model on full history and produces a recursive 12-month FY2025 forecast. |
| `phase5_item_features.py` | Same feature engineering as phase1, but per item, restricted to the 948 items with ≥24 months of sales history (77.6% of revenue, 85.0% of units). |
| `phase6_item_model.py` | Item-level backtest using Poisson loss. |
| `phase6b_topdown_test.py` / `phase6c_reconciliation_test.py` | Exploratory: tested naive top-down allocation and forecast rescaling as alternatives — both this and reconciliation were found to *not* help; kept for the record of what was tried. |
| `phase6d_fair_comparison.py` | The real validation: builds the full hybrid forecast (item ML + long-tail top-down allocation) for the FY2024 holdout and compares it against the direct category model on the *same* actual basis. Confirms the hybrid modestly but consistently wins (~32.5% vs ~35.3% WAPE units, ~29.1% vs ~30.2% revenue). |
| `phase7_item_forecast.py` | Retrains the item-level model on full history and produces the hybrid FY2025 forecast: qualifying items' own recursive forecast + long-tail items allocated from the category residual. |
| `phase4_export.py` | Assembles `dashboard_data.json`: actuals, the hybrid FY2025 forecast, backtest results (both category and hybrid), category tiers, item-level drill-down data (948 items, quarterly), and the customer/industry EDA breakdowns. |
| `build_dashboard.py` | Injects `dashboard_data.json` and `app.js` into an HTML template to produce `dashboard_final.html`. |
| `app.js` | The dashboard's front-end logic (Chart.js charts, tables, local-storage-backed editable fields, the SKU-Level Detail drill-down). Edit this and re-run `build_dashboard.py` to change the dashboard. |

## Notes on the modeling choices

- **Category-level granularity**: monthly × Product Category 1, since
  most of the 5,706 individual items have too little sales history for
  reliable per-item forecasting on their own.
- **Item-level extension**: the 948 items with ≥24 months of history
  get their own forecast; this was validated (not just assumed) to
  improve accuracy over the category-only model, but only after fixing
  the calibration bug above — the buggy version wrongly suggested
  item-level forecasting *didn't* help.
- **Long tail (~4,758 items)**: no individual model — allocated
  top-down from the category forecast's residual, split by historical
  share within the category.
- **Two independent targets**: `units` (Quantity) and `revenue` (Final
  Sales), each with its own lag/rolling features, per the brief's two
  deliverables.
- **FY2023 regime shift**: company-wide monthly revenue dropped from a
  ~₿175–280M/month range to a sustained ~₿85–180M/month range starting
  April 2023. A `post_regime_shift` binary flag is included as a feature.
- **No FY2025 sales target in the data**: the dashboard has an editable
  target field (saved locally in the browser) for this.

## Re-running with fresh data

Replace `MitsubishiModel.csv` with an updated export (same columns) and
re-run the scripts in order. The backtest windows in `phase2_model.py`
and `phase6_item_model.py` are currently hardcoded to fiscal years
2023/2024 — bump those forward by one year each time a new fiscal year
of actuals becomes available, and re-check model calibration (the
in-sample check pattern in `phase6_item_model.py` / the submission
notebook §6) rather than assuming last time's fix still applies.
