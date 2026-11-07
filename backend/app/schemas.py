from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


class OTPRequest(BaseModel):
    phone: str


class OTPVerify(BaseModel):
    phone: str
    otp: str
    lang: str = "en"
    name: str = ""


class DonorRegister(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    blood_group: BloodGroup
    gender: Literal["M", "F"] = "M"
    last_donation_date: date | None = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    area: str = ""
    telegram_chat_id: str | None = None


class Availability(BaseModel):
    status: Literal["available", "busy", "unavailable"]


class RequestCreate(BaseModel):
    blood_group: BloodGroup
    units: int = Field(ge=1, le=10)
    urgency: Literal["normal", "urgent", "critical"] = "urgent"
    hospital: str = Field(min_length=2, max_length=160)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    patient_name: str = ""
    language: str = "en"


class CheckIn(BaseModel):
    lat: float | None = None
    lon: float | None = None


class VoiceTurn(BaseModel):
    session_id: str | None = None
    lang: str = "en"
    text: str = ""
    lat: float | None = None
    lon: float | None = None


class ReportCreate(BaseModel):
    reported_user_id: str
    request_id: str | None = None
    reason: Literal["payment_demand", "fake_profile", "harassment", "no_show", "other"]
    details: str = Field(default="", max_length=1000)


class Suspend(BaseModel):
    suspend: bool = True


class StockUpdate(BaseModel):
    stock: dict[str, int]
