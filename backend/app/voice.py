"""Voice-first, multilingual task assistant (dialogue manager).

The browser does speech-to-text and text-to-speech; this module receives the
transcribed text, fills slots one question at a time, confirms, and then performs
real actions (OTP login, create blood request, register donor, track request).
"""
from __future__ import annotations

import secrets
from datetime import date

from sqlalchemy.orm import Session

from . import nlu
from .auth import check_otp, get_or_create_user, issue_otp, make_token, mask_phone, normalize_phone, valid_phone
from .blood import BENGALURU_CENTER, BLOOD_GROUPS, HOSPITALS, find_area, find_hospital, in_cooldown, next_eligible_date
from .config import settings
from .i18n import LANGS, STATUS_LABELS, label, t
from .models import BloodRequest, User
from .services import create_request, groups_donor_can_help, register_donor
from .store import store

SESSION_TTL = 3600
LOCATION_TOKEN = "__location__"


def _chips(lang: str, *keys: str) -> list[dict]:
    return [{"label": label(k, lang), "value": k} for k in keys]


def _bg_chips() -> list[dict]:
    return [{"label": g, "value": g} for g in BLOOD_GROUPS]


def _user_view(u: User) -> dict:
    return {"id": u.id, "name": u.full_name, "phone": u.phone, "role": u.role, "lang": u.preferred_language,
            "is_donor": u.donor is not None}


class Assistant:
    def __init__(self, db: Session, session_id: str | None, lang: str, user: User | None):
        self.db = db
        self.sid = session_id or secrets.token_hex(8)
        self.lang = lang if lang in LANGS else "en"
        self.state = store.get(f"voice:{self.sid}") or {"step": None, "slots": {}, "user_id": None}
        self.user = user or (db.get(User, self.state["user_id"]) if self.state.get("user_id") else None)
        if self.user:
            self.state["user_id"] = self.user.id
        self.out: dict = {}

    # ------------------------------------------------------------ helpers
    def save(self):
        store.set(f"voice:{self.sid}", self.state, ttl=SESSION_TTL)

    def reply(self, text: str, step: str, chips: list[dict] | None = None, input_hint: str = "text", **extra) -> dict:
        self.state["step"] = step
        self.save()
        return {"session_id": self.sid, "lang": self.lang, "reply": text, "step": step, "chips": chips or [],
                "input_hint": input_hint, "slots": self.state["slots"], **self.out, **extra}

    def ask_intent(self, prefix: str = "") -> dict:
        self.state["slots"] = {}
        key = "welcome_back" if self.user and self.user.full_name else "logged_in"
        text = prefix + t(key, self.lang, name=(self.user.full_name if self.user else ""))
        return self.reply(text, "ask_intent", _chips(self.lang, "need", "donate", "track"))

    # ------------------------------------------------------------ entry
    def turn(self, text: str, lat: float | None, lon: float | None) -> dict:
        text = (text or "").strip()
        if lat is not None and lon is not None:
            self.state["last_coords"] = [lat, lon]
        step = self.state.get("step")

        if not text or text == "__start__" or step is None or nlu.extract_intent(text) == "restart":
            if self.user:
                return self.ask_intent()
            self.state["slots"] = {}
            return self.reply(t("welcome", self.lang), "ask_phone", input_hint="phone")

        handler = getattr(self, f"on_{step}", None)
        if handler is None:
            return self.ask_intent()
        return handler(text, lat, lon)

    # ------------------------------------------------------------ login
    def on_ask_phone(self, text, lat, lon):
        phone = normalize_phone(nlu.extract_digits(text))
        if not valid_phone(phone):
            return self.reply(t("bad_phone", self.lang), "ask_phone", input_hint="phone")
        otp = issue_otp(phone)
        self.state["phone"] = phone
        extra = {"demo_otp": otp} if settings.DEMO_MODE else {}
        return self.reply(t("otp_sent", self.lang, phone=mask_phone(phone)), "ask_otp", input_hint="otp", **extra)

    def on_ask_otp(self, text, lat, lon):
        code = nlu.extract_digits(text)[:6]
        phone = self.state.get("phone")
        if not phone or not check_otp(phone, code):
            return self.reply(t("bad_otp", self.lang), "ask_otp", input_hint="otp")
        self.user = get_or_create_user(self.db, phone, self.lang)
        self.user.preferred_language = self.lang
        self.db.commit()
        self.state["user_id"] = self.user.id
        self.out["action"] = {"type": "login", "token": make_token(self.user), "user": _user_view(self.user)}
        return self.ask_intent()

    # ------------------------------------------------------------ intent
    def on_ask_intent(self, text, lat, lon):
        intent = nlu.extract_intent(text)
        if intent == "need":
            self.state["intent"] = "need"
            self._fill_request_slots(text, first=True)
            return self._next_request_question()
        if intent == "donate":
            self.state["intent"] = "donate"
            if self.user and self.user.donor:
                self.user.donor.availability_status = "available"
                self.db.commit()
                self.out["action"] = {"type": "open_donor"}
                return self.reply(t("already_donor", self.lang, name=self.user.full_name or ""), "done",
                                  _chips(self.lang, "need", "track", "restart"))
            s = self.state["slots"]
            if self.user and self.user.full_name:
                s["name"] = self.user.full_name
            if bg := nlu.extract_blood_group(text):
                s["blood_group"] = bg
            if g := nlu.extract_gender(text):
                s["gender"] = g
            return self._next_donor_question()
        if intent == "track":
            req = (self.db.query(BloodRequest).filter(BloodRequest.requester_id == self.user.id)
                   .order_by(BloodRequest.created_at.desc()).first()) if self.user else None
            if not req:
                return self.reply(t("no_request", self.lang), "ask_intent", _chips(self.lang, "need", "donate"))
            self.out["action"] = {"type": "open_request", "request_id": req.id}
            status = STATUS_LABELS.get(req.status, {}).get(self.lang, req.status)
            return self.reply(t("track", self.lang, status=status), "done", _chips(self.lang, "need", "donate", "restart"))
        return self.reply(t("not_understood", self.lang) + t("ask_intent_again", self.lang), "ask_intent",
                          _chips(self.lang, "need", "donate", "track"))

    # ------------------------------------------------------------ blood request flow
    def _fill_request_slots(self, text: str, first: bool = False):
        s = self.state["slots"]
        if bg := nlu.extract_blood_group(text):
            s["blood_group"] = bg
        if u := nlu.extract_urgency(text):
            s["urgency"] = u
        units = nlu.extract_units_if_mentioned(text)
        if units:
            s["units"] = units
        if h := find_hospital(text):
            s.update(hospital=h["name"], lat=h["lat"], lon=h["lon"])

    def _next_request_question(self, prefix: str = "") -> dict:
        s = self.state["slots"]
        if "blood_group" not in s:
            return self.reply(prefix + t("ask_bg", self.lang), "req_bg", _bg_chips())
        if "units" not in s:
            return self.reply(prefix + t("ask_units", self.lang), "req_units",
                              [{"label": str(n), "value": f"{n} units"} for n in (1, 2, 3, 4)])
        if "hospital" not in s:
            chips = [{"label": h["name"].split(",")[0], "value": h["name"]} for h in HOSPITALS[:6]]
            return self.reply(prefix + t("ask_hospital", self.lang), "req_hospital", chips + _chips(self.lang, "location"))
        if "urgency" not in s:
            return self.reply(prefix + t("ask_urgency", self.lang), "req_urgency", _chips(self.lang, "critical", "urgent", "normal"))
        text = t("confirm_request", self.lang, units=s["units"], bg=s["blood_group"], hospital=s["hospital"],
                 urgency=label(s["urgency"], self.lang))
        return self.reply(prefix + text, "req_confirm", _chips(self.lang, "yes", "no"))

    def on_req_bg(self, text, lat, lon):
        self._fill_request_slots(text)
        if "blood_group" not in self.state["slots"]:
            return self.reply(t("bad_bg", self.lang), "req_bg", _bg_chips())
        return self._next_request_question()

    def on_req_units(self, text, lat, lon):
        n = nlu.extract_number(text, 1, 10)
        self._fill_request_slots(text)
        if not n:
            return self.reply(t("not_understood", self.lang) + t("ask_units", self.lang), "req_units",
                              [{"label": str(k), "value": f"{k} units"} for k in (1, 2, 3, 4)])
        self.state["slots"]["units"] = n
        return self._next_request_question()

    def on_req_hospital(self, text, lat, lon):
        s = self.state["slots"]
        h = find_hospital(text)
        coords = [lat, lon] if lat is not None and lon is not None else self.state.get("last_coords")
        if h:
            s.update(hospital=h["name"], lat=h["lat"], lon=h["lon"])
        elif text == LOCATION_TOKEN or text == "location":
            if not coords:
                return self.reply(t("ask_hospital", self.lang), "req_hospital", _chips(self.lang, "location"))
            s.update(hospital="Shared location", lat=coords[0], lon=coords[1])
        else:
            area = find_area(text)
            base = coords or ([area["lat"], area["lon"]] if area else list(BENGALURU_CENTER))
            s.update(hospital=nlu._PUNCT.sub(" ", text).strip()[:120] or "Hospital", lat=base[0], lon=base[1])
        if u := nlu.extract_urgency(text):
            s["urgency"] = u
        return self._next_request_question()

    def on_req_urgency(self, text, lat, lon):
        u = nlu.extract_urgency(text)
        if not u:
            return self.reply(t("not_understood", self.lang) + t("ask_urgency", self.lang), "req_urgency",
                              _chips(self.lang, "critical", "urgent", "normal"))
        self.state["slots"]["urgency"] = u
        return self._next_request_question()

    def on_req_confirm(self, text, lat, lon):
        yn = nlu.yes_no(text)
        if yn is None:
            # allow corrections at the confirm step, e.g. "no, O positive"
            before = dict(self.state["slots"])
            self._fill_request_slots(text)
            if before != self.state["slots"]:
                return self._next_request_question()
            return self._next_request_question(t("not_understood", self.lang))
        if yn is False:
            return self.ask_intent(t("cancelled", self.lang).split(".")[0] + ". ")
        s = self.state["slots"]
        req = create_request(self.db, self.user, blood_group=s["blood_group"], units=s["units"], urgency=s["urgency"],
                             hospital=s["hospital"], lat=s["lat"], lon=s["lon"], language=self.lang, via="voice")
        notified = sum(1 for m in req.matches if m.status == "notified")
        self.out["action"] = {"type": "open_request", "request_id": req.id}
        key = "request_created" if notified else "request_created_none"
        self.state["slots"] = {}
        return self.reply(t(key, self.lang, n=notified), "done", _chips(self.lang, "track", "restart"))

    # ------------------------------------------------------------ donor flow
    def _next_donor_question(self, prefix: str = "") -> dict:
        s = self.state["slots"]
        if "name" not in s:
            return self.reply(prefix + t("ask_name", self.lang), "don_name")
        if "blood_group" not in s:
            return self.reply(prefix + t("ask_bg_donor", self.lang), "don_bg", _bg_chips())
        if "gender" not in s:
            return self.reply(prefix + t("ask_gender", self.lang), "don_gender", _chips(self.lang, "male", "female"))
        if "last_set" not in s:
            return self.reply(prefix + t("ask_last", self.lang), "don_last",
                              _chips(self.lang, "never") + [{"label": "3+", "value": "4 months"}, {"label": "6+", "value": "7 months"}])
        if "lat" not in s:
            return self.reply(prefix + t("ask_location", self.lang), "don_location",
                              _chips(self.lang, "location") + [{"label": a, "value": a} for a in ("Koramangala", "Jayanagar", "Whitefield", "Hebbal")])
        last = s.get("last_donation") or label("never", self.lang)
        return self.reply(prefix + t("confirm_donor", self.lang, name=s["name"], bg=s["blood_group"], last=last),
                          "don_confirm", _chips(self.lang, "yes", "no"))

    def on_don_name(self, text, lat, lon):
        name = nlu.extract_name(text)
        if not name:
            return self.reply(t("ask_name", self.lang), "don_name")
        self.state["slots"]["name"] = name
        return self._next_donor_question()

    def on_don_bg(self, text, lat, lon):
        bg = nlu.extract_blood_group(text)
        if not bg:
            return self.reply(t("bad_bg", self.lang), "don_bg", _bg_chips())
        self.state["slots"]["blood_group"] = bg
        if g := nlu.extract_gender(text):
            self.state["slots"]["gender"] = g
        return self._next_donor_question()

    def on_don_gender(self, text, lat, lon):
        g = nlu.extract_gender(text)
        if not g:
            return self.reply(t("not_understood", self.lang) + t("ask_gender", self.lang), "don_gender", _chips(self.lang, "male", "female"))
        self.state["slots"]["gender"] = g
        return self._next_donor_question()

    def on_don_last(self, text, lat, lon):
        ok, d = nlu.extract_last_donation(text)
        if not ok:
            return self.reply(t("not_understood", self.lang) + t("ask_last", self.lang), "don_last", _chips(self.lang, "never"))
        s = self.state["slots"]
        s["last_set"] = True
        s["last_donation"] = d.isoformat() if d else None
        return self._next_donor_question()

    def on_don_location(self, text, lat, lon):
        s = self.state["slots"]
        coords = [lat, lon] if lat is not None and lon is not None else None
        area = find_area(text) or find_hospital(text)
        if area:
            s.update(lat=area["lat"], lon=area["lon"], area=area["name"].split(",")[0])
        elif coords or (text in (LOCATION_TOKEN, "location") and self.state.get("last_coords")):
            c = coords or self.state["last_coords"]
            s.update(lat=c[0], lon=c[1], area=label("location", "en").replace("Share my ", "Shared "))
        else:
            c = self.state.get("last_coords") or list(BENGALURU_CENTER)
            s.update(lat=c[0], lon=c[1], area=nlu._PUNCT.sub(" ", text).strip()[:80])
        return self._next_donor_question()

    def on_don_confirm(self, text, lat, lon):
        yn = nlu.yes_no(text)
        if yn is None:
            return self._next_donor_question(t("not_understood", self.lang))
        if yn is False:
            return self.ask_intent(t("cancelled", self.lang).split(".")[0] + ". ")
        s = self.state["slots"]
        last = date.fromisoformat(s["last_donation"]) if s.get("last_donation") else None
        register_donor(self.db, self.user, name=s["name"], blood_group=s["blood_group"], gender=s["gender"],
                       last_donation=last, lat=s["lat"], lon=s["lon"], area=s.get("area", ""), language=self.lang)
        self.out["action"] = {"type": "donor_registered", "user": _user_view(self.user)}
        self.state["slots"] = {}
        if in_cooldown(last, s["gender"]):
            msg = t("donor_cooldown", self.lang, name=s["name"], date=str(next_eligible_date(last, s["gender"])))
        else:
            msg = t("donor_registered", self.lang, name=s["name"], groups=", ".join(groups_donor_can_help(s["blood_group"])))
        return self.reply(msg, "done", _chips(self.lang, "track", "restart"))

    def on_done(self, text, lat, lon):
        return self.on_ask_intent(text, lat, lon)


def handle_turn(db: Session, session_id: str | None, lang: str, text: str, lat=None, lon=None, user: User | None = None) -> dict:
    a = Assistant(db, session_id, lang, user)
    # steps after login require a user; if the session lost its user, restart login
    if a.state.get("step") not in (None, "ask_phone", "ask_otp") and not a.user:
        a.state["step"] = None
    return a.turn(text, lat, lon)
