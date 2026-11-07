"""Domain rules: blood compatibility, donation cooldown, geo helpers, hospital gazetteer."""
from __future__ import annotations

import math
from datetime import date

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

# Red-cell compatibility: recipient -> donor groups that can give to them.
RECIPIENT_CAN_RECEIVE_FROM: dict[str, list[str]] = {
    "O-": ["O-"],
    "O+": ["O+", "O-"],
    "A-": ["A-", "O-"],
    "A+": ["A+", "A-", "O+", "O-"],
    "B-": ["B-", "O-"],
    "B+": ["B+", "B-", "O+", "O-"],
    "AB-": ["AB-", "A-", "B-", "O-"],
    "AB+": BLOOD_GROUPS,
}

# Minimum gap between whole-blood donations (India guidance): 90 days male, 120 days female.
COOLDOWN_DAYS = {"M": 90, "F": 120}
URGENCY_LEVEL = {"normal": 0, "urgent": 1, "critical": 2}


def compatible_donor_groups(recipient_group: str) -> list[str]:
    if recipient_group not in RECIPIENT_CAN_RECEIVE_FROM:
        raise ValueError(f"Unknown blood group {recipient_group}")
    return RECIPIENT_CAN_RECEIVE_FROM[recipient_group]


def is_compatible(donor_group: str, recipient_group: str) -> bool:
    return donor_group in RECIPIENT_CAN_RECEIVE_FROM.get(recipient_group, [])


def cooldown_days(gender: str) -> int:
    return COOLDOWN_DAYS.get((gender or "M").upper()[:1], 90)


def next_eligible_date(last_donation: date | None, gender: str) -> date | None:
    if not last_donation:
        return None
    from datetime import timedelta

    return last_donation + timedelta(days=cooldown_days(gender))


def in_cooldown(last_donation: date | None, gender: str, today: date | None = None) -> bool:
    nxt = next_eligible_date(last_donation, gender)
    return bool(nxt and (today or date.today()) < nxt)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


BENGALURU_CENTER = (12.9716, 77.5946)


def zone_for(lat: float, lon: float) -> str:
    """Coarse zone used by the demand forecaster (central/north/south/east/west)."""
    dlat, dlon = lat - BENGALURU_CENTER[0], lon - BENGALURU_CENTER[1]
    if abs(dlat) < 0.03 and abs(dlon) < 0.03:
        return "central"
    if abs(dlat) >= abs(dlon):
        return "north" if dlat > 0 else "south"
    return "east" if dlon > 0 else "west"


# Approximate coordinates of well-known Bengaluru hospitals (for demo geocoding of spoken names).
HOSPITALS = [
    {"name": "Manipal Hospital, Old Airport Road", "keys": ["manipal", "ಮಣಿಪಾಲ", "मणिपाल", "மணிப்பால்", "మణిపాల్"], "lat": 12.9592, "lon": 77.6489},
    {"name": "Victoria Hospital, KR Market", "keys": ["victoria", "ವಿಕ್ಟೋರಿಯಾ", "विक्टोरिया", "விக்டோரியா", "విక్టోరియా"], "lat": 12.9634, "lon": 77.5737},
    {"name": "St. John's Medical College Hospital, Koramangala", "keys": ["john", "ಜಾನ್", "जॉन", "ஜான்", "జాన్"], "lat": 12.9298, "lon": 77.6197},
    {"name": "Narayana Health City, Bommasandra", "keys": ["narayana", "ನಾರಾಯಣ", "नारायण", "நாராயணா", "నారాయణ"], "lat": 12.8100, "lon": 77.6950},
    {"name": "NIMHANS, Hosur Road", "keys": ["nimhans", "ನಿಮ್ಹಾನ್ಸ್", "निम्हांस", "நிம்ஹான்ஸ்", "నిమ్హాన్స్"], "lat": 12.9387, "lon": 77.5960},
    {"name": "Fortis Hospital, Bannerghatta Road", "keys": ["fortis", "ಫೋರ್ಟಿಸ್", "फोर्टिस", "ஃபோர்டிஸ்", "ఫోర్టిస్"], "lat": 12.8956, "lon": 77.5986},
    {"name": "Apollo Hospital, Bannerghatta Road", "keys": ["apollo", "ಅಪೋಲೋ", "अपोलो", "அப்பல்லோ", "అపోలో"], "lat": 12.8960, "lon": 77.5990},
    {"name": "Bowring & Lady Curzon Hospital, Shivajinagar", "keys": ["bowring", "ಬೌರಿಂಗ್", "बॉरिंग", "பௌரிங்", "బౌరింగ్"], "lat": 12.9830, "lon": 77.6050},
    {"name": "KC General Hospital, Malleshwaram", "keys": ["kc general", "k c general", "ಕೆ ಸಿ", "ಕೆಸಿ", "केसी", "malleshwaram", "ಮಲ್ಲೇಶ್ವರ"], "lat": 12.9930, "lon": 77.5710},
    {"name": "Ramaiah Memorial Hospital, New BEL Road", "keys": ["ramaiah", "ರಾಮಯ್ಯ", "रमैया", "ராமையா", "రామయ్య"], "lat": 13.0280, "lon": 77.5700},
    {"name": "Sakra World Hospital, Bellandur", "keys": ["sakra", "ಸಕ್ರ", "सकरा", "சக்ரா", "సక్ర"], "lat": 12.9310, "lon": 77.6830},
    {"name": "Aster CMI Hospital, Hebbal", "keys": ["aster", "ಆಸ್ಟರ್", "एस्टर", "ஆஸ்டர்", "ఆస్టర్"], "lat": 13.0480, "lon": 77.5920},
]


def find_hospital(text: str) -> dict | None:
    t = (text or "").lower()
    for h in HOSPITALS:
        if any(k in t for k in h["keys"]):
            return h
    return None


AREAS_GEO = [
    {"name": "Koramangala", "keys": ["koramangala", "ಕೋರಮಂಗಲ", "कोरमंगला", "கோரமங்களா", "కోరమంగళ"], "lat": 12.9352, "lon": 77.6245},
    {"name": "Indiranagar", "keys": ["indiranagar", "indira nagar", "ಇಂದಿರಾನಗರ", "इंदिरानगर", "இந்திராநகர்", "ఇందిరానగర్"], "lat": 12.9784, "lon": 77.6408},
    {"name": "Jayanagar", "keys": ["jayanagar", "ಜಯನಗರ", "जयनगर", "ஜெயநகர்", "జయనగర్"], "lat": 12.9250, "lon": 77.5938},
    {"name": "Whitefield", "keys": ["whitefield", "ವೈಟ್‌ಫೀಲ್ಡ್", "ವೈಟ್ ಫೀಲ್ಡ್", "व्हाइटफील्ड", "வைட்ஃபீல்ட்", "వైట్‌ఫీల్డ్"], "lat": 12.9698, "lon": 77.7500},
    {"name": "Electronic City", "keys": ["electronic city", "ಎಲೆಕ್ಟ್ರಾನಿಕ್ ಸಿಟಿ", "इलेक्ट्रॉनिक सिटी", "எலக்ட்ரானிக் சிட்டி", "ఎలక్ట్రానిక్ సిటీ"], "lat": 12.8452, "lon": 77.6602},
    {"name": "Hebbal", "keys": ["hebbal", "ಹೆಬ್ಬಾಳ", "हेब्बल", "ஹெப்பால்", "హెబ్బాల్"], "lat": 13.0358, "lon": 77.5970},
    {"name": "Malleshwaram", "keys": ["malleshwaram", "malleswaram", "ಮಲ್ಲೇಶ್ವರ", "मल्लेश्वरम", "மல்லேஸ்வரம்", "మల్లేశ్వరం"], "lat": 13.0031, "lon": 77.5643},
    {"name": "Rajajinagar", "keys": ["rajajinagar", "ರಾಜಾಜಿನಗರ", "राजाजीनगर", "ராஜாஜிநகர்", "రాజాజీనగర్"], "lat": 12.9910, "lon": 77.5520},
    {"name": "BTM Layout", "keys": ["btm", "ಬಿಟಿಎಂ", "बीटीएम", "பிடிஎம்", "బీటీఎం"], "lat": 12.9166, "lon": 77.6101},
    {"name": "HSR Layout", "keys": ["hsr", "ಎಚ್‌ಎಸ್‌ಆರ್", "ಎಚ್ ಎಸ್ ಆರ್", "एचएसआर", "ஹெச்எஸ்ஆர்", "హెచ్ఎస్ఆర్"], "lat": 12.9121, "lon": 77.6446},
    {"name": "Marathahalli", "keys": ["marathahalli", "ಮಾರತ್ತಹಳ್ಳಿ", "मराठहल्ली", "மாரத்தஹள்ளி", "మారతహళ్లి"], "lat": 12.9569, "lon": 77.7011},
    {"name": "Yelahanka", "keys": ["yelahanka", "ಯಲಹಂಕ", "येलहंका", "எலஹங்கா", "యలహంక"], "lat": 13.1007, "lon": 77.5963},
    {"name": "Banashankari", "keys": ["banashankari", "ಬನಶಂಕರಿ", "बनशंकरी", "பனசங்கரி", "బనశంకరి"], "lat": 12.9255, "lon": 77.5468},
    {"name": "JP Nagar", "keys": ["jp nagar", "j p nagar", "ಜೆಪಿ ನಗರ", "ಜೆ ಪಿ ನಗರ", "जेपी नगर", "ஜேபி நகர்", "జేపీ నగర్"], "lat": 12.9063, "lon": 77.5857},
    {"name": "Basavanagudi", "keys": ["basavanagudi", "ಬಸವನಗುಡಿ", "बसवनगुडी", "பசவனகுடி", "బసవనగుడి"], "lat": 12.9406, "lon": 77.5738},
    {"name": "Shivajinagar", "keys": ["shivajinagar", "ಶಿವಾಜಿನಗರ", "शिवाजीनगर", "சிவாஜிநகர்", "శివాజీనగర్"], "lat": 12.9857, "lon": 77.6057},
    {"name": "MG Road", "keys": ["mg road", "m g road", "ಎಂಜಿ ರಸ್ತೆ", "ಎಂ ಜಿ ರೋಡ್", "एमजी रोड", "எம்ஜி ரோடு", "ఎంజీ రోడ్"], "lat": 12.9756, "lon": 77.6050},
]


def find_area(text: str) -> dict | None:
    t = (text or "").lower()
    for a in AREAS_GEO:
        if any(k in t for k in a["keys"]):
            return a
    return None
