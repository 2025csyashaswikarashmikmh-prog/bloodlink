import hashlib
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..i18n import LANGS
from ..schemas import VoiceTurn
from ..voice import handle_turn
from .request_routes import optional_user

router = APIRouter(prefix="/api/voice", tags=["voice"])
_tts_cache: dict[str, bytes] = {}


@router.post("/turn")
def turn(body: VoiceTurn, user=Depends(optional_user), db: Session = Depends(get_db)):
    return handle_turn(db, body.session_id, body.lang, body.text, body.lat, body.lon, user)


@router.get("/tts")
def tts(text: str, lang: str = "en"):
    """Server-side text-to-speech fallback (gTTS) for browsers without a voice for the language
    (Kannada/Tamil/Telugu voices are often missing on laptops)."""
    if lang not in LANGS or not text or len(text) > 600:
        raise HTTPException(400, "bad text or language")
    key = hashlib.sha1(f"{lang}:{text}".encode()).hexdigest()
    if key not in _tts_cache:
        try:
            from gtts import gTTS

            buf = io.BytesIO()
            gTTS(text=text, lang=lang, tld="co.in" if lang == "en" else "com").write_to_fp(buf)
            _tts_cache[key] = buf.getvalue()
        except Exception as e:
            raise HTTPException(503, f"TTS unavailable: {e}")
    return Response(_tts_cache[key], media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})
