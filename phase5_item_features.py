"""
Phase 5 - Item-level extension, part 1: feature engineering.

Scope decision (see notebook §2 for the full rationale): of 5,706 items,
only 948 have >=24 months of sales history - but those 948 items account
for 77.6% of revenue and 85.0% of units. So:
  - "high-volume" items (>=24 months history): bottom-up ML forecast, same
    methodology as the category-level model.
  - "long-tail" items (<24 months history): NOT modeled individually
    (too little signal) - instead allocated top-down from the category
    forecast, proportional to historical share. See phase7_reconciliation.py.
"""
import pandas as pd
import numpy as np

item_col = "Item Code"
cat_col = "Product Category 1"

sales = pd.read_csv("MitsubishiModel.csv", parse_dates=["Sales Order Date"])
sales.columns = sales.columns.str.strip()
sales["month"] = sales["Sales Order Date"].values.astype("datetime64[M]")

item_month_counts = sales.groupby([item_col, "month"]).size().reset_index().groupby(item_col).size()
QUALIFYING_ITEMS = sorted(item_month_counts[item_month_counts >= 24].index.tolist())
print(f"Qualifying items (>=24mo history): {len(QUALIFYING_ITEMS)} / {sales[item_col].nunique()}")

# Each qualifying item belongs to exactly one category (validate this assumption)
item_to_cat = sales[sales[item_col].isin(QUALIFYING_ITEMS)].groupby(item_col)[cat_col].agg(lambda s: s.mode().iloc[0])
n_multi_cat = sales[sales[item_col].isin(QUALIFYING_ITEMS)].groupby(item_col)[cat_col].nunique()
print(f"Items with >1 category label (using mode): {(n_multi_cat > 1).sum()}")

sub = sales[sales[item_col].isin(QUALIFYING_ITEMS)].copy()
item_monthly = (
    sub.groupby(["month", item_col])
    .agg(units=("Quantity", "sum"), revenue=("Final Sales (Newest)", "sum"))
    .reset_index()
)

all_months = pd.date_range(sales["month"].min(), sales["month"].max(), freq="MS")
full_index = pd.MultiIndex.from_product([all_months, QUALIFYING_ITEMS], names=["month", item_col])
item_monthly = item_monthly.set_index(["month", item_col]).reindex(full_index, fill_value=0).reset_index()
item_monthly[cat_col] = item_monthly[item_col].map(item_to_cat)
item_monthly = item_monthly.sort_values([item_col, "month"]).reset_index(drop=True)

# --- calendar features (same as category-level) ---
item_monthly["year"] = item_monthly["month"].dt.year
item_monthly["month_num"] = item_monthly["month"].dt.month
item_monthly["quarter"] = item_monthly["month"].dt.quarter
item_monthly["fiscal_year"] = np.where(item_monthly["month_num"] >= 4, item_monthly["year"], item_monthly["year"] - 1)
item_monthly["fiscal_month"] = ((item_monthly["month_num"] - 4) % 12) + 1
item_monthly["is_fiscal_q_end"] = item_monthly["fiscal_month"].isin([3, 6, 9, 12]).astype(int)
item_monthly["post_regime_shift"] = (item_monthly["month"] >= "2023-04-01").astype(int)

# --- lag & rolling features, per item ---
item_monthly = item_monthly.sort_values([item_col, "month"]).reset_index(drop=True)
group = item_monthly.groupby(item_col, group_keys=False)
for target in ["units", "revenue"]:
    for lag in [1, 2, 3, 6, 12]:
        item_monthly[f"{target}_lag_{lag}"] = group[target].shift(lag)
    item_monthly[f"{target}_roll_mean_3"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(3).mean())
    item_monthly[f"{target}_roll_mean_6"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(6).mean())
    item_monthly[f"{target}_roll_mean_12"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(12).mean())
    item_monthly[f"{target}_roll_std_6"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(6).std())
    item_monthly[f"{target}_yoy_change"] = (item_monthly[f"{target}_lag_1"] - item_monthly[f"{target}_lag_12"]) / (item_monthly[f"{target}_lag_12"] + 1)

# item historical average (pre-2023-04, no leakage) + item's average share of its OWN category
train_mask = item_monthly["month"] < "2023-04-01"
item_hist_avg_units = item_monthly[train_mask].groupby(item_col)["units"].mean().to_dict()
item_hist_avg_rev = item_monthly[train_mask].groupby(item_col)["revenue"].mean().to_dict()
item_monthly["item_hist_avg_units"] = item_monthly[item_col].map(item_hist_avg_units).fillna(0)
item_monthly["item_hist_avg_revenue"] = item_monthly[item_col].map(item_hist_avg_rev).fillna(0)

item_monthly[item_col] = item_monthly[item_col].astype("category")
item_monthly[cat_col] = item_monthly[cat_col].astype("category")

item_monthly.to_csv("item_monthly_features.csv", index=False)
print(f"Item-level feature table: {item_monthly.shape[0]} rows, {item_monthly[item_col].nunique()} items, {item_monthly.shape[1]} cols")
