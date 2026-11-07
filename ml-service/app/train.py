"""
RaktaSetu ML training pipeline.

Generates a SIMULATED (synthetic) dataset of donor behaviour and trains three models:
  1. acceptance_model  - P(donor accepts an emergency request)
  2. noshow_model      - P(accepted donor fails to reach the blood centre)
  3. demand_model      - expected number of requests per blood group / area / day

No real patient or donor data is used. The data-generating process encodes
reasonable behavioural assumptions (distance, reliability, time of day, urgency...)
so that the models learn meaningful, explainable patterns.

Run:  python -m app.train            (writes models to ./models)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
from sklearn.metrics import accuracy_score, mean_absolute_error, roc_auc_score
from sklearn.model_selection import train_test_split

MODEL_DIR = Path(os.getenv("MODEL_DIR", Path(__file__).resolve().parent.parent / "models"))
SEED = 42

ACCEPT_FEATURES = [
    "distance_km",
    "exact_match",
    "days_since_last_donation",
    "total_donations",
    "acceptance_rate",
    "noshow_rate",
    "urgency",
    "hour_of_day",
    "reliability_score",
]
NOSHOW_FEATURES = [
    "distance_km",
    "hour_of_day",
    "noshow_rate",
    "response_delay_min",
    "urgency",
    "reliability_score",
    "commitment_window_min",
]
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
# approximate share of each group in the Indian population (used only for simulation)
BG_SHARE = [0.22, 0.02, 0.32, 0.02, 0.07, 0.01, 0.32, 0.02]
AREAS = ["central", "north", "south", "east", "west"]
DEMAND_FEATURES = ["blood_group_idx", "area_idx", "day_of_week", "is_holiday", "month"]


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def generate_acceptance_data(n: int = 12000, rng=None) -> pd.DataFrame:
    rng = rng or np.random.default_rng(SEED)
    df = pd.DataFrame(
        {
            "distance_km": rng.gamma(2.0, 4.0, n).clip(0.2, 60),
            "exact_match": rng.integers(0, 2, n),
            "days_since_last_donation": rng.integers(90, 900, n),
            "total_donations": rng.poisson(3, n),
            "acceptance_rate": rng.beta(4, 3, n),
            "noshow_rate": rng.beta(1.2, 8, n),
            "urgency": rng.integers(0, 3, n),  # 0 normal, 1 urgent, 2 critical
            "hour_of_day": rng.integers(0, 24, n),
            "reliability_score": rng.normal(70, 15, n).clip(0, 100),
        }
    )
    night = ((df.hour_of_day >= 23) | (df.hour_of_day <= 5)).astype(int)
    logit = (
        1.2
        - 0.11 * df.distance_km
        + 0.35 * df.exact_match
        + 2.6 * (df.acceptance_rate - 0.55)
        - 2.0 * df.noshow_rate
        + 0.45 * df.urgency
        - 0.9 * night
        + 0.025 * (df.reliability_score - 70)
        + 0.06 * df.total_donations.clip(0, 10)
        - 0.0006 * (df.days_since_last_donation - 90)
    )
    df["accepted"] = (rng.random(n) < _sigmoid(logit + rng.normal(0, 0.4, n))).astype(int)
    return df


def generate_noshow_data(n: int = 8000, rng=None) -> pd.DataFrame:
    rng = rng or np.random.default_rng(SEED + 1)
    df = pd.DataFrame(
        {
            "distance_km": rng.gamma(2.0, 4.0, n).clip(0.2, 60),
            "hour_of_day": rng.integers(0, 24, n),
            "noshow_rate": rng.beta(1.2, 8, n),
            "response_delay_min": rng.exponential(6, n).clip(0, 60),
            "urgency": rng.integers(0, 3, n),
            "reliability_score": rng.normal(70, 15, n).clip(0, 100),
            "commitment_window_min": rng.choice([45, 60, 90, 120], n),
        }
    )
    peak = (((df.hour_of_day >= 8) & (df.hour_of_day <= 10)) | ((df.hour_of_day >= 17) & (df.hour_of_day <= 20))).astype(int)
    logit = (
        -2.4
        + 0.07 * df.distance_km
        + 0.6 * peak
        + 4.0 * df.noshow_rate
        + 0.04 * df.response_delay_min
        - 0.3 * df.urgency
        - 0.03 * (df.reliability_score - 70)
        - 0.006 * (df.commitment_window_min - 60)
    )
    df["no_show"] = (rng.random(n) < _sigmoid(logit)).astype(int)
    return df


def generate_demand_data(days: int = 730, rng=None) -> pd.DataFrame:
    rng = rng or np.random.default_rng(SEED + 2)
    rows = []
    start = pd.Timestamp("2024-01-01")
    for d in range(days):
        date = start + pd.Timedelta(days=d)
        is_holiday = int(date.weekday() >= 5 or rng.random() < 0.04)
        for ai, area in enumerate(AREAS):
            area_factor = [1.6, 1.0, 1.2, 1.1, 0.9][ai]
            for bi, bg in enumerate(BLOOD_GROUPS):
                lam = 6 * BG_SHARE[bi] * area_factor * (1.25 if is_holiday else 1.0)
                lam *= 1.15 if date.month in (6, 7, 8) else 1.0  # dengue/monsoon season bump
                rows.append(
                    {
                        "blood_group_idx": bi,
                        "area_idx": ai,
                        "day_of_week": date.weekday(),
                        "is_holiday": is_holiday,
                        "month": date.month,
                        "requests": rng.poisson(lam),
                    }
                )
    return pd.DataFrame(rows)


def train(model_dir: Path = MODEL_DIR) -> dict:
    model_dir.mkdir(parents=True, exist_ok=True)
    metrics: dict = {"trained_at": datetime.now(timezone.utc).isoformat(), "data": "synthetic (simulated)"}

    acc = generate_acceptance_data()
    X_tr, X_te, y_tr, y_te = train_test_split(acc[ACCEPT_FEATURES], acc["accepted"], test_size=0.2, random_state=SEED)
    acc_model = RandomForestClassifier(n_estimators=150, max_depth=10, min_samples_leaf=5, random_state=SEED, n_jobs=-1)
    acc_model.fit(X_tr, y_tr)
    p = acc_model.predict_proba(X_te)[:, 1]
    metrics["acceptance"] = {
        "algorithm": "RandomForestClassifier",
        "rows": len(acc),
        "accuracy": round(float(accuracy_score(y_te, p > 0.5)), 4),
        "roc_auc": round(float(roc_auc_score(y_te, p)), 4),
        "feature_importance": dict(
            sorted(
                ((f, round(float(i), 4)) for f, i in zip(ACCEPT_FEATURES, acc_model.feature_importances_)),
                key=lambda kv: -kv[1],
            )
        ),
    }

    ns = generate_noshow_data()
    X_tr, X_te, y_tr, y_te = train_test_split(ns[NOSHOW_FEATURES], ns["no_show"], test_size=0.2, random_state=SEED)
    ns_model = RandomForestClassifier(n_estimators=150, max_depth=8, min_samples_leaf=5, random_state=SEED, n_jobs=-1, class_weight="balanced")
    ns_model.fit(X_tr, y_tr)
    p = ns_model.predict_proba(X_te)[:, 1]
    metrics["no_show"] = {
        "algorithm": "RandomForestClassifier (balanced)",
        "rows": len(ns),
        "accuracy": round(float(accuracy_score(y_te, p > 0.5)), 4),
        "roc_auc": round(float(roc_auc_score(y_te, p)), 4),
    }

    dm = generate_demand_data()
    X_tr, X_te, y_tr, y_te = train_test_split(dm[DEMAND_FEATURES], dm["requests"], test_size=0.2, random_state=SEED)
    dm_model = GradientBoostingRegressor(n_estimators=200, max_depth=3, random_state=SEED)
    dm_model.fit(X_tr, y_tr)
    metrics["demand"] = {
        "algorithm": "GradientBoostingRegressor",
        "rows": len(dm),
        "mae": round(float(mean_absolute_error(y_te, dm_model.predict(X_te))), 4),
    }

    joblib.dump(acc_model, model_dir / "acceptance_model.joblib")
    joblib.dump(ns_model, model_dir / "noshow_model.joblib")
    joblib.dump(dm_model, model_dir / "demand_model.joblib")
    (model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
