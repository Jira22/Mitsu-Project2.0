"""
Phase 2 (final model) + the piece the original notebook was missing:
a genuine forward, out-of-sample forecast for FY2025 (Apr 2025 - Mar 2026),
built recursively month-by-month per category since future lag/rolling
features don't exist until earlier future months have been predicted.
"""
import pandas as pd
import numpy as np
import json
from forecasting_utils import make_model, fit_with_smearing, predict_smeared

cat_col = "Product Category 1"
monthly = pd.read_csv("monthly_features.csv", parse_dates=["month"])
monthly[cat_col] = monthly[cat_col].astype("category")
CATEGORIES = list(monthly[cat_col].cat.categories)

CAL_FEATURES = ["month_num", "quarter", "fiscal_month", "is_fiscal_q_end", "post_regime_shift"]

def target_features(target):
    feats = [f"{target}_lag_{l}" for l in [1, 2, 3, 6, 12]]
    feats += [f"{target}_roll_mean_{w}" for w in [3, 6, 12]]
    feats += [f"{target}_roll_std_6", f"{target}_yoy_change", f"cat_hist_avg_{target}"]
    return feats

FEATURES = {
    "units": [cat_col] + CAL_FEATURES + target_features("units"),
    "revenue": [cat_col] + CAL_FEATURES + target_features("revenue") + ["cat_share_of_month_revenue_lag1"],
}
for k in FEATURES:
    seen = set()
    FEATURES[k] = [f for f in FEATURES[k] if not (f in seen or seen.add(f))]

# ---------------------------------------------------------------
# Final models: train on ALL available history (Apr2021-Mar2025)
# ---------------------------------------------------------------
final_models = {}
smear_factors = {}
for target in ["units", "revenue"]:
    feats = FEATURES[target]
    data = monthly.dropna(subset=feats + [target]).copy()
    model = make_model(categorical_idx=[0])
    model, smear = fit_with_smearing(model, data[feats], data[target])
    final_models[target] = model
    smear_factors[target] = smear
print("Final models trained on", monthly["month"].min().date(), "to", monthly["month"].max().date())
print("Smearing correction factors:", {k: round(v, 3) for k, v in smear_factors.items()})

# ---------------------------------------------------------------
# Build per-category history series to drive recursive forecasting
# ---------------------------------------------------------------
cat_hist_avg = {
    "units": monthly[monthly["month"] < "2023-04-01"].groupby(cat_col)["units"].mean().to_dict(),
    "revenue": monthly[monthly["month"] < "2023-04-01"].groupby(cat_col)["revenue"].mean().to_dict(),
}

units_hist = {c: monthly[monthly[cat_col] == c].set_index("month")["units"].sort_index() for c in CATEGORIES}
revenue_hist = {c: monthly[monthly[cat_col] == c].set_index("month")["revenue"].sort_index() for c in CATEGORIES}

# Contemporaneous historical share per month (to seed the lag-1 share feature going forward)
month_totals = monthly.groupby("month")["revenue"].sum()
share_hist = {
    c: (revenue_hist[c] / month_totals.reindex(revenue_hist[c].index).replace(0, np.nan)).fillna(0)
    for c in CATEGORIES
}

FUTURE_MONTHS = pd.date_range("2025-04-01", "2026-03-01", freq="MS")

def calendar_feats(month):
    month_num = month.month
    quarter = (month_num - 1) // 3 + 1
    fiscal_month = ((month_num - 4) % 12) + 1
    is_fq_end = int(fiscal_month in [3, 6, 9, 12])
    return {"month_num": month_num, "quarter": quarter, "fiscal_month": fiscal_month,
            "is_fiscal_q_end": is_fq_end, "post_regime_shift": 1}

def lag_roll_feats(series, target, upto_month):
    """series: pd.Series indexed by month, values up to (not including) upto_month already present."""
    hist = series[series.index < upto_month].sort_index()
    out = {}
    for l in [1, 2, 3, 6, 12]:
        out[f"{target}_lag_{l}"] = hist.iloc[-l] if len(hist) >= l else np.nan
    last1 = hist.iloc[-1:] if len(hist) >= 1 else hist
    for w in [3, 6, 12]:
        window = hist.iloc[-w:]
        out[f"{target}_roll_mean_{w}"] = window.mean() if len(window) > 0 else np.nan
    window6 = hist.iloc[-6:]
    out[f"{target}_roll_std_6"] = window6.std() if len(window6) > 1 else 0.0
    lag1 = out[f"{target}_lag_1"]
    lag12 = out[f"{target}_lag_12"]
    out[f"{target}_yoy_change"] = (lag1 - lag12) / (lag12 + 1) if pd.notna(lag1) and pd.notna(lag12) else np.nan
    return out

forecast_rows = []
for month in FUTURE_MONTHS:
    cal = calendar_feats(month)

    # --- units forecast (independent of revenue) ---
    unit_rows = []
    for c in CATEGORIES:
        feats = {cat_col: c, **cal, **lag_roll_feats(units_hist[c], "units", month),
                  "cat_hist_avg_units": cat_hist_avg["units"].get(c, 0)}
        unit_rows.append(feats)
    Xu = pd.DataFrame(unit_rows)[FEATURES["units"]]
    Xu[cat_col] = Xu[cat_col].astype(pd.CategoricalDtype(categories=CATEGORIES))
    units_pred = predict_smeared(final_models["units"], Xu, smear_factors["units"])
    for c, p in zip(CATEGORIES, units_pred):
        units_hist[c].loc[month] = p

    # --- revenue forecast (needs previous month's share, already available) ---
    rev_rows = []
    for c in CATEGORIES:
        share_series = share_hist[c]
        share_lag1 = share_series[share_series.index < month].sort_index().iloc[-1] if len(share_series[share_series.index < month]) else 0.0
        feats = {cat_col: c, **cal, **lag_roll_feats(revenue_hist[c], "revenue", month),
                  "cat_hist_avg_revenue": cat_hist_avg["revenue"].get(c, 0),
                  "cat_share_of_month_revenue_lag1": share_lag1}
        rev_rows.append(feats)
    Xr = pd.DataFrame(rev_rows)[FEATURES["revenue"]]
    Xr[cat_col] = Xr[cat_col].astype(pd.CategoricalDtype(categories=CATEGORIES))
    revenue_pred = predict_smeared(final_models["revenue"], Xr, smear_factors["revenue"])
    for c, p in zip(CATEGORIES, revenue_pred):
        revenue_hist[c].loc[month] = p

    total_rev_month = revenue_pred.sum()
    for c, p in zip(CATEGORIES, revenue_pred):
        share_hist[c].loc[month] = (p / total_rev_month) if total_rev_month > 0 else 0.0

    for c, u, r in zip(CATEGORIES, units_pred, revenue_pred):
        forecast_rows.append({"month": month.strftime("%Y-%m-%d"), "category": c,
                                "units_forecast": float(u), "revenue_forecast": float(r)})

forecast_df = pd.DataFrame(forecast_rows)
forecast_df.to_csv("fy2025_forecast.csv", index=False)

print("\nFY2025 (Apr2025-Mar2026) company-wide forecast totals:")
print("Units:  ", f"{forecast_df['units_forecast'].sum():,.0f}")
print("Revenue:", f"{forecast_df['revenue_forecast'].sum():,.0f}")
print("\nBy month (company total):")
print(forecast_df.groupby("month")[["units_forecast", "revenue_forecast"]].sum())
