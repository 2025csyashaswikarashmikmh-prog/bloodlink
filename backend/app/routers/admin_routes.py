from collections import Counter
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import current_user, require_roles
from ..blood import BLOOD_GROUPS, haversine_km
from ..config import settings
from ..database import get_db
from ..matching import escalation_tick, iso
from ..models import BloodBank, BloodRequest, DonorMatch, DonorProfile, FraudReport, RequestEvent, User, now
from ..schemas import ReportCreate, StockUpdate, Suspend

router = APIRouter(prefix="/api/admin", tags=["admin"])
staff_only = require_roles("admin", "staff")
admin_only = require_roles("admin")


@router.get("/overview")
def overview(_: User = Depends(staff_only), db: Session = Depends(get_db)):
    reqs = db.query(BloodRequest).order_by(BloodRequest.created_at.desc()).all()
    matches = db.query(DonorMatch).all()
    donors = db.query(DonorProfile).all()
    responded = [m for m in matches if m.responded_at]
    accepted = [m for m in matches if m.status in {"accepted", "checked_in", "donated", "no_show"}]
    resp_secs = [(m.responded_at - m.notified_at).total_seconds() for m in accepted if m.responded_at]
    status_counts = Counter(r.status for r in reqs)
    events = db.query(RequestEvent).order_by(RequestEvent.created_at.desc()).limit(25).all()
    return {
        "kpis": {
            "open_requests": sum(status_counts[s] for s in ("pending", "searching", "donor_committed")),
            "fulfilled": status_counts["fulfilled"],
            "total_requests": len(reqs),
            "donors_total": len(donors),
            "donors_available": sum(1 for d in donors if d.availability_status == "available"),
            "acceptance_rate": round(len(accepted) / len(matches), 3) if matches else 0,
            "avg_response_sec": round(sum(resp_secs) / len(resp_secs), 1) if resp_secs else None,
            "no_show_rate": round(sum(1 for m in matches if m.status == "no_show") / len(accepted), 3) if accepted else 0,
            "voice_share": round(sum(1 for r in reqs if r.created_via == "voice") / len(reqs), 3) if reqs else 0,
            "open_reports": db.query(FraudReport).filter(FraudReport.status == "open").count(),
            "responded": len(responded),
        },
        "status_counts": dict(status_counts),
        "requests_by_group": {g: sum(1 for r in reqs if r.blood_group == g) for g in BLOOD_GROUPS},
        "donors_by_group": {g: sum(1 for d in donors if d.blood_group == g) for g in BLOOD_GROUPS},
        "requests": [{"id": r.id, "blood_group": r.blood_group, "units": r.units_needed, "fulfilled": r.units_fulfilled,
                      "urgency": r.urgency, "hospital": r.hospital_name, "status": r.status, "via": r.created_via,
                      "lang": r.language, "radius_km": r.current_radius_km, "wave": r.wave, "created_at": iso(r.created_at),
                      "lat": r.latitude, "lon": r.longitude} for r in reqs[:50]],
        "events": [{"request_id": e.request_id, "type": e.event_type, "message": e.message, "at": iso(e.created_at)} for e in events],
        "donor_points": [{"lat": d.latitude, "lon": d.longitude, "bg": d.blood_group, "status": d.availability_status} for d in donors],
    }


@router.get("/donors")
def donors(_: User = Depends(staff_only), db: Session = Depends(get_db)):
    rows = db.query(DonorProfile).join(User).order_by(DonorProfile.reliability_score.desc()).all()
    return [{"id": d.user_id, "name": d.user.full_name, "blood_group": d.blood_group, "area": d.area,
             "availability": d.availability_status, "reliability": d.reliability_score, "donations": d.total_donations,
             "no_shows": d.times_no_show, "suspended": d.user.is_suspended} for d in rows]


@router.get("/forecast")
def forecast(area: str = "central", days: int = 7, _: User = Depends(staff_only)):
    try:
        r = httpx.get(f"{settings.ML_SERVICE_URL}/forecast", params={"area": area, "days": days}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(503, f"ML service unavailable: {e}")


@router.get("/model-info")
def model_info(_: User = Depends(staff_only)):
    try:
        return httpx.get(f"{settings.ML_SERVICE_URL}/model-info", timeout=5).json()
    except Exception as e:
        raise HTTPException(503, f"ML service unavailable: {e}")


@router.post("/tick")
def tick(_: User = Depends(staff_only), db: Session = Depends(get_db)):
    """Run one escalation cycle immediately (useful during the live demo)."""
    return escalation_tick(db)


@router.post("/simulate-expiry/{request_id}")
def simulate_expiry(request_id: str, _: User = Depends(staff_only), db: Session = Depends(get_db)):
    """Demo helper: age all open alerts of a request so the next tick expires them and escalates."""
    req = db.get(BloodRequest, request_id)
    if not req:
        raise HTTPException(404)
    for m in req.matches:
        if m.status == "notified":
            m.notified_at = now() - timedelta(seconds=settings.RESPONSE_WINDOW_SEC + 5)
        if m.status == "accepted" and m.commitment_deadline:
            m.commitment_deadline = now() - timedelta(seconds=1)
    db.commit()
    return escalation_tick(db)


@router.get("/reports")
def reports(_: User = Depends(staff_only), db: Session = Depends(get_db)):
    rows = db.query(FraudReport).order_by(FraudReport.created_at.desc()).all()
    out = []
    for r in rows:
        u = db.get(User, r.reported_user_id)
        out.append({"id": r.id, "reason": r.reason, "details": r.details, "status": r.status, "request_id": r.request_id,
                    "reported_user": {"id": u.id, "name": u.full_name, "suspended": u.is_suspended} if u else None,
                    "created_at": iso(r.created_at)})
    return out


@router.post("/users/{user_id}/suspend")
def suspend(user_id: str, body: Suspend, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    u.is_suspended = body.suspend
    if u.donor and body.suspend:
        u.donor.availability_status = "unavailable"
    for r in db.query(FraudReport).filter(FraudReport.reported_user_id == user_id, FraudReport.status == "open"):
        r.status = "actioned" if body.suspend else "dismissed"
    db.commit()
    return {"id": u.id, "suspended": u.is_suspended}


public = APIRouter(prefix="/api", tags=["public"])


@public.post("/reports")
def create_report(body: ReportCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.get(User, body.reported_user_id):
        raise HTTPException(404, "Reported user not found")
    r = FraudReport(reporter_id=user.id, reported_user_id=body.reported_user_id, request_id=body.request_id,
                    reason=body.reason, details=body.details)
    db.add(r)
    db.commit()
    return {"id": r.id, "status": r.status}


@public.get("/blood-banks")
def blood_banks(lat: float = 12.9716, lon: float = 77.5946, db: Session = Depends(get_db)):
    rows = db.query(BloodBank).all()
    out = [{"id": b.id, "name": b.name, "address": b.address, "phone": b.phone, "lat": b.latitude, "lon": b.longitude,
            "stock": b.stock, "stock_updated_at": iso(b.stock_updated_at), "is_demo": b.is_demo,
            "distance_km": haversine_km(lat, lon, b.latitude, b.longitude)} for b in rows]
    return sorted(out, key=lambda x: x["distance_km"])


@public.patch("/blood-banks/{bank_id}/stock")
def update_stock(bank_id: str, body: StockUpdate, _: User = Depends(staff_only), db: Session = Depends(get_db)):
    b = db.get(BloodBank, bank_id)
    if not b:
        raise HTTPException(404)
    b.stock = {g: max(0, int(body.stock.get(g, b.stock.get(g, 0)))) for g in BLOOD_GROUPS}
    b.stock_updated_at = now()
    db.commit()
    return {"id": b.id, "stock": b.stock}
