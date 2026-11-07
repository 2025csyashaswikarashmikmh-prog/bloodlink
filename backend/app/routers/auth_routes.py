from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import check_otp, current_user, get_or_create_user, issue_otp, make_token, normalize_phone, valid_phone
from ..config import settings
from ..database import get_db
from ..models import DonorProfile, User
from ..schemas import OTPRequest, OTPVerify
from ..voice import _user_view

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/request-otp")
def request_otp(body: OTPRequest):
    phone = normalize_phone(body.phone)
    if not valid_phone(phone):
        raise HTTPException(422, "Enter a valid 10-digit Indian mobile number")
    otp = issue_otp(phone)
    # In production the OTP goes out by SMS; DEMO_MODE returns it so the expo demo needs no SMS gateway.
    return {"sent": True, **({"demo_otp": otp} if settings.DEMO_MODE else {})}


@router.post("/verify-otp")
def verify_otp(body: OTPVerify, db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    if not check_otp(phone, body.otp):
        raise HTTPException(401, "Invalid or expired OTP")
    user = get_or_create_user(db, phone, body.lang)
    if body.name and not user.full_name:
        user.full_name = body.name.strip()[:120]
    user.preferred_language = body.lang
    db.commit()
    return {"token": make_token(user), "user": _user_view(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user_view(user)


demo = APIRouter(prefix="/api/demo", tags=["demo"])


@demo.get("/accounts")
def demo_accounts(db: Session = Depends(get_db)):
    """Seeded accounts for the expo demo (only when DEMO_MODE=true)."""
    if not settings.DEMO_MODE:
        raise HTTPException(404)
    rows = db.query(User).outerjoin(DonorProfile).filter(User.phone.like("90000%") | User.role.in_(["admin", "staff"])).limit(40).all()
    return [{"id": u.id, "name": u.full_name, "phone": u.phone, "role": u.role,
             "blood_group": u.donor.blood_group if u.donor else None, "area": u.donor.area if u.donor else None,
             "status": u.donor.availability_status if u.donor else None} for u in rows]


@demo.post("/login/{user_id}")
def demo_login(user_id: str, db: Session = Depends(get_db)):
    if not settings.DEMO_MODE:
        raise HTTPException(404)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "No such user")
    return {"token": make_token(user), "user": _user_view(user)}
