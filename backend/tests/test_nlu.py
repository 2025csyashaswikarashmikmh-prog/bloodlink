import pytest

from app import nlu


@pytest.mark.parametrize("text,expected", [
    ("I need B positive blood", "B+"),
    ("O-", "O-"),
    ("ab negative", "AB-"),
    ("nanage B positive rakta beku", "B+"),
    ("मुझे बी पॉजिटिव खून चाहिए", "B+"),
    ("ओ नेगेटिव", "O-"),
    ("ನನಗೆ ಬಿ ಪಾಸಿಟಿವ್ ರಕ್ತ ಬೇಕು", "B+"),
    ("ಎಬಿ ನೆಗೆಟಿವ್", "AB-"),
    ("ಓ ಪಾಸಿಟಿವ್", "O+"),
    ("எனக்கு ஏ பாசிட்டிவ் இரத்தம் வேண்டும்", "A+"),
    ("నాకు ఓ పాజిటివ్ రక్తం కావాలి", "O+"),
    ("b+ve", "B+"),
    ("A+", "A+"),
])
def test_blood_group(text, expected):
    assert nlu.extract_blood_group(text) == expected


def test_no_blood_group():
    assert nlu.extract_blood_group("I need a doctor") is None
    assert nlu.extract_blood_group("ನನಗೆ ಎರಡು ಯೂನಿಟ್ ಬೇಕು") is None


@pytest.mark.parametrize("text,expected", [
    ("I need blood", "need"), ("I want to donate", "donate"), ("मुझे खून चाहिए", "need"),
    ("मैं रक्तदान करना चाहता हूँ", "donate"), ("ನನಗೆ ರಕ್ತ ಬೇಕು", "need"), ("ನಾನು ರಕ್ತದಾನ ಮಾಡುತ್ತೇನೆ", "donate"),
    ("எனக்கு இரத்தம் வேண்டும்", "need"), ("నేను రక్తదానం చేస్తాను", "donate"), ("we need a donor urgently", "need"),
    ("track my request", "track"),
])
def test_intent(text, expected):
    assert nlu.extract_intent(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("2 units", 2), ("ಎರಡು ಯೂನಿಟ್", 2), ("तीन", 3), ("मुझे ३ यूनिट चाहिए", 3), ("ரெண்டு", 2), ("ఒకటి", 1), ("hmm", None),
])
def test_numbers(text, expected):
    assert nlu.extract_number(text) == expected


def test_phone_digits():
    assert nlu.extract_digits("+91 98765 43210").endswith("9876543210")
    assert nlu.extract_digits("nine eight seven six five four three two one zero") == "9876543210"
    assert nlu.extract_digits("९८७६५४३२१०") == "9876543210"


@pytest.mark.parametrize("text,expected", [
    ("very urgent", "critical"), ("tumba urgent", "critical"), ("ತುರ್ತು", "urgent"), ("ತೀವ್ರ ತುರ್ತು", "critical"),
    ("तुरंत चाहिए", "critical"), ("कल तक", "normal"), ("not urgent", "normal"), ("அவசரம்", "urgent"), ("critical", "critical"),
])
def test_urgency(text, expected):
    assert nlu.extract_urgency(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("yes", True), ("हाँ", True), ("ಹೌದು", True), ("சரி", True), ("అవును", True),
    ("no", False), ("नहीं", False), ("ಬೇಡ", False), ("வேண்டாம்", False), ("వద్దు", False), ("maybe", None),
])
def test_yes_no(text, expected):
    assert nlu.yes_no(text) is expected


def test_gender_and_last_donation():
    assert nlu.extract_gender("female") == "F" and nlu.extract_gender("ಪುರುಷ") == "M" and nlu.extract_gender("महिला") == "F"
    ok, d = nlu.extract_last_donation("never")
    assert ok and d is None
    ok, d = nlu.extract_last_donation("4 months ago")
    assert ok and d is not None
    ok, d = nlu.extract_last_donation("ಎರಡು ತಿಂಗಳ ಹಿಂದೆ")
    assert ok and d is not None


def test_name():
    assert nlu.extract_name("my name is ravi kumar") == "Ravi Kumar"
    assert nlu.extract_name("मेरा नाम राहुल है") == "राहुल"
