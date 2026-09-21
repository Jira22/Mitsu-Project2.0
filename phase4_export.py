"""
Phase 3 - Export a single static JSON payload for the standalone dashboard.
"""
"""
Phase 4 - Export a single static JSON payload for the standalone dashboard.

Forecast source: the HYBRID forecast (item-level ML for the 948 qualifying
items + top-down long-tail allocation, rolled up to category/company level)
is used as the primary FY2025 forecast, since it was validated in phase6d
to be modestly more accurate than the pure category-level model (32.5% vs
35.3% WAPE on units, 29.1% vs 30.2% on revenue, FY2024 holdout). The pure
category-level model/backtest is still included for the Model Performance
tab as the baseline comparison.
"""
import pandas as pd
import numpy as np
import json

cat_col = "Product Category 1"

monthly = pd.read_csv("monthly_features.csv", parse_dates=["month"])
backtest = pd.read_csv("backtest_fy24.csv", parse_dates=["month"])
metrics = json.load(open("backtest_metrics.json"))
item_forecast_full = pd.read_csv("item_fy2025_forecast_full.csv", parse_dates=["month"])
hybrid_comparison = json.load(open("fair_hybrid_comparison.json"))

sales = pd.read_csv("MitsubishiModel.csv", parse_dates=["Sales Order Date"])
customers = pd.read_csv("Customer_xlsx_-_Customer.csv")
sales.columns = sales.columns.str.strip()
customers.columns = customers.columns.str.strip()
df = sales.merge(customers[["Customer Internal ID", "FA Sub Industries"]], on="Customer Internal ID", how="left")
df["FA Sub Industries"] = df["FA Sub Industries"].fillna("Unknown_Industry")

CATEGORIES = sorted(monthly[cat_col].unique().tolist())

# --- Hybrid forecast rolled up to category level (the primary FY2025 forecast) ---
forecast = item_forecast_full.groupby(["category", "month"])[["units_forecast", "revenue_forecast"]].sum().reset_index()

# --- 1. Actuals by month & category ---
actuals = []
for _, r in monthly.iterrows():
    actuals.append({
        "month": r["month"].strftime("%Y-%m"),
        "category": r[cat_col],
        "units": round(float(r["units"]), 1),
        "revenue": round(float(r["revenue"]), 2),
    })

# --- 2. FY2025 forecast by month & category (hybrid) ---
forecasts = []
for _, r in forecast.iterrows():
    forecasts.append({
        "month": r["month"].strftime("%Y-%m"),
        "category": r["category"],
        "units_forecast": round(float(r["units_forecast"]), 1),
        "revenue_forecast": round(float(r["revenue_forecast"]), 2),
    })

# --- 3. Company-wide monthly totals (actual history + forecast) ---
company_actual = monthly.groupby("month")[["units", "revenue"]].sum().reset_index()
company_actual_list = [
    {"month": r["month"].strftime("%Y-%m"), "units": round(float(r["units"]), 1), "revenue": round(float(r["revenue"]), 2)}
    for _, r in company_actual.iterrows()
]
company_forecast = forecast.groupby("month")[["units_forecast", "revenue_forecast"]].sum().reset_index()
company_forecast_list = [
    {"month": r["month"].strftime("%Y-%m"), "units_forecast": round(float(r["units_forecast"]), 1), "revenue_forecast": round(float(r["revenue_forecast"]), 2)}
    for _, r in company_forecast.iterrows()
]

# --- 4. Backtest (FY2024 actual vs predicted), for the Model Performance tab (direct category-only model) ---
backtest_company = backtest.pivot_table(index="month", columns="target", values=["actual", "predicted"], aggfunc="sum").reset_index()
backtest_company.columns = ["_".join(c).strip("_") for c in backtest_company.columns]
backtest_company_list = [
    {
        "month": r["month"].strftime("%Y-%m"),
        "units_actual": round(float(r.get("actual_units", 0)), 1),
        "units_predicted": round(float(r.get("predicted_units", 0)), 1),
        "revenue_actual": round(float(r.get("actual_revenue", 0)), 2),
        "revenue_predicted": round(float(r.get("predicted_revenue", 0)), 2),
    }
    for _, r in backtest_company.iterrows()
]

def cat_wape(sub):
    denom = np.sum(np.abs(sub["actual"]))
    return float(np.sum(np.abs(sub["actual"] - sub["predicted"])) / denom) if denom > 0 else None

backtest_by_category = []
for target in ["units", "revenue"]:
    sub_t = backtest[backtest["target"] == target]
    for c, sub in sub_t.groupby("category"):
        backtest_by_category.append({"category": c, "target": target, "wape": cat_wape(sub), "n_months": int(len(sub))})

# --- 5. Category volume tier (for confidence flagging in the dashboard) ---
cat_total_rev = monthly.groupby(cat_col)["revenue"].sum().sort_values(ascending=False)
n_cats = len(cat_total_rev)
tiers = {}
for i, (c, v) in enumerate(cat_total_rev.items()):
    if i < n_cats * 0.4:
        tiers[c] = "high_volume"
    elif i < n_cats * 0.75:
        tiers[c] = "medium_volume"
    else:
        tiers[c] = "low_volume"

# --- 6. EDA breakdowns (reused from the notebook's analysis) ---
rev_by_customer_type = df.groupby("Customer.Customer Type")["Final Sales (Newest)"].sum().sort_values(ascending=False)
rev_by_customer_type_list = [{"customer_type": k, "revenue": round(float(v), 2)} for k, v in rev_by_customer_type.items()]

top_customers = df.groupby(["Customer Internal ID", "Company Name"])["Final Sales (Newest)"].sum().sort_values(ascending=False).head(10)
top_customers_list = [{"company": k[1], "revenue": round(float(v), 2)} for k, v in top_customers.items()]

top_industries = df.groupby("FA Sub Industries")["Final Sales (Newest)"].sum().sort_values(ascending=False).head(8)
top_industries_list = [{"industry": k, "revenue": round(float(v), 2)} for k, v in top_industries.items()]

# --- 7. Item-level FY2025 drill-down (quarterly, qualifying items only - the long tail
#         stays aggregated since it's not individually forecast) ---
def fiscal_quarter(m):
    mn = m.month
    if 4 <= mn <= 6: return "Q1"
    if 7 <= mn <= 9: return "Q2"
    if 10 <= mn <= 12: return "Q3"
    return "Q4"

qual_items = item_forecast_full[item_forecast_full["method"] == "item_ml"].copy()
qual_items["fq"] = qual_items["month"].apply(fiscal_quarter)
item_quarterly = qual_items.groupby(["item", "category", "fq"])[["units_forecast", "revenue_forecast"]].sum().reset_index()
item_fy_total = qual_items.groupby(["item", "category"])[["units_forecast", "revenue_forecast"]].sum().reset_index()

items_payload = []
for _, item_row in item_fy_total.sort_values("revenue_forecast", ascending=False).iterrows():
    item, cat = item_row["item"], item_row["category"]
    q_rows = item_quarterly[(item_quarterly["item"] == item)]
    quarters = {q: {"units": 0.0, "revenue": 0.0} for q in ["Q1", "Q2", "Q3", "Q4"]}
    for _, qr in q_rows.iterrows():
        quarters[qr["fq"]] = {"units": round(float(qr["units_forecast"]), 1), "revenue": round(float(qr["revenue_forecast"]), 2)}
    items_payload.append({
        "item": item, "category": cat,
        "fy2025_units": round(float(item_row["units_forecast"]), 1),
        "fy2025_revenue": round(float(item_row["revenue_forecast"]), 2),
        "quarters": quarters,
    })

# Long-tail (unmodeled) aggregate, per category, for context in the item drill-down
long_tail = item_forecast_full[item_forecast_full["method"] == "topdown_allocated"]
long_tail_by_cat = long_tail.groupby("category")[["units_forecast", "revenue_forecast"]].sum().reset_index()
long_tail_summary = {
    r["category"]: {"units": round(float(r["units_forecast"]), 1), "revenue": round(float(r["revenue_forecast"]), 2)}
    for _, r in long_tail_by_cat.iterrows()
}
n_long_tail_items = sales["Item Code"].nunique() - qual_items["item"].nunique()

# --- 8. Assemble payload ---
payload = {
    "meta": {
        "generated_from": "MitsubishiModel.csv (Apr 2021 - Mar 2025)",
        "data_through": "2025-03",
        "forecast_horizon": "2025-04 to 2026-03 (FY2025)",
        "model": "HistGradientBoostingRegressor (histogram-based gradient boosted trees), monthly x Product Category 1 grain, hybrid with item-level forecasting for 948 high-volume SKUs",
        "note_lightgbm": "Notebook prototype used LightGBM; this environment could not install it (no network access), so scikit-learn's HistGradientBoostingRegressor was used instead - same algorithm family with native categorical support.",
        "note_regime_shift": "Company-wide monthly revenue dropped from a ~175-280M/month range to a sustained ~85-180M/month range starting April 2023; a post_regime_shift flag was added as a feature and this is reflected in the FY2025 forecast level.",
        "note_hybrid_model": "The FY2025 forecast is a hybrid: 948 high-volume items (>=24mo sales history, 77.6% of historical revenue) get their own item-level ML forecast (Poisson-loss HistGradientBoostingRegressor); the remaining ~4,758 long-tail items are allocated top-down from the category forecast's residual, split by historical share. Validated on the FY2024 holdout to modestly outperform a pure category-level model: WAPE "
                             f"{hybrid_comparison['units']['hybrid_item_plus_longtail_wape']*100:.1f}% vs {hybrid_comparison['units']['direct_category_model_wape']*100:.1f}% (units), "
                             f"{hybrid_comparison['revenue']['hybrid_item_plus_longtail_wape']*100:.1f}% vs {hybrid_comparison['revenue']['direct_category_model_wape']*100:.1f}% (revenue).",
        "fy2025_sales_target": None,
    },
    "categories": CATEGORIES,
    "category_volume_tier": tiers,
    "monthly_actuals_by_category": actuals,
    "monthly_forecast_by_category": forecasts,
    "company_monthly_actual": company_actual_list,
    "company_monthly_forecast": company_forecast_list,
    "backtest_company_monthly": backtest_company_list,
    "backtest_by_category": backtest_by_category,
    "backtest_metrics_summary": metrics,
    "hybrid_vs_direct_comparison": hybrid_comparison,
    "fy2025_totals": {
        "units": round(float(forecast["units_forecast"].sum()), 1),
        "revenue": round(float(forecast["revenue_forecast"].sum()), 2),
    },
    "revenue_by_customer_type": rev_by_customer_type_list,
    "top_customers": top_customers_list,
    "top_industries": top_industries_list,
    "item_forecast_fy2025": items_payload,
    "item_long_tail_summary": long_tail_summary,
    "n_qualifying_items": int(qual_items["item"].nunique()),
    "n_long_tail_items": int(n_long_tail_items),
}

with open("dashboard_data.json", "w") as f:
    json.dump(payload, f, indent=None, default=float)

import os
print("Exported dashboard_data.json -", os.path.getsize("dashboard_data.json") / 1024, "KB")
