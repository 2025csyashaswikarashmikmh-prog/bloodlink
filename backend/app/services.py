"""Shared business operations used by REST routes and the voice assistant."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from .blood import BLOOD_GROUPS, RECIPIENT_CAN_RECEIVE_FROM, zone_for
from .matching import OPEN_REQUEST, log_event, run_wave
from .models import BloodRequest, DonorProfile, User


def groups_donor_can_help(bg: str) -> list[str]:
    return [r for r, donors in RECIPIENT_CAN_RECEIVE_FROM.items() if bg in donors]


def create_request(db: Session, user: User, *, blood_group: str, units: int, urgency: str, hospital: str,
                   lat: float, lon: float, patient_name: str = "", language: str = "en", via: str = "form") -> BloodRequest:
    if blood_group not in BLOOD_GROUPS:
        raise ValueError("Invalid blood group")
    # Anti-spam: the same requester re-submitting the same need returns the open request instead of re-alerting donors.
    existing = db.query(BloodRequest).filter(
        BloodRequest.requester_id == user.id, BloodRequest.blood_group == blood_group,
        BloodRequest.hospital_name == hospital[:160], BloodRequest.status.in_(OPEN_REQUEST),
    ).first()
    if existing:
        return existing
    req = BloodRequest(
        requester_id=user.id, blood_group=blood_group, units_needed=max(1, min(int(units), 10)), urgency=urgency,
        hospital_name=hospital[:160], latitude=lat, longitude=lon, area_zone=zone_for(lat, lon),
        patient_name=patient_name[:120], language=language, created_via=via, current_radius_km=5,
    )
    db.add(req)
    db.flush()
    log_event(db, req, "created",
              f"Request created via {via}: {req.units_needed} unit(s) {blood_group}, {urgency}, at {req.hospital_name}",
              actor=user.id, meta={"language": language})
    db.commit()
    run_wave(db, req)
    db.refresh(req)
    return req


def register_donor(db: Session, user: User, *, name: str, blood_group: str, gender: str, last_donation: date | None,
                   lat: float, lon: float, area: str = "", language: str | None = None) -> DonorProfile:
    if blood_group not in BLOOD_GROUPS:
        raise ValueError("Invalid blood group")
    if name:
        user.full_name = name
    if language:
        user.preferred_language = language
    if user.role == "requester":
        user.role = "donor"
    p = user.donor or DonorProfile(user_id=user.id, blood_group=blood_group, latitude=lat, longitude=lon)
    p.blood_group, p.gender, p.last_donation_date = blood_group, gender, last_donation
    p.latitude, p.longitude, p.area = lat, lon, area
    p.availability_status = "available"
    db.add(p)
    db.commit()
    db.refresh(user)
    return p
