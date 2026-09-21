"""
Phase 6b - Test a simpler alternative to full item-level ML: allocate the
(already more-accurate) category-level forecast down to items using each
item's recent historical share of its category. This is standard top-down
hierarchical-forecasting reconciliation, and avoids compounding per-item
model noise on top of category noise.

Backtest design: for FY2024, allocate the ACTUAL category FY2024 model
prediction (from phase2, the direct category model) down to each item
using item shares computed from data strictly BEFORE FY2024 (no leakage),
then compare against each item's real FY2024 actuals.
"""
import pandas as pd
import numpy as np
import json

item_col = "Item Code"
cat_col = "Product Category 1"

item_monthly = pd.read_csv("item_monthly_features.csv", parse_dates=["month"])
cat_backtest = pd.read_csv("backtest_fy24.csv", parse_dates=["month"])  # direct category model's FY2024 predictions

def wape(a, p):
    a, p = np.asarray(a, float), np.asarray(p, float)
    d = np.sum(np.abs(a))
    return np.sum(np.abs(a - p)) / d if d > 0 else np.nan

results = {}
share_tables = {}

for target in ["units", "revenue"]:
    # Item's historical share of its category, computed on data before FY2024 (fiscal_year <= 2023)
    hist = item_monthly[item_monthly["fiscal_year"] <= 2023]
    item_hist_total = hist.groupby(item_col)[target].sum()
    cat_hist_total = hist.groupby(cat_col)[target].sum()
    item_to_cat = item_monthly.groupby(item_col)[cat_col].first()
    share = item_hist_total / item_to_cat.map(cat_hist_total)
    share = share.fillna(0)
    share_tables[target] = share

    # Category model's FY2024 PREDICTED total, by category & month (this is what we allocate)
    cat_pred = cat_backtest[cat_backtest["target"] == target].set_index(["month", "category"])["predicted"]

    # Actual item-level FY2024 data
    actual_2024 = item_monthly[item_monthly["fiscal_year"] == 2024][["month", item_col, cat_col, target]].copy()
    actual_2024["item_share"] = actual_2024[item_col].map(share)
    actual_2024["cat_pred_total"] = actual_2024.apply(
        lambda r: cat_pred.get((r["month"], r[cat_col]), np.nan), axis=1
    )
    actual_2024["allocated_pred"] = actual_2024["item_share"] * actual_2024["cat_pred_total"]
    actual_2024 = actual_2024.dropna(subset=["allocated_pred"])

    topdown_item_wape = wape(actual_2024[target], actual_2024["allocated_pred"])
    # rolled back up to category (should reproduce the direct-category-model accuracy almost exactly)
    rollup = actual_2024.groupby(["month", cat_col])[[target, "allocated_pred"]].sum().reset_index()
    topdown_cat_wape = wape(rollup[target], rollup["allocated_pred"])

    results[target] = {
        "topdown_item_level_wape": float(topdown_item_wape),
        "topdown_rolled_to_category_wape": float(topdown_cat_wape),
    }
    print(f"=== {target.upper()}: top-down allocation (category forecast x historical item share) ===")
    print(f"  Item-level WAPE            : {topdown_item_wape*100:.2f}%")
    print(f"  Rolled up to category WAPE : {topdown_cat_wape*100:.2f}%")

print("\n=== Summary: item-level WAPE, three approaches (FY2024 holdout, qualifying items) ===")
item_ml_metrics = json.load(open("item_backtest_metrics.json"))
for target in ["units", "revenue"]:
    print(f"{target}:")
    print(f"  Full item-level ML model      : {item_ml_metrics[target]['item_level_wape']*100:.2f}%")
    print(f"  Top-down proportional alloc.  : {results[target]['topdown_item_level_wape']*100:.2f}%")

with open("topdown_vs_ml_comparison.json", "w") as f:
    json.dump(results, f, indent=2)

# Save the share tables for use in the final FY2025 item-level forecast export
share_df = pd.DataFrame({
    "item": share_tables["units"].index.astype(str),
    "units_share": share_tables["units"].values,
    "revenue_share": share_tables["revenue"].reindex(share_tables["units"].index).values,
})
share_df.to_csv("item_category_shares.csv", index=False)
