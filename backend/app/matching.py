"""Matching + escalation engine.

Pipeline for each request "wave":
  1. hard filters  - compatible blood group, available, not in cooldown, not suspended, within radius
  2. ML scoring    - ml-service predicts P(accept); falls back to a heuristic if the service is down
  3. priority      - blend of ML probability, distance, reliability and exact-group bonus
  4. notify top-N  - in-app WebSocket push (+ optional Telegram)
  5. escalation    - unanswered alerts expire, no-shows are penalised, next wave widens the radius
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from .auth import mask_phone
from .blood import URGENCY_LEVEL, compatible_donor_groups, haversine_km, in_cooldown, next_eligible_date
from .config import settings
from .models import BloodBank, BloodRequest, DonorMatch, DonorProfile, RequestEvent, User, now
from .notify import notify_user
from .realtime import hub

ACTIVE_MATCH = {"notified", "accepted", "checked_in"}
COMMITTED = {"accepted", "checked_in"}
OPEN_REQUEST = {"pending", "searching", "donor_committed"}


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


# ---------------------------------------------------------------- events
def log_event(db: Session, req: BloodRequest, event_type: str, message: str, actor: str = "system", meta: dict | None = None):
    ev = RequestEvent(request_id=req.id, event_type=event_type, message=message, actor=actor, meta=meta or {})
    db.add(ev)
    db.flush()
    payload = {"type": "event", "request_id": req.id, "event": event_view(ev), "status": req.status}
    hub.publish(f"request:{req.id}", payload)
    hub.publish("admin", payload)
    return ev


def event_view(ev: RequestEvent) -> dict:
    return {"id": ev.id, "type": ev.event_type, "message": ev.message, "actor": ev.actor, "meta": ev.meta, "at": iso(ev.created_at)}


# ---------------------------------------------------------------- scoring
def donor_features(p: DonorProfile, req: BloodRequest, distance: float) -> dict:
    notified = max(p.times_notified, 1)
    days = (date.today() - p.last_donation_date).days if p.last_donation_date else 365
    return {
        "donor_id": p.user_id,
        "distance_km": distance,
        "exact_match": int(p.blood_group == req.blood_group),
        "days_since_last_donation": max(days, 0),
        "total_donations": p.total_donations,
        "acceptance_rate": round(p.times_accepted / notified, 3) if p.times_notified else 0.6,
        "noshow_rate": round(p.times_no_show / max(p.times_accepted, 1), 3),
        "urgency": URGENCY_LEVEL.get(req.urgency, 1),
        "hour_of_day": datetime.now().hour,
        "reliability_score": p.reliability_score,
    }


def heuristic_probability(f: dict) -> float:
    p = 0.75 - 0.012 * f["distance_km"] + 0.25 * (f["acceptance_rate"] - 0.5) - 0.3 * f["noshow_rate"]
    p += 0.002 * (f["reliability_score"] - 70) + 0.04 * f["urgency"]
    return round(min(max(p, 0.02), 0.98), 4)


def score_candidates(features: list[dict]) -> tuple[dict[str, float], str]:
    if not features:
        return {}, "ml"
    try:
        r = httpx.post(f"{settings.ML_SERVICE_URL}/predict/acceptance", json={"donors": features}, timeout=3)
        r.raise_for_status()
        return {p["donor_id"]: p["accept_probability"] for p in r.json()["predictions"]}, "ml"
    except Exception as e:
        print(f"[matching] ML service unavailable, using heuristic: {e}")
        return {f["donor_id"]: heuristic_probability(f) for f in features}, "heuristic"


def priority(prob: float, distance: float, radius: float, reliability: float, exact: bool) -> float:
    return round(0.55 * prob + 0.20 * max(0.0, 1 - distance / max(radius, 1)) + 0.15 * reliability / 100 + 0.10 * int(exact), 4)


def predict_noshow(match: DonorMatch, profile: DonorProfile, req: BloodRequest) -> str | None:
    delay = (match.responded_at - match.notified_at).total_seconds() / 60 if match.responded_at else 5
    body = {
        "distance_km": match.distance_km,
        "hour_of_day": datetime.now().hour,
        "noshow_rate": round(profile.times_no_show / max(profile.times_accepted, 1), 3),
        "response_delay_min": round(delay, 2),
        "urgency": URGENCY_LEVEL.get(req.urgency, 1),
        "reliability_score": profile.reliability_score,
        "commitment_window_min": settings.COMMITMENT_WINDOW_MIN,
    }
    try:
        r = httpx.post(f"{settings.ML_SERVICE_URL}/predict/noshow", json=body, timeout=3)
        r.raise_for_status()
        return r.json()["risk"]
    except Exception:
        return "high" if body["noshow_rate"] > 0.4 or match.distance_km > 20 else "low"


# ---------------------------------------------------------------- matching waves
def remaining_units(req: BloodRequest) -> int:
    return max(req.units_needed - req.units_fulfilled, 0)


def find_candidates(db: Session, req: BloodRequest, radius: float) -> list[tuple[DonorProfile, float]]:
    already = {m.donor_id for m in req.matches}
    groups = compatible_donor_groups(req.blood_group)
    rows = (
        db.query(DonorProfile)
        .join(User, User.id == DonorProfile.user_id)
        .filter(
            DonorProfile.blood_group.in_(groups),
            DonorProfile.availability_status == "available",
            User.is_suspended.is_(False),
            User.id != req.requester_id,
        )
        .all()
    )
    out = []
    for p in rows:
        if p.user_id in already or in_cooldown(p.last_donation_date, p.gender):
            continue
        # donors already committed to another open request are not double-booked
        busy = (
            db.query(DonorMatch)
            .join(BloodRequest)
            .filter(DonorMatch.donor_id == p.user_id, DonorMatch.status.in_(COMMITTED), BloodRequest.status.in_(OPEN_REQUEST))
            .first()
        )
        if busy:
            continue
        d = haversine_km(req.latitude, req.longitude, p.latitude, p.longitude)
        if d <= radius:
            out.append((p, d))
    return out


def run_wave(db: Session, req: BloodRequest) -> list[DonorMatch]:
    """Notify the next batch of best donors, widening the radius if needed."""
    if req.status not in OPEN_REQUEST or remaining_units(req) == 0:
        return []
    radii = [r for r in settings.SEARCH_RADII_KM if r >= req.current_radius_km] or [settings.SEARCH_RADII_KM[-1]]
    n = max(settings.DONORS_PER_WAVE, remaining_units(req) * 2)
    cands, radius = [], radii[0]
    for radius in radii:  # widen the circle until we have a full wave (or run out of radii)
        cands = find_candidates(db, req, radius)
        if len(cands) >= n:
            break
    if not cands:
        req.current_radius_km = settings.SEARCH_RADII_KM[-1]
        if not any(m.status in ACTIVE_MATCH for m in req.matches):
            log_event(
                db, req, "no_donors",
                f"No more eligible donors within {req.current_radius_km:g} km. Showing nearby blood banks as backup.",
                meta={"blood_banks": nearest_blood_banks(db, req, 3)},
            )
        db.commit()
        return []

    if radius > req.current_radius_km:
        log_event(db, req, "radius_expanded", f"Search radius expanded to {radius:g} km", meta={"radius_km": radius})
    req.current_radius_km = radius

    feats = [donor_features(p, req, d) for p, d in cands]
    probs, source = score_candidates(feats)
    scored = sorted(
        ((p, d, probs[p.user_id], priority(probs[p.user_id], d, radius, p.reliability_score, p.blood_group == req.blood_group)) for p, d in cands),
        key=lambda x: -x[3],
    )
    req.wave += 1
    req.status = "searching" if req.status == "pending" else req.status
    created = []
    for rank, (p, d, prob, prio) in enumerate(scored[:n], start=1):
        m = DonorMatch(
            request_id=req.id, donor_id=p.user_id, wave=req.wave, rank=rank, exact_match=p.blood_group == req.blood_group,
            distance_km=d, accept_probability=prob, priority_score=prio, score_source=source,
        )
        db.add(m)
        p.times_notified += 1
        created.append(m)
    db.flush()
    log_event(
        db, req, "donors_notified",
        f"Wave {req.wave}: {len(created)} of {len(scored)} compatible donors alerted (radius {radius:g} km, ranked by {source.upper()})",
        meta={"wave": req.wave, "candidates": len(scored), "notified": len(created), "source": source,
              "top": [{"rank": m.rank, "probability": m.accept_probability, "distance_km": m.distance_km} for m in created]},
    )
    db.commit()
    for m in created:
        donor = db.get(User, m.donor_id)
        notify_user(
            donor, "alert", {"match": match_view_for_donor(m)},
            text=f"RaktaSetu emergency: {req.blood_group} blood needed at {req.hospital_name} ({m.distance_km} km). Open the app to accept.",
        )
    return created


def nearest_blood_banks(db: Session, req: BloodRequest, k: int = 3) -> list[dict]:
    banks = db.query(BloodBank).all()
    groups = compatible_donor_groups(req.blood_group)
    rows = []
    for b in banks:
        units = sum(int(b.stock.get(g, 0)) for g in groups)
        rows.append({"id": b.id, "name": b.name, "phone": b.phone, "lat": b.latitude, "lon": b.longitude, "distance_km": haversine_km(req.latitude, req.longitude, b.latitude, b.longitude), "compatible_units": units})
    rows.sort(key=lambda r: (r["compatible_units"] == 0, r["distance_km"]))
    return rows[:k]


# ---------------------------------------------------------------- donor actions
def _adjust_reliability(p: DonorProfile, delta: float):
    p.reliability_score = round(min(100.0, max(0.0, p.reliability_score + delta)), 1)


def accept_match(db: Session, m: DonorMatch, donor: User) -> DonorMatch:
    req = m.request
    if m.status != "notified":
        raise ValueError(f"This alert is already {m.status}")
    if req.status not in OPEN_REQUEST or remaining_units(req) == 0:
        m.status = "cancelled"
        db.commit()
        raise ValueError("This request has already been fulfilled or closed. Thank you!")
    committed = sum(1 for x in req.matches if x.status in COMMITTED)
    if committed >= remaining_units(req):
        m.status = "cancelled"
        db.commit()
        raise ValueError("Enough donors have already committed. Thank you for responding!")
    p = donor.donor
    m.status, m.responded_at = "accepted", now()
    m.commitment_deadline = m.responded_at + timedelta(minutes=settings.COMMITMENT_WINDOW_MIN)
    p.times_accepted += 1
    _adjust_reliability(p, 2)
    m.noshow_risk = predict_noshow(m, p, req)
    req.status = "donor_committed"
    log_event(
        db, req, "donor_accepted",
        f"{donor.full_name.split(' ')[0] or 'A donor'} ({p.blood_group}, {m.distance_km} km) committed to reach by {m.commitment_deadline.strftime('%H:%M')} UTC. No-show risk: {m.noshow_risk}",
        actor=donor.id, meta={"match_id": m.id, "deadline": iso(m.commitment_deadline), "noshow_risk": m.noshow_risk},
    )
    # if enough donors are committed, withdraw the remaining open alerts
    if sum(1 for x in req.matches if x.status in COMMITTED) >= remaining_units(req):
        for other in req.matches:
            if other.status == "notified":
                other.status = "cancelled"
                notify_user(other.donor, "alert_withdrawn", {"match_id": other.id})
    db.commit()
    return m


def decline_match(db: Session, m: DonorMatch, donor: User):
    if m.status != "notified":
        raise ValueError(f"This alert is already {m.status}")
    m.status, m.responded_at = "declined", now()
    log_event(db, m.request, "donor_declined", f"A donor declined (rank #{m.rank}).", actor=donor.id)
    db.commit()
    maybe_escalate(db, m.request)


def checkin_match(db: Session, m: DonorMatch, lat: float | None, lon: float | None):
    if m.status != "accepted":
        raise ValueError("Check-in is only possible after accepting")
    req = m.request
    m.status, m.checkin_at = "checked_in", now()
    if lat is not None and lon is not None:
        m.checkin_distance_km = haversine_km(lat, lon, req.latitude, req.longitude)
    verified = m.checkin_distance_km is not None and m.checkin_distance_km <= 1.0
    _adjust_reliability(m.donor.donor, 5 if verified else 2)
    where = f"{m.checkin_distance_km} km from hospital" if m.checkin_distance_km is not None else "location not shared"
    log_event(
        db, req, "donor_checked_in",
        f"Donor checked in at the blood centre ({where}){' - location verified' if verified else ''}. Awaiting staff confirmation.",
        actor=m.donor_id, meta={"match_id": m.id, "verified": verified, "distance_km": m.checkin_distance_km},
    )
    db.commit()


def confirm_donation(db: Session, m: DonorMatch, actor: User):
    if m.status not in COMMITTED:
        raise ValueError("Only committed donors can be confirmed")
    req = m.request
    p = m.donor.donor
    m.status = "donated"
    p.total_donations += 1
    p.last_donation_date = date.today()
    p.availability_status = "unavailable"  # automatically enters cooldown
    req.units_fulfilled += 1
    _adjust_reliability(p, 5)
    msg = f"Donation confirmed by {actor.role}. {req.units_fulfilled}/{req.units_needed} units fulfilled."
    if remaining_units(req) == 0:
        req.status = "fulfilled"
        msg += " Request fulfilled."
        for other in req.matches:
            if other.status == "notified":
                other.status = "cancelled"
    log_event(db, req, "donation_confirmed", msg, actor=actor.id,
              meta={"match_id": m.id, "next_eligible": str(next_eligible_date(p.last_donation_date, p.gender))})
    db.commit()
    notify_user(m.donor, "thank_you", {"match_id": m.id, "next_eligible": str(next_eligible_date(p.last_donation_date, p.gender))},
                text="Thank you for donating blood through RaktaSetu. You just helped save a life.")
    if req.status != "fulfilled":
        maybe_escalate(db, req)


# ---------------------------------------------------------------- escalation
def maybe_escalate(db: Session, req: BloodRequest):
    db.refresh(req)
    if req.status not in OPEN_REQUEST:
        return
    committed = sum(1 for m in req.matches if m.status in COMMITTED)
    pending = sum(1 for m in req.matches if m.status == "notified")
    if committed >= remaining_units(req):
        return
    if pending == 0:
        if committed == 0:
            req.status = "searching"
        log_event(db, req, "escalated", "No pending responses - escalating to the next donors.")
        db.commit()
        run_wave(db, req)


def escalation_tick(db: Session) -> dict:
    """Called periodically by the background worker."""
    t = now()
    expired = no_shows = 0
    touched: set[str] = set()
    for m in db.query(DonorMatch).filter(DonorMatch.status == "notified").all():
        if (t - m.notified_at).total_seconds() > settings.RESPONSE_WINDOW_SEC:
            m.status = "expired"
            _adjust_reliability(m.donor.donor, -1)
            log_event(db, m.request, "alert_expired", f"Alert to donor rank #{m.rank} expired after {settings.RESPONSE_WINDOW_SEC}s without response.")
            notify_user(m.donor, "alert_withdrawn", {"match_id": m.id})
            expired += 1
            touched.add(m.request_id)
    for m in db.query(DonorMatch).filter(DonorMatch.status == "accepted").all():
        if m.commitment_deadline and t > m.commitment_deadline:
            m.status = "no_show"
            p = m.donor.donor
            p.times_no_show += 1
            _adjust_reliability(p, -15)
            log_event(db, m.request, "no_show", "Committed donor did not check in before the deadline - marked NO-SHOW, reliability reduced.",
                      meta={"match_id": m.id})
            no_shows += 1
            touched.add(m.request_id)
    db.commit()
    for rid in touched:
        req = db.get(BloodRequest, rid)
        if req:
            maybe_escalate(db, req)
    return {"expired": expired, "no_shows": no_shows}


# ---------------------------------------------------------------- views (privacy-aware)
def match_view_for_donor(m: DonorMatch) -> dict:
    req = m.request
    reveal = m.status in COMMITTED | {"donated"}
    return {
        "match_id": m.id, "status": m.status, "request_id": req.id, "blood_group": req.blood_group, "units": req.units_needed,
        "urgency": req.urgency, "hospital": req.hospital_name, "lat": req.latitude, "lon": req.longitude,
        "distance_km": m.distance_km, "notified_at": iso(m.notified_at), "commitment_deadline": iso(m.commitment_deadline),
        "expires_at": iso(m.notified_at + timedelta(seconds=settings.RESPONSE_WINDOW_SEC)),
        "requester_name": req.requester.full_name or "Family member",
        "requester_phone": req.requester.phone if reveal else mask_phone(req.requester.phone),
        "patient_name": req.patient_name,
    }


def request_view(req: BloodRequest, viewer: User | None) -> dict:
    is_owner = viewer is not None and viewer.id == req.requester_id
    is_staff = viewer is not None and viewer.role in {"admin", "staff"}
    matches = []
    for m in req.matches:
        reveal = (is_owner or is_staff) and m.status in COMMITTED | {"donated"}
        matches.append({
            "id": m.id, "rank": m.rank, "wave": m.wave, "status": m.status, "distance_km": m.distance_km,
            "blood_group": m.donor.donor.blood_group if m.donor.donor else "?", "exact_match": m.exact_match,
            "accept_probability": m.accept_probability, "priority_score": m.priority_score, "score_source": m.score_source,
            "noshow_risk": m.noshow_risk, "reliability": m.donor.donor.reliability_score if m.donor.donor else None,
            "donor_name": (m.donor.full_name.split(" ")[0] if m.donor.full_name else "Donor") if reveal or is_staff else f"Donor #{m.rank}",
            "donor_phone": m.donor.phone if reveal else mask_phone(m.donor.phone),
            "donor_user_id": m.donor_id if reveal or is_staff else None,
            "commitment_deadline": iso(m.commitment_deadline), "checkin_at": iso(m.checkin_at),
            "checkin_distance_km": m.checkin_distance_km,
        })
    return {
        "id": req.id, "blood_group": req.blood_group, "compatible_groups": compatible_donor_groups(req.blood_group),
        "units_needed": req.units_needed, "units_fulfilled": req.units_fulfilled, "urgency": req.urgency,
        "hospital_name": req.hospital_name, "lat": req.latitude, "lon": req.longitude, "status": req.status,
        "radius_km": req.current_radius_km, "wave": req.wave, "patient_name": req.patient_name,
        "created_via": req.created_via, "language": req.language, "created_at": iso(req.created_at),
        "requester": {"name": req.requester.full_name, "phone": req.requester.phone if (is_owner or is_staff) else mask_phone(req.requester.phone)},
        "is_owner": is_owner, "matches": matches, "events": [event_view(e) for e in req.events],
    }
