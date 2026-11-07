import pytest
from fastapi.testclient import TestClient

from app.main import app, load_models
from app.train import generate_acceptance_data, train


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    load_models()
    with TestClient(app) as c:
        yield c


def test_training_quality(tmp_path):
    metrics = train(tmp_path)
    assert metrics["acceptance"]["roc_auc"] > 0.70
    assert metrics["no_show"]["roc_auc"] > 0.60
    assert (tmp_path / "acceptance_model.joblib").exists()


def test_synthetic_data_shape():
    df = generate_acceptance_data(500)
    assert len(df) == 500 and set(df["accepted"].unique()) <= {0, 1}


def test_health(client):
    assert client.get("/health").json()["models_loaded"] is True


def base(**kw):
    d = dict(distance_km=2, exact_match=1, days_since_last_donation=200, total_donations=5,
             acceptance_rate=0.9, noshow_rate=0.02, urgency=2, hour_of_day=11, reliability_score=90)
    d.update(kw)
    return d


def test_near_reliable_donor_scores_higher(client):
    r = client.post("/predict/acceptance", json={"donors": [
        base(donor_id="good"),
        base(donor_id="bad", distance_km=40, acceptance_rate=0.1, noshow_rate=0.6, reliability_score=20, hour_of_day=3),
    ]}).json()["predictions"]
    assert r[0]["accept_probability"] > r[1]["accept_probability"]


def test_noshow_and_forecast(client):
    r = client.post("/predict/noshow", json=dict(distance_km=30, hour_of_day=18, noshow_rate=0.5,
                    response_delay_min=20, urgency=0, reliability_score=30, commitment_window_min=45)).json()
    assert r["risk"] in {"low", "medium", "high"}
    f = client.get("/forecast?area=central&days=7").json()
    assert len(f["totals_by_blood_group"]) == 8
    assert client.get("/forecast?area=mars").status_code == 400
