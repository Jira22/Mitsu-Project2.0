"""
Phase 6c - Reconciliation test: rescale each item's raw ML prediction so
that items within a category sum exactly to that category's (more
accurate) direct category-level forecast for the same month. This is a
standard hierarchical-forecasting technique ("forecast-proportion
reconciliation") - it keeps the item model's learned relative shape
across items, while inheriting the category model's better level accuracy.
"""
import pandas as pd
import numpy as np
import json

item_backtest = pd.read_csv("item_backtest_fy24.csv", parse_dates=["month"])
cat_backtest = pd.read_csv("backtest_fy24.csv", parse_dates=["month"])

def wape(a, p):
    a, p = np.asarray(a, float), np.asarray(p, float)
    d = np.sum(np.abs(a))
    return np.sum(np.abs(a - p)) / d if d > 0 else np.nan

results = {}
for target in ["units", "revenue"]:
    ib = item_backtest[item_backtest["target"] == target].copy()
    cb = cat_backtest[cat_backtest["target"] == target].set_index(["month", "category"])["predicted"]

    # raw item-level ML WAPE (baseline, already known: 57.60% units / 70.52% revenue)
    raw_wape = wape(ib["actual"], ib["predicted"])

    # sum of raw item predictions per category-month (only over qualifying items)
    item_pred_sum = ib.groupby(["month", "category"])["predicted"].transform("sum")
    ib["item_pred_sum_in_cat"] = item_pred_sum
    ib["cat_model_pred"] = ib.apply(lambda r: cb.get((r["month"], r["category"]), np.nan), axis=1)
    ib = ib.dropna(subset=["cat_model_pred"])

    # rescale factor = trusted category forecast / sum of raw item forecasts in that category-month
    ib["rescale_factor"] = np.where(ib["item_pred_sum_in_cat"] > 0, ib["cat_model_pred"] / ib["item_pred_sum_in_cat"], 1.0)
    ib["reconciled_pred"] = ib["predicted"] * ib["rescale_factor"]

    reconciled_wape = wape(ib["actual"], ib["reconciled_pred"])

    results[target] = {"raw_item_ml_wape": float(raw_wape), "reconciled_item_wape": float(reconciled_wape)}
    print(f"{target}: raw item ML WAPE = {raw_wape*100:.2f}%   ->   reconciled (rescaled to category total) WAPE = {reconciled_wape*100:.2f}%")

with open("reconciliation_test.json", "w") as f:
    json.dump(results, f, indent=2)
