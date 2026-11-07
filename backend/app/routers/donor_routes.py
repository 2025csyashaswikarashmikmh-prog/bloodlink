from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import current_user
from ..blood import cooldown_days, in_cooldown, next_eligible_date
from ..database import get_db
from ..matching import match_view_for_donor
from ..models import DonorMatch, User
from ..schemas import Availability, DonorRegister
from ..services import groups_donor_can_help, register_donor

router = APIRouter(prefix="/api/donors", tags=["donors"])


def profile_view(u: User) -> dict:
    p = u.donor
    if not p:
        return {"registered": False}
    return {
        "registered": True, "name": u.full_name, "phone": u.phone, "blood_group": p.blood_group, "gender": p.gender,
        "area": p.area, "lat": p.latitude, "lon": p.longitude, "availability": p.availability_status,
        "reliability": p.reliability_score, "total_donations": p.total_donations,
        "last_donation_date": str(p.last_donation_date) if p.last_donation_date else None,
        "in_cooldown": in_cooldown(p.last_donation_date, p.gender), "cooldown_days": cooldown_days(p.gender),
        "next_eligible": str(next_eligible_date(p.last_donation_date, p.gender) or "") or None,
        "can_help": groups_donor_can_help(p.blood_group),
        "stats": {"notified": p.times_notified, "accepted": p.times_accepted, "no_show": p.times_no_show},
    }


@router.post("/register")
def register(body: DonorRegister, user: User = Depends(current_user), db: Session = Depends(get_db)):
    register_donor(db, user, name=body.name, blood_group=body.blood_group, gender=body.gender,
                   last_donation=body.last_donation_date, lat=body.lat, lon=body.lon, area=body.area)
    if body.telegram_chat_id:
        user.telegram_chat_id = body.telegram_chat_id
        db.commit()
    return profile_view(user)


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    data = profile_view(user)
    if data["registered"]:
        matches = (db.query(DonorMatch).filter(DonorMatch.donor_id == user.id)
                   .order_by(DonorMatch.notified_at.desc()).limit(20).all())
        data["matches"] = [match_view_for_donor(m) for m in matches]
    return data


@router.patch("/availability")
def availability(body: Availability, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.donor:
        raise HTTPException(400, "Register as a donor first")
    if body.status == "available" and in_cooldown(user.donor.last_donation_date, user.donor.gender):
        raise HTTPException(409, f"You are in the safe-gap period until {next_eligible_date(user.donor.last_donation_date, user.donor.gender)}")
    user.donor.availability_status = body.status
    db.commit()
    return profile_view(user)
