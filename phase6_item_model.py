"""
Phase 6 - Item-level model: backtest, and a rollup comparison against the
pure category-level model to demonstrate the hybrid approach adds value.
"""
import pandas as pd
import numpy as np
from forecasting_utils import wape, make_poisson_model, fit_predict_poisson
import json

item_col = "Item Code"
cat_col = "Product Category 1"

item_monthly = pd.read_csv("item_monthly_features.csv", parse_dates=["month"])
item_monthly[item_col] = item_monthly[item_col].astype("category")
item_monthly[cat_col] = item_monthly[cat_col].astype("category")

CAL_FEATURES = ["month_num", "quarter", "fiscal_month", "is_fiscal_q_end", "post_regime_shift"]

def target_features(target):
    feats = [f"{target}_lag_{l}" for l in [1, 2, 3, 6, 12]]
    feats += [f"{target}_roll_mean_{w}" for w in [3, 6, 12]]
    feats += [f"{target}_roll_std_6", f"{target}_yoy_change", f"item_hist_avg_{target}"]
    return feats

# categorical col: Product Category 1 only. Item Code has 948 unique values,
# which exceeds HistGradientBoostingRegressor's native-categorical cardinality
# limit (255) - item identity is instead captured through the lag/rolling
# features and item_hist_avg_* (both computed per item), so raw Item Code
# isn't needed as a model input.
FEATURES = {
    "units": [cat_col] + CAL_FEATURES + target_features("units"),
    "revenue": [cat_col] + CAL_FEATURES + target_features("revenue"),
}

def fit_predict(train_df, test_df, target, feats):
    model = make_poisson_model(categorical_idx=[0], max_leaf_nodes=31, min_samples_leaf=8, l2_regularization=0.15)
    model, preds = fit_predict_poisson(model, train_df[feats], train_df[target], test_df[feats])
    return model, preds, None

item_backtest_metrics = {}
item_backtest_rows = []

for target in ["units", "revenue"]:
    feats = FEATURES[target]
    data = item_monthly.dropna(subset=feats + [target]).copy()

    train2 = data[data["fiscal_year"] <= 2023]
    test2 = data[data["fiscal_year"] == 2024]
    _, test2_preds, smear = fit_predict(train2, test2, target, feats)
    print(f"  Model: Poisson loss (no log-transform / smearing needed)")

    item_wape = wape(test2[target], test2_preds)

    # Roll item-level predictions up to category level and compare vs actual category totals
    t2 = test2[["month", cat_col, target]].copy()
    t2["pred"] = test2_preds
    cat_rollup = t2.groupby(["month", cat_col]).sum(numeric_only=True).reset_index()
    cat_rollup_wape = wape(cat_rollup[target], cat_rollup["pred"])

    # Company-level rollup
    company_rollup = t2.groupby("month").sum(numeric_only=True)
    company_rollup_wape = wape(company_rollup[target], company_rollup["pred"])

    item_backtest_metrics[target] = {
        "item_level_wape": float(item_wape),
        "rolled_up_to_category_wape": float(cat_rollup_wape),
        "rolled_up_to_company_wape": float(company_rollup_wape),
    }
    print(f"=== {target.upper()} (qualifying items only, FY2024 holdout) ===")
    print(f"  Item-level WAPE                    : {item_wape*100:5.2f}%")
    print(f"  Rolled up to category, WAPE        : {cat_rollup_wape*100:5.2f}%")
    print(f"  Rolled up to company total, WAPE   : {company_rollup_wape*100:5.2f}%")

    for _, row in test2.assign(pred=test2_preds)[[item_col, cat_col, "month", target, "pred"]].iterrows():
        item_backtest_rows.append({
            "item": str(row[item_col]), "category": str(row[cat_col]), "month": row["month"].strftime("%Y-%m-%d"),
            "target": target, "actual": float(row[target]), "predicted": float(row["pred"]),
        })

pd.DataFrame(item_backtest_rows).to_csv("item_backtest_fy24.csv", index=False)
with open("item_backtest_metrics.json", "w") as f:
    json.dump(item_backtest_metrics, f, indent=2)

# ------------------------------------------------------------------
# Compare: does item-level rollup beat the pure category-level model
# on the SAME FY2024 holdout, for the categories that contain qualifying items?
# ------------------------------------------------------------------
cat_monthly = pd.read_csv("monthly_features.csv", parse_dates=["month"])
cat_test24 = cat_monthly[cat_monthly["fiscal_year"] == 2024]

print("\n=== Category-level accuracy: pure category model vs. item-rollup (FY2024 holdout) ===")
comparison = {}
for target in ["units", "revenue"]:
    direct_actual = cat_test24.groupby(cat_col)[target].sum()
    t2 = pd.DataFrame(item_backtest_rows)
    t2 = t2[t2["target"] == target]
    rollup_by_cat = t2.groupby("category")[["actual", "predicted"]].sum()
    common_cats = [c for c in direct_actual.index if c in rollup_by_cat.index]
    rollup_wape_covered = wape(rollup_by_cat.loc[common_cats, "actual"], rollup_by_cat.loc[common_cats, "predicted"])
    comparison[target] = {"covered_categories": len(common_cats), "item_rollup_wape_on_covered_categories": float(rollup_wape_covered)}
    print(f"{target}: item-rollup WAPE on the {len(common_cats)} categories with qualifying items = {rollup_wape_covered*100:.2f}%")

with open("item_vs_category_comparison.json", "w") as f:
    json.dump(comparison, f, indent=2)
