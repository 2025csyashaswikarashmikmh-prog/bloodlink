"""SQLAlchemy ORM models."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="requester")  # requester | donor | staff | admin
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    donor: Mapped["DonorProfile | None"] = relationship(back_populates="user", uselist=False)


class DonorProfile(Base):
    __tablename__ = "donor_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    blood_group: Mapped[str] = mapped_column(String(3), index=True)
    gender: Mapped[str] = mapped_column(String(1), default="M")  # M | F (drives cooldown 90/120 days)
    city: Mapped[str] = mapped_column(String(60), default="Bengaluru")
    area: Mapped[str] = mapped_column(String(80), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    last_donation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    availability_status: Mapped[str] = mapped_column(String(15), default="available")  # available|busy|unavailable
    reliability_score: Mapped[float] = mapped_column(Float, default=70.0)
    total_donations: Mapped[int] = mapped_column(Integer, default=0)
    times_notified: Mapped[int] = mapped_column(Integer, default=0)
    times_accepted: Mapped[int] = mapped_column(Integer, default=0)
    times_no_show: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    user: Mapped[User] = relationship(back_populates="donor")


class BloodRequest(Base):
    __tablename__ = "blood_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    patient_name: Mapped[str] = mapped_column(String(120), default="")
    blood_group: Mapped[str] = mapped_column(String(3))
    units_needed: Mapped[int] = mapped_column(Integer, default=1)
    urgency: Mapped[str] = mapped_column(String(10), default="urgent")  # normal|urgent|critical
    hospital_name: Mapped[str] = mapped_column(String(160))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    area_zone: Mapped[str] = mapped_column(String(10), default="central")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending -> searching -> donor_committed -> fulfilled | unfulfilled | cancelled
    current_radius_km: Mapped[float] = mapped_column(Float, default=5)
    wave: Mapped[int] = mapped_column(Integer, default=0)
    units_fulfilled: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(5), default="en")
    created_via: Mapped[str] = mapped_column(String(10), default="form")  # form | voice
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    requester: Mapped[User] = relationship()
    matches: Mapped[list["DonorMatch"]] = relationship(back_populates="request", order_by="DonorMatch.rank")
    events: Mapped[list["RequestEvent"]] = relationship(back_populates="request", order_by="RequestEvent.created_at")


class DonorMatch(Base):
    __tablename__ = "donor_matches"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("blood_requests.id"), index=True)
    donor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    wave: Mapped[int] = mapped_column(Integer, default=1)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    exact_match: Mapped[bool] = mapped_column(Boolean, default=False)
    distance_km: Mapped[float] = mapped_column(Float)
    accept_probability: Mapped[float] = mapped_column(Float)
    priority_score: Mapped[float] = mapped_column(Float)
    score_source: Mapped[str] = mapped_column(String(12), default="ml")  # ml | heuristic
    noshow_risk: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="notified")
    # notified | accepted | declined | expired | checked_in | donated | no_show | cancelled
    notified_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    commitment_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checkin_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    checkin_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)

    request: Mapped[BloodRequest] = relationship(back_populates="matches")
    donor: Mapped[User] = relationship()


class RequestEvent(Base):
    __tablename__ = "request_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("blood_requests.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    actor: Mapped[str] = mapped_column(String(40), default="system")
    message: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    request: Mapped[BloodRequest] = relationship(back_populates="events")


class FraudReport(Base):
    __tablename__ = "fraud_reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reported_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(String(30))  # payment_demand|fake_profile|harassment|no_show|other
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="open")  # open | actioned | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class BloodBank(Base):
    __tablename__ = "blood_banks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(240), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    stock: Mapped[dict] = mapped_column(JSON, default=dict)  # {"A+": 4, ...}
    stock_updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
