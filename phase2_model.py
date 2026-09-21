"""
Phase 2 - Modeling
Two HistGradientBoostingRegressor models (units, revenue) per the plan.
NOTE: lightgbm is not installable in this sandboxed environment (no network
egress). HistGradientBoostingRegressor (scikit-learn) is used instead - it is
the same family of algorithm (histogram-based gradient boosted trees, native
categorical support) so the methodology matches what was planned/discussed.

Steps:
 1. Out-of-time validation: train FY21-22 -> validate FY23; retrain FY21-23 -> test FY24
    (mirrors the notebook's OOT discipline, using fiscal years to match the business framing)
 2. Final model: retrain on all of FY21-24 (Apr 2021 - Mar 2025)
 3. Recursive 12-month-ahead forecast for FY2025 (Apr 2025 - Mar 2026), per category
"""
import pandas as pd
import numpy as np
from forecasting_utils import wape, mae, make_model, fit_with_smearing, predict_smeared

pd.set_option("display.width", 140)
np.random.seed(42)

cat_col = "Product Category 1"
monthly = pd.read_csv("monthly_features.csv", parse_dates=["month"])
monthly[cat_col] = monthly[cat_col].astype("category")

CAL_FEATURES = [
    "month_num", "quarter", "fiscal_month", "is_fiscal_q_end", "post_regime_shift",
]

def target_features(target):
    feats = [f"{target}_lag_{l}" for l in [1, 2, 3, 6, 12]]
    feats += [f"{target}_roll_mean_{w}" for w in [3, 6, 12]]
    feats += [f"{target}_roll_std_6", f"{target}_yoy_change"]
    feats += [f"cat_hist_avg_{target}" if target != "revenue" else "cat_hist_avg_revenue"]
    return feats

FEATURES = {
    "units": [cat_col] + CAL_FEATURES + target_features("units") + ["cat_hist_avg_units"],
    "revenue": [cat_col] + CAL_FEATURES + target_features("revenue") + ["cat_hist_avg_revenue", "cat_share_of_month_revenue_lag1"],
}
# de-dup while preserving order
for k in FEATURES:
    seen = set()
    FEATURES[k] = [f for f in FEATURES[k] if not (f in seen or seen.add(f))]

def fit_predict(train_df, test_df, target, feats):
    model = make_model(categorical_idx=[0])
    model, smear = fit_with_smearing(model, train_df[feats], train_df[target])
    preds = predict_smeared(model, test_df[feats], smear)
    return model, preds, smear

results = {}
backtest_rows = []

for target in ["units", "revenue"]:
    feats = FEATURES[target]
    data = monthly.dropna(subset=feats + [target]).copy()

    # --- OOT validation: train FY21-22, validate FY23 ---
    train1 = data[data["fiscal_year"] <= 2022]
    valid1 = data[data["fiscal_year"] == 2023]
    _, valid1_preds, smear1 = fit_predict(train1, valid1, target, feats)
    valid1_wape = wape(valid1[target], valid1_preds)
    valid1_mae = mae(valid1[target], valid1_preds)

    # --- Retrain FY21-23, test FY24 ---
    train2 = data[data["fiscal_year"] <= 2023]
    test2 = data[data["fiscal_year"] == 2024]
    _, test2_preds, smear2 = fit_predict(train2, test2, target, feats)
    test2_wape = wape(test2[target], test2_preds)
    test2_mae = mae(test2[target], test2_preds)

    # Company-level (macro) WAPE for the FY24 test: sum predictions & actuals across categories by month
    t2 = test2[["month", target]].copy()
    t2["pred"] = test2_preds
    macro = t2.groupby("month").sum(numeric_only=True)
    macro_wape = wape(macro[target], macro["pred"])

    print(f"\n=== {target.upper()} ===")
    print(f"Smearing correction factor (bias fix): {smear2:.3f}")
    print(f"FY23 OOT holdout  -> WAPE {valid1_wape*100:.2f}%  MAE {valid1_mae:,.1f}")
    print(f"FY24 test (granular, by category) -> WAPE {test2_wape*100:.2f}%  MAE {test2_mae:,.1f}")
    print(f"FY24 test (macro, company total)   -> WAPE {macro_wape*100:.2f}%")

    results[target] = {
        "fy23_oot_wape": valid1_wape,
        "fy23_oot_mae": valid1_mae,
        "fy24_test_wape_granular": test2_wape,
        "fy24_test_mae_granular": test2_mae,
        "fy24_test_wape_macro": macro_wape,
    }

    for _, row in test2.assign(pred=test2_preds)[[cat_col, "month", target, "pred"]].iterrows():
        backtest_rows.append({
            "category": str(row[cat_col]), "month": row["month"].strftime("%Y-%m-%d"),
            "target": target, "actual": float(row[target]), "predicted": float(row["pred"]),
        })

backtest_df = pd.DataFrame(backtest_rows)
backtest_df.to_csv("backtest_fy24.csv", index=False)

import json
with open("backtest_metrics.json", "w") as f:
    json.dump(results, f, indent=2, default=float)

print("\nSaved backtest_fy24.csv and backtest_metrics.json")
