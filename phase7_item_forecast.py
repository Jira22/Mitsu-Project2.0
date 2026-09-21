"""
Phase 7 - Final item-level FY2025 forecast.

Design (informed by the backtest experiments in phase6/6b/6c/6d - see those
files and the submission notebook for the full investigation):
  - An initial item-level model showed the item-level approach looking much
    worse than the category-level model. That turned out to be a real bug:
    naively back-transforming log1p-trained predictions with expm1() is a
    biased estimator (Jensen's inequality), and at the noisy item level
    that bias was severe (~53% systematic underprediction). A first fix
    (Duan's smearing correction) worked for the category model but was
    unstable at the item level (a few outlier residuals inflated the
    correction factor to >12x). The working fix: Poisson loss, which
    models the mean directly via a log-link with no manual back-transform.
  - With that fixed, a fair backtest (same actual basis - full category
    totals including long-tail items) showed the hybrid approach modestly
    but consistently BEATS the pure category-level model: ~32.5% vs ~35.3%
    WAPE on units, ~29.1% vs ~30.2% on revenue (FY2024 holdout).
  - Qualifying items (948, >=24mo history): their OWN recursive ML forecast
    (Poisson loss), used as-is.
  - Long-tail items (~4,758, <24mo history): no learnable per-item signal,
    so they get a top-down allocation from the CATEGORY forecast's residual
    (category total minus the qualifying items' own ML forecast for that
    category-month), split by each long-tail item's historical share of
    the long-tail total in its category. This reconciles the combined
    item-level forecast to the category total by construction.
"""
import pandas as pd
import numpy as np
from forecasting_utils import make_poisson_model, fit_predict_poisson
import json

item_col = "Item Code"
cat_col = "Product Category 1"

item_monthly = pd.read_csv("item_monthly_features.csv", parse_dates=["month"])
item_monthly[item_col] = item_monthly[item_col].astype("category")
item_monthly[cat_col] = item_monthly[cat_col].astype("category")
QUALIFYING_ITEMS = list(item_monthly[item_col].cat.categories)
item_to_cat = item_monthly.groupby(item_col)[cat_col].first().to_dict()

CAL_FEATURES = ["month_num", "quarter", "fiscal_month", "is_fiscal_q_end", "post_regime_shift"]

def target_features(target):
    feats = [f"{target}_lag_{l}" for l in [1, 2, 3, 6, 12]]
    feats += [f"{target}_roll_mean_{w}" for w in [3, 6, 12]]
    feats += [f"{target}_roll_std_6", f"{target}_yoy_change", f"item_hist_avg_{target}"]
    return feats

FEATURES = {
    "units": [cat_col] + CAL_FEATURES + target_features("units"),
    "revenue": [cat_col] + CAL_FEATURES + target_features("revenue"),
}

# --- final item models, trained on ALL history (Poisson loss - see forecasting_utils) ---
final_item_models = {}
for target in ["units", "revenue"]:
    feats = FEATURES[target]
    data = item_monthly.dropna(subset=feats + [target]).copy()
    model = make_poisson_model(categorical_idx=[0], max_leaf_nodes=31, min_samples_leaf=8, l2_regularization=0.15)
    model.fit(data[feats], data[target].clip(lower=0))
    final_item_models[target] = model
print("Final item models trained on", item_monthly["month"].min().date(), "to", item_monthly["month"].max().date())

item_hist_avg = {
    "units": item_monthly[item_monthly["month"] < "2023-04-01"].groupby(item_col)["units"].mean().to_dict(),
    "revenue": item_monthly[item_monthly["month"] < "2023-04-01"].groupby(item_col)["revenue"].mean().to_dict(),
}
units_hist = {i: item_monthly[item_monthly[item_col] == i].set_index("month")["units"].sort_index() for i in QUALIFYING_ITEMS}
revenue_hist = {i: item_monthly[item_monthly[item_col] == i].set_index("month")["revenue"].sort_index() for i in QUALIFYING_ITEMS}

FUTURE_MONTHS = pd.date_range("2025-04-01", "2026-03-01", freq="MS")

def calendar_feats(m):
    mn = m.month
    return {"month_num": mn, "quarter": (mn - 1) // 3 + 1, "fiscal_month": ((mn - 4) % 12) + 1,
            "is_fiscal_q_end": int((((mn - 4) % 12) + 1) in [3, 6, 9, 12]), "post_regime_shift": 1}

def lag_roll_feats(series, target, upto_month):
    hist = series[series.index < upto_month].sort_index()
    out = {}
    for l in [1, 2, 3, 6, 12]:
        out[f"{target}_lag_{l}"] = hist.iloc[-l] if len(hist) >= l else np.nan
    for w in [3, 6, 12]:
        window = hist.iloc[-w:]
        out[f"{target}_roll_mean_{w}"] = window.mean() if len(window) > 0 else np.nan
    window6 = hist.iloc[-6:]
    out[f"{target}_roll_std_6"] = window6.std() if len(window6) > 1 else 0.0
    lag1, lag12 = out[f"{target}_lag_1"], out[f"{target}_lag_12"]
    out[f"{target}_yoy_change"] = (lag1 - lag12) / (lag12 + 1) if pd.notna(lag1) and pd.notna(lag12) else np.nan
    return out

item_forecast_rows = []
for month in FUTURE_MONTHS:
    cal = calendar_feats(month)
    for target, hist_dict in [("units", units_hist), ("revenue", revenue_hist)]:
        rows = [{cat_col: item_to_cat[i], **cal, **lag_roll_feats(hist_dict[i], target, month),
                 f"item_hist_avg_{target}": item_hist_avg[target].get(i, 0)} for i in QUALIFYING_ITEMS]
        X = pd.DataFrame(rows)[FEATURES[target]]
        X[cat_col] = X[cat_col].astype(pd.CategoricalDtype(categories=list(item_monthly[cat_col].cat.categories)))
        preds = np.maximum(0.0, final_item_models[target].predict(X))
        for i, p in zip(QUALIFYING_ITEMS, preds):
            hist_dict[i].loc[month] = p

for month in FUTURE_MONTHS:
    for i in QUALIFYING_ITEMS:
        item_forecast_rows.append({
            "item": i, "category": item_to_cat[i], "month": month.strftime("%Y-%m-%d"),
            "units_forecast": float(units_hist[i].loc[month]), "revenue_forecast": float(revenue_hist[i].loc[month]),
            "method": "item_ml",
        })

qualifying_forecast_df = pd.DataFrame(item_forecast_rows)
print(f"\nQualifying-item FY2025 forecast: {qualifying_forecast_df['units_forecast'].sum():,.0f} units, "
      f"{qualifying_forecast_df['revenue_forecast'].sum():,.0f} revenue")

# ------------------------------------------------------------------
# Long-tail allocation: category forecast residual, split by historical share
# ------------------------------------------------------------------
category_forecast = pd.read_csv("fy2025_forecast.csv", parse_dates=["month"])

sales = pd.read_csv("MitsubishiModel.csv", parse_dates=["Sales Order Date"])
sales.columns = sales.columns.str.strip()
all_items_cat = sales.groupby("Item Code")[cat_col].agg(lambda s: s.mode().iloc[0])
LONG_TAIL_ITEMS = [i for i in all_items_cat.index if i not in item_to_cat]
print(f"Long-tail items (no dedicated model): {len(LONG_TAIL_ITEMS)}")

long_tail_hist = sales[sales["Item Code"].isin(LONG_TAIL_ITEMS)].copy()
long_tail_hist_totals_units = long_tail_hist.groupby(["Item Code"])["Quantity"].sum()
long_tail_hist_totals_rev = long_tail_hist.groupby(["Item Code"])["Final Sales (Newest)"].sum()
long_tail_cat_totals_units = long_tail_hist.groupby(cat_col)["Quantity"].sum()
long_tail_cat_totals_rev = long_tail_hist.groupby(cat_col)["Final Sales (Newest)"].sum()

qual_sum_by_cat_month = qualifying_forecast_df.groupby(["category", "month"])[["units_forecast", "revenue_forecast"]].sum()

long_tail_rows = []
clip_events = 0
for _, cf_row in category_forecast.iterrows():
    c, m = cf_row["category"], cf_row["month"].strftime("%Y-%m-%d")
    qual_u, qual_r = 0.0, 0.0
    if (c, m) in qual_sum_by_cat_month.index:
        qual_u = qual_sum_by_cat_month.loc[(c, m), "units_forecast"]
        qual_r = qual_sum_by_cat_month.loc[(c, m), "revenue_forecast"]
    residual_units = cf_row["units_forecast"] - qual_u
    residual_rev = cf_row["revenue_forecast"] - qual_r
    if residual_units < 0 or residual_rev < 0:
        clip_events += 1
    residual_units = max(0.0, residual_units)
    residual_rev = max(0.0, residual_rev)

    items_in_cat = [i for i in LONG_TAIL_ITEMS if all_items_cat.get(i) == c]
    cat_lt_units_total = long_tail_cat_totals_units.get(c, 0)
    cat_lt_rev_total = long_tail_cat_totals_rev.get(c, 0)
    for i in items_in_cat:
        share_u = (long_tail_hist_totals_units.get(i, 0) / cat_lt_units_total) if cat_lt_units_total > 0 else 0
        share_r = (long_tail_hist_totals_rev.get(i, 0) / cat_lt_rev_total) if cat_lt_rev_total > 0 else 0
        if share_u == 0 and share_r == 0:
            continue
        long_tail_rows.append({
            "item": i, "category": c, "month": m,
            "units_forecast": residual_units * share_u, "revenue_forecast": residual_rev * share_r,
            "method": "topdown_allocated",
        })

long_tail_forecast_df = pd.DataFrame(long_tail_rows)
print(f"Clip events (ML sum exceeded category forecast): {clip_events} / {len(category_forecast)}")
print(f"Long-tail FY2025 allocated forecast: {long_tail_forecast_df['units_forecast'].sum():,.0f} units, "
      f"{long_tail_forecast_df['revenue_forecast'].sum():,.0f} revenue")

full_item_forecast = pd.concat([qualifying_forecast_df, long_tail_forecast_df], ignore_index=True)
full_item_forecast.to_csv("item_fy2025_forecast_full.csv", index=False)
print(f"\nCombined item-level FY2025 forecast: {len(full_item_forecast)} rows, "
      f"{full_item_forecast['units_forecast'].sum():,.0f} units, {full_item_forecast['revenue_forecast'].sum():,.0f} revenue")
print("(compare to category-level total:", f"{category_forecast['units_forecast'].sum():,.0f} units, "
      f"{category_forecast['revenue_forecast'].sum():,.0f} revenue)")
