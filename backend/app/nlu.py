"""Multilingual slot extraction for the voice assistant.

Works on raw speech-to-text output in English, Hindi, Kannada, Tamil and Telugu
(native script OR romanised, e.g. "nanage B positive rakta beku tumba urgent").
Deterministic lexicon-based NLU is deliberate: in an emergency flow we want
predictable, testable behaviour rather than a free-form LLM guess.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

# --------------------------------------------------------------- tokenising
_PUNCT = re.compile(r"[,.!?;:।|()\"'“”‘’]+")


def tokens(text: str) -> list[str]:
    return [t for t in _PUNCT.sub(" ", (text or "").lower()).split() if t]


def has_any(text: str, words: list[str]) -> bool:
    low = (text or "").lower()
    toks = set(tokens(low))
    for w in words:
        if " " in w:
            if w in low:  # multi-word phrase
                return True
        elif w.isascii() or len(w) <= 2:
            if w in toks:  # short / latin words must match a whole token
                return True
        elif w in low:  # Indic stems: substring match handles agglutinative suffixes
            return True
    return False


# --------------------------------------------------------------- blood group
LETTER = {
    "ab": ["ab", "एबी", "ए बी", "ಎಬಿ", "ಎ ಬಿ", "ஏபி", "ஏ பி", "ఏబి", "ఎబి", "ఏ బి"],
    "a": ["a", "ए", "ಎ", "ஏ", "ఎ", "ఏ"],
    "b": ["b", "bee", "बी", "ಬಿ", "பி", "బి", "బీ"],
    "o": ["o", "0", "oh", "ओ", "ಒ", "ಓ", "ஓ", "ఓ", "ఒ"],
}
POS = ["positive", "pos", "plus", "+", "+ve", "ve", "पॉजिटिव", "पोजिटिव", "पॉज़िटिव", "पॉजिटिव्", "प्लस", "ಪಾಸಿಟಿವ್", "ಪಾಜಿಟಿವ್", "ಪಾಸಿಟೀವ್", "ಪ್ಲಸ್",
       "பாசிட்டிவ்", "பாசிடிவ்", "பாசிட்டிவ", "பிளஸ்", "పాజిటివ్", "పాసిటివ్", "ప్లస్"]
NEG = ["negative", "neg", "minus", "-", "-ve", "नेगेटिव", "निगेटिव", "माइनस", "ನೆಗೆಟಿವ್", "ನೆಗಟಿವ್", "ಮೈನಸ್", "நெகட்டிவ்", "நெகடிவ்", "மைனஸ்",
       "నెగటివ్", "నెగెటివ్", "మైనస్"]


def _norm_bg_text(text: str) -> str:
    s = " " + (text or "").lower() + " "
    s = s.replace("+ve", " + ").replace("-ve", " - ").replace("+", " + ")
    s = re.sub(r"(?<=[ab0o])-", " - ", s)
    # replace Indic multi-token letters first (AB before A/B)
    for key in ("ab", "a", "b", "o"):
        for w in sorted(LETTER[key], key=len, reverse=True):
            if not w.isascii():
                s = re.sub(rf"(?<!\S){re.escape(w)}(?=\s|$|[{''.join(map(re.escape, '+-'))}])", f" {key} ", s)
    for w in sorted(POS, key=len, reverse=True):
        if not w.isascii():
            s = s.replace(w, " pos ")
    for w in sorted(NEG, key=len, reverse=True):
        if not w.isascii():
            s = s.replace(w, " neg ")
    # glued forms like "ಬಿಪಾಸಿಟಿವ್" -> after replacement "ಬಿ pos" ; handle leftover glued Indic letter
    for key in ("ab", "a", "b", "o"):
        for w in LETTER[key]:
            if not w.isascii():
                s = s.replace(f"{w} pos", f" {key} pos").replace(f"{w} neg", f" {key} neg")
                s = s.replace(f"{w}pos", f" {key} pos")
    return re.sub(r"\s+", " ", s)


_BG_RE = re.compile(r"(?<![a-z])(ab|a|b|o|0|oh|bee)\s*(positive|pos|plus|\+|ve|negative|neg|minus|-)(?![a-z])")


def extract_blood_group(text: str) -> str | None:
    s = _norm_bg_text(text)
    m = _BG_RE.search(s)
    if not m:
        compact = re.search(r"\b(ab|a|b|o)\s*([+-])", (text or "").lower())
        if not compact:
            return None
        letter, sign = compact.group(1), compact.group(2)
    else:
        letter, sign = m.group(1), m.group(2)
    letter = {"0": "o", "oh": "o", "bee": "b"}.get(letter, letter)
    positive = sign in {"positive", "pos", "plus", "+", "ve"}
    return f"{letter.upper()}{'+' if positive else '-'}"


# --------------------------------------------------------------- numbers
NUM_WORDS = {
    0: ["zero", "oh", "शून्य", "ಸೊನ್ನೆ", "பூஜ்ஜியம்", "సున్నా"],
    1: ["one", "ek", "ondu", "एक", "ಒಂದು", "ஒன்று", "ஒண்ணு", "ఒకటి", "okati"],
    2: ["two", "do", "eradu", "दो", "ಎರಡು", "இரண்டு", "ரெண்டு", "రెండు", "rendu"],
    3: ["three", "teen", "mooru", "तीन", "ಮೂರು", "மூன்று", "మూడు", "moodu"],
    4: ["four", "char", "chaar", "naalku", "चार", "ನಾಲ್ಕು", "நான்கு", "నాలుగు"],
    5: ["five", "paanch", "aidu", "पांच", "पाँच", "ಐದು", "ஐந்து", "ఐదు"],
    6: ["six", "chhah", "aaru", "छह", "छः", "ಆರು", "ஆறு", "ఆరు"],
    7: ["seven", "saat", "elu", "सात", "ಏಳು", "ஏழு", "ఏడు"],
    8: ["eight", "aath", "entu", "आठ", "ಎಂಟು", "எட்டு", "ఎనిమిది"],
    9: ["nine", "nau", "ombattu", "नौ", "ಒಂಬತ್ತು", "ஒன்பது", "తొమ్మిది"],
    10: ["ten", "das", "hattu", "दस", "ಹತ್ತು", "பத்து", "పది"],
}
_WORD_TO_NUM = {w: n for n, ws in NUM_WORDS.items() for w in ws}


def _unicode_digits(text: str) -> str:
    out = []
    for ch in text or "":
        if ch.isdigit():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except (TypeError, ValueError):
                pass
        out.append(ch)
    return "".join(out)


def extract_number(text: str, lo: int = 1, hi: int = 10) -> int | None:
    s = _unicode_digits(text)
    m = re.search(r"\d+", s)
    if m:
        n = int(m.group())
        return n if lo <= n <= hi else None
    for tok in tokens(s):
        for w, n in _WORD_TO_NUM.items():
            if tok == w or (not w.isascii() and tok.startswith(w)):
                if lo <= n <= hi:
                    return n
    return None


def extract_digits(text: str) -> str:
    """Collect all digits, including spoken digit words ("nine eight four ...")."""
    s = _unicode_digits(text)
    out = []
    for tok in tokens(s):
        if re.fullmatch(r"[\d\-]+", tok):
            out.append(tok.replace("-", ""))
        elif tok in _WORD_TO_NUM and _WORD_TO_NUM[tok] <= 9:
            out.append(str(_WORD_TO_NUM[tok]))
        elif tok in {"double", "डबल", "ಡಬಲ್"}:
            out.append("D")
        else:
            out.append(re.sub(r"\D", "", tok))
    joined = "".join(out)
    # "double 9" -> "99"
    return re.sub(r"D(\d)", r"\1\1", joined).replace("D", "")


# --------------------------------------------------------------- yes / no
YES = ["yes", "yeah", "yep", "ok", "okay", "sure", "confirm", "correct", "haan", "ha", "han", "houdu", "howdu", "sari", "aam", "avunu",
       "हाँ", "हां", "हा", "जी", "ठीक", "ಹೌದು", "ಹೂಂ", "ಸರಿ", "ಆಯ್ತು", "ಕಳುಹಿಸಿ", "ஆம்", "ஆமா", "சரி", "అవును", "సరే", "ఓకే", "send", "go ahead"]
NO = ["no", "nope", "cancel", "stop", "dont", "don't", "nahi", "nahin", "illa", "beda", "venda", "vaddu", "ledu",
      "नहीं", "नही", "ना", "मत", "ಇಲ್ಲ", "ಬೇಡ", "இல்லை", "வேண்டாம்", "లేదు", "వద్దు", "రద్దు", "रद्द", "ರದ್ದು", "ரத்து"]


def yes_no(text: str) -> bool | None:
    if has_any(text, NO):
        return False
    if has_any(text, YES):
        return True
    return None


# --------------------------------------------------------------- intents
DONATE = ["donate", "donation", "give blood", "register as donor", "become a donor", "i want to donate", "daan",
          "दान", "डोनेट", "ದಾನ", "ಡೊನೇಟ್", "தானம்", "டொனேட்", "దానం", "డొనేట్"]
NEED = ["need", "require", "required", "want blood", "patient", "emergency", "chahiye", "zaroorat", "jarurat", "beku", "venum", "kavali",
        "चाहिए", "जरूरत", "ज़रूरत", "ಬೇಕು", "ಬೇಕಾಗಿದೆ", "ಅಗತ್ಯ", "வேண்டும்", "தேவை", "வேணும்", "కావాలి", "అవసరం"]
TRACK = ["track", "status", "my request", "where is", "स्थिति", "अनुरोध देख", "ಸ್ಥಿತಿ", "ವಿನಂತಿ ನೋಡಿ", "நிலை", "என் கோரிக்கை", "స్థితి", "నా అభ్యర్థన"]
RESTART = ["start over", "restart", "reset", "फिर से शुरू", "ಮತ್ತೆ ಶುರು", "மீண்டும் தொடங்கு", "మళ్ళీ ప్రారంభించు"]


def extract_intent(text: str) -> str | None:
    if has_any(text, RESTART):
        return "restart"
    if has_any(text, TRACK):
        return "track"
    low = (text or "").lower()
    if has_any(low, DONATE) and not ("donor" in low and has_any(low, NEED)):
        return "donate"
    if has_any(low, NEED) or extract_blood_group(low):
        return "need"
    if "donor" in low:
        return "donate"
    return None


# --------------------------------------------------------------- urgency
VERY = ["very", "bahut", "tumba", "romba", "chala", "बहुत", "ತುಂಬಾ", "ರೊಂಬ", "ரொம்ப", "மிக", "చాలా"]
CRITICAL = ["critical", "emergency", "immediately", "right now", "asap", "turant", "abhi", "ega", "ippove", "ventane",
            "गंभीर", "तुरंत", "अभी", "इमरजेंसी", "ತೀವ್ರ", "ಈಗಲೇ", "ತಕ್ಷಣ", "ಎಮರ್ಜೆನ್ಸಿ", "உடனே", "மிக அவசரம்", "எமர்ஜென்சி", "అత్యవసరం", "వెంటనే", "ఎమర్జెన్సీ"]
URGENT = ["urgent", "today", "soon", "quickly", "jaldi", "aaj", "bega", "jaldi", "जल्दी", "आज", "अर्जेंट", "ತುರ್ತು", "ಬೇಗ", "ಇಂದು", "ಅರ್ಜೆಂಟ್",
          "அவசரம்", "இன்று", "சீக்கிரம்", "త్వరగా", "ఈరోజు", "అర్జెంట్"]
NORMAL = ["normal", "tomorrow", "later", "no hurry", "not urgent", "kal", "naale", "सामान्य", "कल", "ಸಾಮಾನ್ಯ", "ನಾಳೆ", "சாதாரணம்", "நாளை", "సాధారణం", "రేపు"]


def extract_urgency(text: str) -> str | None:
    if has_any(text, NORMAL):
        return "normal"
    if has_any(text, CRITICAL):
        return "critical"
    if has_any(text, URGENT):
        return "critical" if has_any(text, VERY) else "urgent"
    return None


# --------------------------------------------------------------- donor details
FEMALE = ["female", "woman", "lady", "girl", "f", "mahila", "aurat", "mahile", "penn", "stree",
          "महिला", "औरत", "स्त्री", "ಮಹಿಳೆ", "ಹೆಣ್ಣು", "ಮಹಿಳೆಯ", "பெண்", "స్త్రీ", "మహిళ", "అమ్మాయి"]
MALE = ["male", "man", "boy", "gent", "m", "purush", "aadmi", "purusha", "gandu", "aan",
        "पुरुष", "आदमी", "लड़का", "ಪುರುಷ", "ಗಂಡು", "ஆண்", "పురుషుడు", "పురుష", "అబ్బాయి"]


def extract_gender(text: str) -> str | None:
    if has_any(text, FEMALE):
        return "F"
    if has_any(text, MALE):
        return "M"
    return None


NEVER = ["never", "first time", "not yet", "no", "kabhi nahi", "endu illa", "illa", "never donated",
         "कभी नहीं", "कभी नही", "पहली बार", "ಎಂದೂ ಇಲ್ಲ", "ಇಲ್ಲ", "ಮೊದಲ ಬಾರಿ", "ஒருபோதும் இல்லை", "இல்லை", "முதல் முறை", "ఎప్పుడూ లేదు", "లేదు", "మొదటిసారి"]
MONTH = ["month", "months", "mahine", "mahina", "महीने", "महीना", "माह", "ತಿಂಗಳು", "ತಿಂಗಳ", "மாதம்", "மாதங்கள", "மாத", "నెల", "నెలల"]
YEAR = ["year", "years", "saal", "varsha", "साल", "वर्ष", "ವರ್ಷ", "வருடம்", "வருட", "ஆண்டு", "సంవత్సరం", "సంవత్సరాల"]
DAY = ["day", "days", "din", "दिन", "ದಿನ", "நாள்", "நாட்கள", "రోజు", "రోజుల"]
WEEK = ["week", "weeks", "hafte", "हफ्ते", "सप्ताह", "ವಾರ", "வாரம்", "வார", "వారం", "వారాల"]


def extract_last_donation(text: str, today: date | None = None) -> tuple[bool, date | None]:
    """Returns (understood, date_or_None). (True, None) means 'never donated'."""
    today = today or date.today()
    n = extract_number(text, 1, 60)
    if n is None:
        if has_any(text, NEVER):
            return True, None
        if has_any(text, YEAR):  # "a year ago"
            return True, today - timedelta(days=365)
        return False, None
    if has_any(text, DAY):
        return True, today - timedelta(days=n)
    if has_any(text, WEEK):
        return True, today - timedelta(weeks=n)
    if has_any(text, YEAR):
        return True, today - timedelta(days=365 * n)
    return True, today - timedelta(days=30 * n)  # default unit: months


NAME_PREFIX = re.compile(
    r"^(my name is|i am|i'm|this is|name is|mera naam|मेरा नाम|मैं|ನನ್ನ ಹೆಸರು|ನಾನು|என் பெயர்|நான்|నా పేరు|నేను)\s*", re.I
)
NAME_SUFFIX = re.compile(r"\s*(है|हूँ|हूं|ಆಗಿದೆ|ಇದೆ|ಅಂತ|ಎಂದು|ஆகும்|அண்டி|ఆండి|అండి)\s*$")


UNIT_WORDS = ["unit", "units", "bottle", "bottles", "यूनिट", "बोतल", "ಯೂನಿಟ್", "ಬಾಟಲ್", "யூனிட்", "பாட்டில்", "యూనిట్", "బాటిల్"]


def extract_units_if_mentioned(text: str) -> int | None:
    return extract_number(text, 1, 10) if has_any(text, UNIT_WORDS) else None


def extract_name(text: str) -> str | None:
    s = NAME_PREFIX.sub("", (text or "").strip())
    s = NAME_SUFFIX.sub("", s)
    s = _PUNCT.sub(" ", s).strip()
    words = s.split()[:3]
    if not words:
        return None
    return " ".join(w[:1].upper() + w[1:] for w in words)[:60]
