"""OTP login + JWT auth + role guards."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .store import store

PHONE_RE = re.compile(r"^[6-9]\d{9}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(phone))


def issue_otp(phone: str) -> str:
    if store.incr(f"otp_rate:{phone}", ttl=600) > 5:
        raise HTTPException(429, "Too many OTP requests. Try again in 10 minutes.")
    otp = f"{secrets.randbelow(900000) + 100000}"
    store.set(f"otp:{phone}", {"otp": otp, "tries": 0}, ttl=300)
    return otp


def check_otp(phone: str, otp: str) -> bool:
    rec = store.get(f"otp:{phone}")
    if not rec:
        return False
    if rec["tries"] >= 5:
        store.delete(f"otp:{phone}")
        return False
    if secrets.compare_digest(rec["otp"], (otp or "").strip()):
        store.delete(f"otp:{phone}")
        return True
    rec["tries"] += 1
    store.set(f"otp:{phone}", rec, ttl=300)
    return False


def get_or_create_user(db: Session, phone: str, lang: str = "en") -> User:
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        user = User(phone=phone, preferred_language=lang, role="admin" if phone in settings.ADMIN_PHONES else "requester")
        db.add(user)
        db.commit()
    return user


def make_token(user: User) -> str:
    payload = {
        "sub": user.id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    data = decode_token(token) if token else None
    if not data:
        raise HTTPException(401, "Login required")
    user = db.get(User, data["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    if user.is_suspended:
        raise HTTPException(403, "Account suspended after a fraud report. Contact the admin.")
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return user

    return dep


def mask_phone(phone: str) -> str:
    return f"{phone[:2]}******{phone[-2:]}" if phone and len(phone) >= 4 else "****"
