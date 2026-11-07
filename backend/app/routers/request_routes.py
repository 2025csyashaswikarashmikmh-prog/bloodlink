from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..auth import current_user, decode_token
from ..database import get_db
from ..matching import (OPEN_REQUEST, accept_match, checkin_match, confirm_donation, decline_match, log_event,
                        match_view_for_donor, nearest_blood_banks, request_view, run_wave)
from ..models import BloodRequest, DonorMatch, User
from ..schemas import CheckIn, RequestCreate
from ..services import create_request

router = APIRouter(prefix="/api", tags=["requests"])


def optional_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User | None:
    data = decode_token(authorization.removeprefix("Bearer ").strip()) if authorization else None
    return db.get(User, data["sub"]) if data else None


@router.post("/requests")
def create(body: RequestCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    req = create_request(db, user, blood_group=body.blood_group, units=body.units, urgency=body.urgency,
                         hospital=body.hospital, lat=body.lat, lon=body.lon, patient_name=body.patient_name,
                         language=body.language, via="form")
    return request_view(req, user)


@router.get("/requests/mine")
def mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    reqs = db.query(BloodRequest).filter(BloodRequest.requester_id == user.id).order_by(BloodRequest.created_at.desc()).all()
    return [{"id": r.id, "blood_group": r.blood_group, "units_needed": r.units_needed, "units_fulfilled": r.units_fulfilled,
             "hospital_name": r.hospital_name, "status": r.status, "urgency": r.urgency, "created_at": r.created_at.isoformat() + "Z"} for r in reqs]


@router.get("/requests/{request_id}")
def get_request(request_id: str, viewer: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    req = db.get(BloodRequest, request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    data = request_view(req, viewer)
    data["blood_banks"] = nearest_blood_banks(db, req, 3)
    return data


def _owned(db: Session, request_id: str, user: User) -> BloodRequest:
    req = db.get(BloodRequest, request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    if req.requester_id != user.id and user.role not in {"admin", "staff"}:
        raise HTTPException(403, "Only the requester or staff can do this")
    return req


@router.post("/requests/{request_id}/cancel")
def cancel(request_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    req = _owned(db, request_id, user)
    if req.status not in OPEN_REQUEST:
        raise HTTPException(409, f"Request is already {req.status}")
    req.status = "cancelled"
    for m in req.matches:
        if m.status in {"notified", "accepted"}:
            m.status = "cancelled"
    log_event(db, req, "cancelled", "Request cancelled by requester.", actor=user.id)
    db.commit()
    return request_view(req, user)


@router.post("/requests/{request_id}/escalate")
def escalate(request_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    req = _owned(db, request_id, user)
    log_event(db, req, "escalated", "Manual escalation requested.", actor=user.id)
    db.commit()
    created = run_wave(db, req)
    db.refresh(req)
    return {"notified": len(created), "request": request_view(req, user)}


def _match(db: Session, match_id: str) -> DonorMatch:
    m = db.get(DonorMatch, match_id)
    if not m:
        raise HTTPException(404, "Alert not found")
    return m


def _own_match(db: Session, match_id: str, user: User) -> DonorMatch:
    m = _match(db, match_id)
    if m.donor_id != user.id:
        raise HTTPException(403, "This alert belongs to another donor")
    return m


@router.post("/matches/{match_id}/accept")
def accept(match_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own_match(db, match_id, user)
    try:
        accept_match(db, m, user)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return match_view_for_donor(m)


@router.post("/matches/{match_id}/decline")
def decline(match_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own_match(db, match_id, user)
    try:
        decline_match(db, m, user)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return match_view_for_donor(m)


@router.post("/matches/{match_id}/checkin")
def checkin(match_id: str, body: CheckIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _own_match(db, match_id, user)
    try:
        checkin_match(db, m, body.lat, body.lon)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return match_view_for_donor(m)


@router.post("/matches/{match_id}/confirm")
def confirm(match_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Requester or blood-centre staff confirms the donation actually happened."""
    m = _match(db, match_id)
    if m.request.requester_id != user.id and user.role not in {"admin", "staff"}:
        raise HTTPException(403, "Only the requester or staff can confirm a donation")
    try:
        confirm_donation(db, m, user)
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.refresh(m.request)
    return request_view(m.request, user)
