from conftest import login


def test_health_and_meta(client):
    h = client.get("/api/health").json()
    assert h["database"] is True
    assert "B+" in client.get("/api/meta").json()["blood_groups"]


def test_otp_errors(client):
    assert client.post("/api/auth/request-otp", json={"phone": "12345"}).status_code == 422
    client.post("/api/auth/request-otp", json={"phone": "9123400000"})
    assert client.post("/api/auth/verify-otp", json={"phone": "9123400000", "otp": "000000"}).status_code == 401
    assert client.get("/api/donors/me").status_code == 401


def test_full_emergency_flow(client):
    """requester creates request -> donors alerted -> donor accepts -> checks in -> staff confirms -> fulfilled"""
    req_h = login(client, "9123456780", name="Family Member")
    r = client.post("/api/requests", headers=req_h, json={
        "blood_group": "B+", "units": 1, "urgency": "critical", "hospital": "Manipal Hospital, Old Airport Road",
        "lat": 12.9592, "lon": 77.6489})
    assert r.status_code == 200, r.text
    req = r.json()
    notified = [m for m in req["matches"] if m["status"] == "notified"]
    assert notified, "at least one compatible donor should be alerted"
    assert all(m["blood_group"] in req["compatible_groups"] for m in notified)
    assert all("******" in m["donor_phone"] for m in notified), "phones must be masked before acceptance"
    assert notified[0]["priority_score"] >= notified[-1]["priority_score"]

    # log in as the top-ranked donor via demo login
    accounts = client.get("/api/demo/accounts").json()
    from app.database import SessionLocal
    from app.models import DonorMatch
    db = SessionLocal()
    match = db.get(DonorMatch, notified[0]["id"])
    donor_id = match.donor_id
    db.close()
    assert any(a["id"] == donor_id for a in accounts)
    tok = client.post(f"/api/demo/login/{donor_id}").json()["token"]
    don_h = {"Authorization": f"Bearer {tok}"}

    me = client.get("/api/donors/me", headers=don_h).json()
    alert = next(m for m in me["matches"] if m["match_id"] == notified[0]["id"])
    assert "******" in alert["requester_phone"]

    acc = client.post(f"/api/matches/{alert['match_id']}/accept", headers=don_h)
    assert acc.status_code == 200, acc.text
    assert "******" not in acc.json()["requester_phone"], "contact revealed after acceptance"
    assert client.post(f"/api/matches/{alert['match_id']}/accept", headers=don_h).status_code == 409

    view = client.get(f"/api/requests/{req['id']}", headers=req_h).json()
    assert view["status"] == "donor_committed"
    committed = next(m for m in view["matches"] if m["status"] == "accepted")
    assert "******" not in committed["donor_phone"]
    # other open alerts are withdrawn because 1 unit is covered
    assert not [m for m in view["matches"] if m["status"] == "notified"]

    ck = client.post(f"/api/matches/{alert['match_id']}/checkin", headers=don_h, json={"lat": 12.9593, "lon": 77.6488})
    assert ck.status_code == 200
    staff_h = login(client, "8888888888")
    done = client.post(f"/api/matches/{alert['match_id']}/confirm", headers=staff_h).json()
    assert done["status"] == "fulfilled" and done["units_fulfilled"] == 1
    types = [e["type"] for e in done["events"]]
    for t in ("created", "donors_notified", "donor_accepted", "donor_checked_in", "donation_confirmed"):
        assert t in types

    prof = client.get("/api/donors/me", headers=don_h).json()
    assert prof["in_cooldown"] is True and prof["availability"] == "unavailable"
    assert client.patch("/api/donors/availability", headers=don_h, json={"status": "available"}).status_code == 409


def test_decline_and_expiry_escalate(client):
    req_h = login(client, "9123456781")
    req = client.post("/api/requests", headers=req_h, json={
        "blood_group": "O+", "units": 1, "urgency": "urgent", "hospital": "Victoria Hospital", "lat": 12.9634, "lon": 77.5737}).json()
    first_wave = {m["id"] for m in req["matches"]}
    admin_h = login(client, "9999999999")
    r = client.post(f"/api/admin/simulate-expiry/{req['id']}", headers=admin_h).json()
    assert r["expired"] == len(first_wave)
    view = client.get(f"/api/requests/{req['id']}", headers=req_h).json()
    assert view["wave"] >= 2 or any(e["type"] == "no_donors" for e in view["events"])
    assert any(e["type"] == "alert_expired" for e in view["events"])


def test_fraud_report_and_suspend(client):
    req_h = login(client, "9123456782")
    accounts = client.get("/api/demo/accounts").json()
    victim = next(a for a in accounts if a["role"] == "donor")
    rep = client.post("/api/reports", headers=req_h, json={"reported_user_id": victim["id"], "reason": "payment_demand",
                                                           "details": "asked for 2000 rupees"})
    assert rep.status_code == 200
    admin_h = login(client, "9999999999")
    assert client.get("/api/admin/reports", headers=admin_h).json()[0]["reason"] == "payment_demand"
    assert client.post(f"/api/admin/users/{victim['id']}/suspend", headers=admin_h, json={"suspend": True}).json()["suspended"]
    tok = client.post(f"/api/demo/login/{victim['id']}").json()["token"]
    assert client.get("/api/donors/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    assert client.get("/api/admin/overview", headers=req_h).status_code == 403


def test_admin_overview(client):
    admin_h = login(client, "9999999999")
    o = client.get("/api/admin/overview", headers=admin_h).json()
    assert o["kpis"]["total_requests"] >= 2 and o["kpis"]["donors_total"] >= 30


def test_duplicate_request_is_not_re_broadcast(client):
    h = login(client, "9123499999")
    body = {"blood_group": "A+", "units": 1, "urgency": "urgent", "hospital": "St. John's Medical College Hospital",
            "lat": 12.9298, "lon": 77.6200}
    first = client.post("/api/requests", headers=h, json=body).json()
    second = client.post("/api/requests", headers=h, json=body).json()
    assert first["id"] == second["id"]
    assert len(second["matches"]) == len(first["matches"])
