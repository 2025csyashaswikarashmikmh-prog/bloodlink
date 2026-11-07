import os
import sys
from pathlib import Path

DB = Path(__file__).parent / "test.db"
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ.setdefault("ML_SERVICE_URL", "http://127.0.0.1:9")  # unreachable -> exercises heuristic fallback
os.environ["DEMO_MODE"] = "true"
os.environ["REDIS_URL"] = ""
os.environ["ESCALATION_TICK_SEC"] = "3600"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client, phone, lang="en", name=""):
    otp = client.post("/api/auth/request-otp", json={"phone": phone}).json()["demo_otp"]
    r = client.post("/api/auth/verify-otp", json={"phone": phone, "otp": otp, "lang": lang, "name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
