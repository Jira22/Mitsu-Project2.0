"""
Shared utilities for the forecasting pipeline (category-level and item-level).

Key fix: HistGradientBoostingRegressor is trained on log1p(target) (since
both units and revenue are non-negative and right-skewed), but naively
back-transforming with expm1() is a biased estimator of E[target] by
Jensen's inequality (E[exp(X)] > exp(E[X]) for a random variable X). This
bias is small at the aggregate category level (~5-6% underprediction) but
severe at the item level (~50%+ underprediction, because individual item
series are far noisier/more skewed). Duan's smearing estimator corrects
this: multiply the naive back-transformed prediction by a correction
factor derived from the model's own in-sample residuals in log-space.
"""
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor


def wape(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    denom = np.sum(np.abs(y_true))
    return np.sum(np.abs(y_true - y_pred)) / denom if denom > 0 else np.nan


def mae(y_true, y_pred):
    return float(np.mean(np.abs(np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float))))


def make_model(categorical_idx, max_leaf_nodes=15, min_samples_leaf=5, l2_regularization=0.1, random_state=42):
    return HistGradientBoostingRegressor(
        max_iter=400,
        learning_rate=0.05,
        max_leaf_nodes=max_leaf_nodes,
        min_samples_leaf=min_samples_leaf,
        l2_regularization=l2_regularization,
        categorical_features=categorical_idx,
        random_state=random_state,
    )


def make_poisson_model(categorical_idx, max_leaf_nodes=15, min_samples_leaf=5, l2_regularization=0.1, random_state=42):
    """For noisier / zero-heavy series (e.g. item-level), Poisson loss models
    the mean directly via a log-link without needing a manual log1p
    transform + back-transform correction. Empirically this is far more
    stable than log1p+smearing at the item level, where a handful of
    extreme residuals can make the smearing correction blow up (observed
    smearing factors as large as 12x on this data's item-level revenue
    model). At the category level, log1p+smearing outperforms Poisson loss
    (the aggregated series is less extreme), so the two granularities
    intentionally use different, empirically-chosen loss functions."""
    return HistGradientBoostingRegressor(
        loss="poisson",
        max_iter=400,
        learning_rate=0.05,
        max_leaf_nodes=max_leaf_nodes,
        min_samples_leaf=min_samples_leaf,
        l2_regularization=l2_regularization,
        categorical_features=categorical_idx,
        random_state=random_state,
    )


def fit_predict_poisson(model, X_train, y_train_raw, X_test):
    model.fit(X_train, np.clip(y_train_raw, 0, None))
    return model, np.maximum(0.0, model.predict(X_test))


def fit_with_smearing(model, X_train, y_train_raw):
    """Fits `model` on log1p(y_train_raw) and returns (model, smear_factor),
    where smear_factor = mean(exp(residuals)) computed in log-space on the
    training data (Duan's smearing estimator)."""
    y_log = np.log1p(np.clip(y_train_raw, 0, None))
    model.fit(X_train, y_log)
    train_preds_log = model.predict(X_train)
    resid = y_log.values - train_preds_log if hasattr(y_log, "values") else y_log - train_preds_log
    smear_factor = float(np.mean(np.exp(resid)))
    return model, smear_factor


def predict_smeared(model, X, smear_factor):
    """Back-transforms log-scale predictions with the smearing correction,
    clipping at zero since units/revenue can't be negative."""
    pred_log = model.predict(X)
    raw = np.expm1(pred_log)
    corrected = (raw + 1.0) * smear_factor - 1.0
    return np.maximum(0.0, corrected)
