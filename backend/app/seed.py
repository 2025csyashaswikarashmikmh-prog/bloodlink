"""Seed demo data: admin, blood-centre staff, ~30 donors around Bengaluru, demo blood banks.
All demo donors use fake numbers starting 90000xxxxx."""
from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .blood import AREAS_GEO, BLOOD_GROUPS
from .models import BloodBank, DonorProfile, User

NAMES = ["Arjun Rao", "Priya Shetty", "Rahul Gowda", "Ananya Iyer", "Kiran Kumar", "Divya Nair", "Suresh Reddy", "Meghana Bhat",
         "Vikram Singh", "Lakshmi Devi", "Imran Khan", "Sneha Patil", "Naveen Hegde", "Fathima Begum", "Rohit Sharma",
         "Kavya Murthy", "Manoj Pillai", "Deepa Rao", "Harish Naik", "Pooja Menon", "Sanjay Joshi", "Asha Kulkarni",
         "Varun Prasad", "Nisha Thomas", "Abdul Rahman", "Shruthi Gowda", "Prakash Shenoy", "Bhavya Rai", "Girish Acharya", "Sowmya Rao"]
GROUP_WEIGHTS = [22, 3, 30, 3, 8, 2, 28, 4]


def seed(db: Session) -> bool:
    if db.query(User).count() > 0:
        return False
    rng = random.Random(7)
    db.add_all([
        User(full_name="RaktaSetu Admin", phone="9999999999", role="admin"),
        User(full_name="Blood Centre Staff", phone="8888888888", role="staff"),
    ])
    groups = rng.choices(BLOOD_GROUPS, weights=GROUP_WEIGHTS, k=len(NAMES))
    groups[:8] = ["B+", "O+", "O-", "A+", "B+", "AB+", "O+", "B-"]  # guarantee coverage for the demo
    for i, name in enumerate(NAMES):
        area = AREAS_GEO[i % len(AREAS_GEO)]
        gender = "F" if name.split()[0] in {"Priya", "Ananya", "Divya", "Meghana", "Lakshmi", "Sneha", "Fathima", "Kavya", "Deepa",
                                            "Pooja", "Asha", "Nisha", "Shruthi", "Bhavya", "Sowmya"} else "M"
        u = User(full_name=name, phone=f"90000{i:05d}", role="donor", preferred_language=rng.choice(["en", "kn", "hi", "kn", "ta", "te"]))
        db.add(u)
        db.flush()
        last = None if rng.random() < 0.35 else date.today() - timedelta(days=rng.randint(40, 400))
        notified = rng.randint(0, 12)
        accepted = rng.randint(0, notified)
        db.add(DonorProfile(
            user_id=u.id, blood_group=groups[i], gender=gender, area=area["name"],
            latitude=area["lat"] + rng.uniform(-0.012, 0.012), longitude=area["lon"] + rng.uniform(-0.012, 0.012),
            last_donation_date=last, availability_status=rng.choices(["available", "busy", "unavailable"], [75, 15, 10])[0],
            reliability_score=round(rng.uniform(45, 95), 1), total_donations=rng.randint(0, 9),
            times_notified=notified, times_accepted=accepted, times_no_show=rng.randint(0, max(accepted // 3, 0)),
        ))
    banks = [
        ("Rotary TTK Blood Bank (demo stock)", "Indiranagar", "080-2528-8000", 12.9790, 77.6400),
        ("Victoria Hospital Blood Centre (demo stock)", "KR Market", "080-2670-1150", 12.9634, 77.5737),
        ("Lions Blood Bank (demo stock)", "Jayanagar", "080-2663-3333", 12.9260, 77.5830),
        ("Narayana Health Blood Centre (demo stock)", "Bommasandra", "080-7122-2222", 12.8100, 77.6950),
        ("Rashtrotthana Blood Centre (demo stock)", "Chamarajpet", "080-2661-2730", 12.9560, 77.5640),
        ("Manipal Hospital Blood Centre (demo stock)", "Old Airport Road", "080-2502-4444", 12.9592, 77.6489),
    ]
    for name, addr, phone, lat, lon in banks:
        db.add(BloodBank(name=name, address=f"{addr}, Bengaluru", phone=phone, latitude=lat, longitude=lon,
                         stock={g: rng.choice([0, 0, 1, 2, 3, 5, 8]) for g in BLOOD_GROUPS}))
    db.commit()
    return True
