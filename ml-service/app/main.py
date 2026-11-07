"""RaktaSetu ML inference service (FastAPI)."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import List

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .train import (
    ACCEPT_FEATURES,
    AREAS,
    BLOOD_GROUPS,
    DEMAND_FEATURES,
    MODEL_DIR,
    NOSHOW_FEATURES,
    train,
)

_models: dict = {}


def load_models() -> None:
    if not (MODEL_DIR / "acceptance_model.joblib").exists():
        train(MODEL_DIR)
    _models["acceptance"] = joblib.load(MODEL_DIR / "acceptance_model.joblib")
    _models["noshow"] = joblib.load(MODEL_DIR / "noshow_model.joblib")
    _models["demand"] = joblib.load(MODEL_DIR / "demand_model.joblib")
    _models["metrics"] = json.loads((MODEL_DIR / "metrics.json").read_text())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_models()
    yield


app = FastAPI(title="RaktaSetu ML Service", version="1.0.0", lifespan=lifespan)


class AcceptanceFeatures(BaseModel):
    donor_id: str = "unknown"
    distance_km: float = Field(ge=0)
    exact_match: int = Field(ge=0, le=1)
    days_since_last_donation: float = Field(ge=0)
    total_donations: int = Field(ge=0)
    acceptance_rate: float = Field(ge=0, le=1)
    noshow_rate: float = Field(ge=0, le=1)
    urgency: int = Field(ge=0, le=2)
    hour_of_day: int = Field(ge=0, le=23)
    reliability_score: float = Field(ge=0, le=100)


class AcceptanceBatch(BaseModel):
    donors: List[AcceptanceFeatures]


class NoShowFeatures(BaseModel):
    distance_km: float = Field(ge=0)
    hour_of_day: int = Field(ge=0, le=23)
    noshow_rate: float = Field(ge=0, le=1)
    response_delay_min: float = Field(ge=0)
    urgency: int = Field(ge=0, le=2)
    reliability_score: float = Field(ge=0, le=100)
    commitment_window_min: float = Field(ge=1)


@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": all(k in _models for k in ("acceptance", "noshow", "demand"))}


@app.get("/model-info")
def model_info():
    return _models.get("metrics", {})


@app.post("/predict/acceptance")
def predict_acceptance(batch: AcceptanceBatch):
    if not batch.donors:
        return {"predictions": []}
    df = pd.DataFrame([d.model_dump() for d in batch.donors])
    probs = _models["acceptance"].predict_proba(df[ACCEPT_FEATURES])[:, 1]
    return {
        "model": "acceptance_rf",
        "predictions": [
            {"donor_id": d.donor_id, "accept_probability": round(float(p), 4)} for d, p in zip(batch.donors, probs)
        ],
    }


@app.post("/predict/noshow")
def predict_noshow(f: NoShowFeatures):
    df = pd.DataFrame([f.model_dump()])[NOSHOW_FEATURES]
    p = float(_models["noshow"].predict_proba(df)[0, 1])
    risk = "high" if p >= 0.5 else "medium" if p >= 0.25 else "low"
    return {"model": "noshow_rf", "noshow_probability": round(p, 4), "risk": risk}


@app.get("/forecast")
def forecast(area: str = "central", days: int = 7):
    if area not in AREAS:
        raise HTTPException(400, f"area must be one of {AREAS}")
    days = max(1, min(days, 30))
    rows = []
    today = date.today()
    for i in range(1, days + 1):
        d = today + timedelta(days=i)
        for bi, bg in enumerate(BLOOD_GROUPS):
            rows.append(
                {
                    "date": d.isoformat(),
                    "blood_group": bg,
                    "blood_group_idx": bi,
                    "area_idx": AREAS.index(area),
                    "day_of_week": d.weekday(),
                    "is_holiday": int(d.weekday() >= 5),
                    "month": d.month,
                }
            )
    df = pd.DataFrame(rows)
    df["expected_requests"] = _models["demand"].predict(df[DEMAND_FEATURES]).clip(0).round(2)
    totals = df.groupby("blood_group")["expected_requests"].sum().round(1).to_dict()
    return {
        "area": area,
        "days": days,
        "totals_by_blood_group": {bg: totals.get(bg, 0) for bg in BLOOD_GROUPS},
        "daily": df[["date", "blood_group", "expected_requests"]].to_dict(orient="records"),
    }
