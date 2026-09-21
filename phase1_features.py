"""
Phase 1 - Data prep & feature engineering
Aggregates raw sales-order lines to MONTHLY x Product Category 1 grain,
builds two targets (Quantity, Final Sales (Newest)) and a feature set
for forecasting. Mirrors the notebook's feature ideas (lags, rolling
stats, calendar) but at the granularity actually asked for in the brief.
"""
import pandas as pd
import numpy as np

pd.set_option("display.width", 140)

# ---------------------------------------------------------------
# Load & merge
# ---------------------------------------------------------------
sales = pd.read_csv("MitsubishiModel.csv", parse_dates=["Sales Order Date"])
customers = pd.read_csv("Customer_xlsx_-_Customer.csv")
sales.columns = sales.columns.str.strip()
customers.columns = customers.columns.str.strip()

df = sales.merge(
    customers[["Customer Internal ID", "FA Sub Industries"]],
    on="Customer Internal ID",
    how="left",
)
df["FA Sub Industries"] = df["FA Sub Industries"].fillna("Unknown_Industry")

date_col = "Sales Order Date"
qty_col = "Quantity"
rev_col = "Final Sales (Newest)"
cat_col = "Product Category 1"

df["month"] = df[date_col].values.astype("datetime64[M]")

# ---------------------------------------------------------------
# Monthly x Category aggregation (company-wide business ask: by product model/category)
# ---------------------------------------------------------------
monthly = (
    df.groupby(["month", cat_col])
    .agg(
        units=(qty_col, "sum"),
        revenue=(rev_col, "sum"),
        n_orders=("SO Internal ID", "nunique"),
        n_customers=("Customer Internal ID", "nunique"),
        vip_revenue=(rev_col, lambda s: s[df.loc[s.index, "Customer.Customer Type"].str.contains("VIP", na=False)].sum()),
    )
    .reset_index()
)

# Fill a complete month x category grid (many category/month combos may be missing -> true zero sales)
all_months = pd.date_range(monthly["month"].min(), monthly["month"].max(), freq="MS")
all_cats = monthly[cat_col].unique()
full_index = pd.MultiIndex.from_product([all_months, all_cats], names=["month", cat_col])
monthly = (
    monthly.set_index(["month", cat_col])
    .reindex(full_index, fill_value=0)
    .reset_index()
)
monthly = monthly.sort_values([cat_col, "month"]).reset_index(drop=True)

# ---------------------------------------------------------------
# Calendar features
# ---------------------------------------------------------------
monthly["year"] = monthly["month"].dt.year
monthly["month_num"] = monthly["month"].dt.month
monthly["quarter"] = monthly["month"].dt.quarter
# Mitsubishi Electric fiscal year: Apr(Y)-Mar(Y+1). FY label = year of April start.
monthly["fiscal_year"] = np.where(monthly["month_num"] >= 4, monthly["year"], monthly["year"] - 1)
monthly["fiscal_month"] = ((monthly["month_num"] - 4) % 12) + 1  # 1=Apr ... 12=Mar
monthly["is_fiscal_q_end"] = monthly["fiscal_month"].isin([3, 6, 9, 12]).astype(int)  # Jun/Sep/Dec/Mar

# Structural break flag identified in EDA (revenue regime shift starting Apr-2023)
monthly["post_regime_shift"] = (monthly["month"] >= "2023-04-01").astype(int)

# ---------------------------------------------------------------
# Lag & rolling features per category, for BOTH targets
# ---------------------------------------------------------------
monthly = monthly.sort_values([cat_col, "month"]).reset_index(drop=True)
group = monthly.groupby(cat_col, group_keys=False)

for target in ["units", "revenue"]:
    for lag in [1, 2, 3, 6, 12]:
        monthly[f"{target}_lag_{lag}"] = group[target].shift(lag)
    monthly[f"{target}_roll_mean_3"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(3).mean())
    monthly[f"{target}_roll_mean_6"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(6).mean())
    monthly[f"{target}_roll_mean_12"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(12).mean())
    monthly[f"{target}_roll_std_6"] = group[f"{target}_lag_1"].transform(lambda s: s.rolling(6).std())
    # Year-over-year change vs. same month last year
    monthly[f"{target}_yoy_change"] = (monthly[f"{target}_lag_1"] - monthly[f"{target}_lag_12"]) / (monthly[f"{target}_lag_12"] + 1)

# Category historical average (computed on TRAIN period only, i.e. before 2023-04, to avoid leakage - mirrors notebook)
train_mask_for_avg = monthly["month"] < "2023-04-01"
cat_hist_avg_units = monthly[train_mask_for_avg].groupby(cat_col)["units"].mean().to_dict()
cat_hist_avg_rev = monthly[train_mask_for_avg].groupby(cat_col)["revenue"].mean().to_dict()
monthly["cat_hist_avg_units"] = monthly[cat_col].map(cat_hist_avg_units).fillna(0)
monthly["cat_hist_avg_revenue"] = monthly[cat_col].map(cat_hist_avg_rev).fillna(0)

# Category size share of company total revenue - use the PREVIOUS month's share (lag 1) so this
# is usable as a real forecasting feature (current month's share isn't known ahead of time).
_month_share = monthly["revenue"] / monthly.groupby("month")["revenue"].transform("sum").replace(0, np.nan)
monthly["_share_tmp"] = _month_share.fillna(0)
monthly["cat_share_of_month_revenue_lag1"] = monthly.groupby(cat_col, group_keys=False)["_share_tmp"].shift(1)
monthly = monthly.drop(columns=["_share_tmp"])

monthly[cat_col] = monthly[cat_col].astype("category")

monthly.to_csv("monthly_features.csv", index=False)
print("Rows:", len(monthly), "Categories:", monthly[cat_col].nunique())
print("Month range:", monthly["month"].min(), "to", monthly["month"].max())
print(monthly.tail(3))
