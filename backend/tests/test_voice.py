"""End-to-end voice conversations in Kannada and Hindi."""


def say(client, sid, lang, text, **kw):
    r = client.post("/api/voice/turn", json={"session_id": sid, "lang": lang, "text": text, **kw}, headers=kw.pop("headers", {}))
    assert r.status_code == 200, r.text
    return r.json()


def test_kannada_blood_request_by_voice(client):
    r = say(client, None, "kn", "__start__")
    sid = r["session_id"]
    assert r["step"] == "ask_phone" and "ಮೊಬೈಲ್" in r["reply"]
    r = say(client, sid, "kn", "ನನ್ನ ನಂಬರ್ 98450 12345")
    assert r["step"] == "ask_otp"
    r = say(client, sid, "kn", r["demo_otp"])
    assert r["action"]["type"] == "login" and r["step"] == "ask_intent"
    # one utterance fills blood group + urgency + hospital at once
    r = say(client, sid, "kn", "ನನಗೆ ಬಿ ಪಾಸಿಟಿವ್ ರಕ್ತ ಬೇಕು ತುಂಬಾ ತುರ್ತು ಮಣಿಪಾಲ ಆಸ್ಪತ್ರೆ")
    assert r["slots"]["blood_group"] == "B+" and r["slots"]["urgency"] == "critical"
    assert r["slots"]["hospital"].startswith("Manipal")
    assert r["step"] == "req_units"
    r = say(client, sid, "kn", "ಎರಡು ಯೂನಿಟ್")
    assert r["step"] == "req_confirm" and "ಖಚಿತಪಡಿಸಿ" in r["reply"]
    r = say(client, sid, "kn", "ಹೌದು")
    assert r["action"]["type"] == "open_request"
    req = client.get(f"/api/requests/{r['action']['request_id']}").json()
    assert req["created_via"] == "voice" and req["units_needed"] == 2 and req["language"] == "kn"


def test_hindi_donor_registration_by_voice(client):
    r = say(client, None, "hi", "")
    sid = r["session_id"]
    r = say(client, sid, "hi", "9988776655")
    r = say(client, sid, "hi", r["demo_otp"])
    r = say(client, sid, "hi", "मैं रक्तदान करना चाहता हूँ")
    assert r["step"] == "don_name"
    r = say(client, sid, "hi", "मेरा नाम राहुल है")
    assert r["step"] == "don_bg"
    r = say(client, sid, "hi", "ओ पॉजिटिव")
    assert r["step"] == "don_gender"
    r = say(client, sid, "hi", "पुरुष")
    r = say(client, sid, "hi", "कभी नहीं")
    assert r["step"] == "don_location"
    r = say(client, sid, "hi", "जयनगर")
    assert r["step"] == "don_confirm"
    r = say(client, sid, "hi", "हाँ")
    assert r["action"]["type"] == "donor_registered" and "धन्यवाद" in r["reply"]


def test_bad_inputs_reprompt(client):
    r = say(client, None, "en", "")
    sid = r["session_id"]
    assert say(client, sid, "en", "my number is 123")["step"] == "ask_phone"
    r = say(client, sid, "en", "9876501234")
    assert say(client, sid, "en", "000000")["step"] == "ask_otp"
    r = say(client, sid, "en", r["demo_otp"])
    assert say(client, sid, "en", "hello there")["step"] == "ask_intent"
    r = say(client, sid, "en", "I need blood")
    assert r["step"] == "req_bg"
    assert say(client, sid, "en", "something")["step"] == "req_bg"
    assert say(client, sid, "en", "start over")["step"] == "ask_intent"
