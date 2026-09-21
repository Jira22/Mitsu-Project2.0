"""
Phase 6d - The real test: build the FULL reconciled forecast for the FY2024
backtest period exactly the way production (phase7) builds FY2025 - qualifying
items' own ML forecast + long-tail items allocated from the residual of the
DIRECT category model's prediction - then compare its rolled-up category
total against the true full category actuals (which include long-tail
items). This is the fair apples-to-apples test: same actual basis for both
the direct category model and the hybrid model.
"""
import pandas as pd
import numpy as np
import json

cat_col = "Product Category 1"

cat_backtest = pd.read_csv("backtest_fy24.csv", parse_dates=["month"])  # direct category model's FY2024 predictions
item_backtest = pd.read_csv("item_backtest_fy24.csv", parse_dates=["month"])  # qualifying items' own FY2024 predictions
cat_monthly = pd.read_csv("monthly_features.csv", parse_dates=["month"])
item_monthly = pd.read_csv("item_monthly_features.csv", parse_dates=["month"])

sales = pd.read_csv("MitsubishiModel.csv", parse_dates=["Sales Order Date"])
sales.columns = sales.columns.str.strip()
all_items_cat = sales.groupby("Item Code")[cat_col].agg(lambda s: s.mode().iloc[0])
qualifying_items = set(item_monthly["Item Code"].unique())
long_tail_items = [i for i in all_items_cat.index if i not in qualifying_items]

def wape(a, p):
    a, p = np.asarray(a, float), np.asarray(p, float)
    d = np.sum(np.abs(a))
    return np.sum(np.abs(a - p)) / d if d > 0 else np.nan

def build_hybrid_for_target(target):
    # long-tail historical shares, computed on pre-FY2024 data only (fiscal_year <= 2023), no leakage
    lt_sales = sales.copy()
    lt_sales["fiscal_year"] = np.where(lt_sales["Sales Order Date"].dt.month >= 4,
                                        lt_sales["Sales Order Date"].dt.year, lt_sales["Sales Order Date"].dt.year - 1)
    lt_hist = lt_sales[(lt_sales["fiscal_year"] <= 2023) & (lt_sales["Item Code"].isin(long_tail_items))]
    col = "Quantity" if target == "units" else "Final Sales (Newest)"
    item_hist_totals = lt_hist.groupby("Item Code")[col].sum()
    cat_hist_totals = lt_hist.groupby(cat_col)[col].sum()

    ib = item_backtest[item_backtest["target"] == target]
    qual_sum_by_cat_month = ib.groupby(["month", "category"])["predicted"].sum()

    cb = cat_backtest[cat_backtest["target"] == target].copy()
    hybrid_rows = []
    for _, row in cb.iterrows():
        m, c, cat_direct_pred, cat_actual = row["month"], row["category"], row["predicted"], row["actual"]
        qual_pred = qual_sum_by_cat_month.get((m, c), 0.0)
        residual = max(0.0, cat_direct_pred - qual_pred)  # long-tail gets the residual of the DIRECT model's prediction
        hybrid_total = qual_pred + residual  # by construction this equals max(cat_direct_pred, qual_pred)
        hybrid_rows.append({"month": m, "category": c, "actual": cat_actual, "hybrid_pred": hybrid_total, "direct_pred": cat_direct_pred})
    return pd.DataFrame(hybrid_rows)

print("=== Fair comparison on FY2024 holdout: same actual basis (full category totals) ===")
comparison = {}
for target in ["units", "revenue"]:
    hybrid_df = build_hybrid_for_target(target)
    direct_wape = wape(hybrid_df["actual"], hybrid_df["direct_pred"])
    hybrid_wape = wape(hybrid_df["actual"], hybrid_df["hybrid_pred"])
    comparison[target] = {"direct_category_model_wape": float(direct_wape), "hybrid_item_plus_longtail_wape": float(hybrid_wape)}
    print(f"{target}: direct category model WAPE = {direct_wape*100:.2f}%   |   hybrid (item ML + long-tail) WAPE = {hybrid_wape*100:.2f}%")

with open("fair_hybrid_comparison.json", "w") as f:
    json.dump(comparison, f, indent=2)
