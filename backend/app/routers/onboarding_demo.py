"""V3 — participant-experience demo during onboarding.

The new researcher records a 20-30s answer to a meta-question ("Tell
me about the best onboarding you had recently") inside an iPhone-framed
modal. We transcribe with Whisper, light-keyword-detect a code label,
pick a sentence to highlight, and return everything so the FE can show
"here's what your participants will look like in the analysis view."

No DB persistence — pure preview. Authed but no charges, no usage logs.
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.services.stt import transcribe_audio

router = APIRouter(prefix="/onboarding/demo-interview", tags=["onboarding-demo"])


# Light keyword → code map. Order matters: first match wins. The
# fallback "Worth coming back to" looks like a real codebook entry
# instead of a sad "no match" message.
_KEYWORD_CODES: list[tuple[str, list[str], str]] = [
    (
        "Trust signal",
        ["safe", "trust", "secure", "honest", "real person", "didn't feel like"],
        "#10b981",  # emerald
    ),
    (
        "First-success moment",
        ["worked", "set up", "right away", "two minutes", "quick", "easy", "fast"],
        "#4f46e5",  # brand
    ),
    (
        "Friction",
        ["confused", "stuck", "couldn't", "frustrated", "annoying", "broken", "didn't know"],
        "#dc2626",  # red
    ),
    (
        "Price concern",
        ["expensive", "cheap", "pricing", "cost", "budget", "free"],
        "#d97706",  # amber
    ),
    (
        "Onboarding craft",
        ["walked me through", "showed me", "tutorial", "tour", "checklist", "step by step"],
        "#7c3aed",  # violet
    ),
]

_FALLBACK_CODE = ("Worth coming back to", "#64748b")  # slate


def _pick_code(transcript: str) -> tuple[str, str]:
    """Light keyword detection — first matching code wins."""
    text = (transcript or "").lower()
    for label, keywords, color in _KEYWORD_CODES:
        if any(kw in text for kw in keywords):
            return label, color
    return _FALLBACK_CODE


def _pick_highlight(
    transcript: str, segments: list[dict]
) -> Optional[dict]:
    """Pick the most quote-worthy sentence to highlight. Prefer a
    segment containing one of our keywords; fall back to the longest
    non-trivial segment. Returns ``{start, end, text}`` (character
    offsets into ``transcript``) or None if nothing works."""
    text = transcript or ""
    if not text:
        return None

    candidates: list[str] = []
    # Segments from Whisper are timestamped slices — usually sentence-ish.
    for seg in segments:
        seg_text = (seg.get("text") or "").strip()
        if seg_text and len(seg_text) > 12:
            candidates.append(seg_text)

    # If Whisper gave no segments, split on sentence-ending punctuation.
    if not candidates:
        candidates = [s.strip() for s in re.split(r"[.!?]\s+", text) if s.strip()]

    if not candidates:
        return None

    # Prefer the first candidate matching any code keyword.
    lower = text.lower()
    chosen: Optional[str] = None
    for cand in candidates:
        cand_lower = cand.lower()
        for _, keywords, _ in _KEYWORD_CODES:
            if any(kw in cand_lower for kw in keywords):
                chosen = cand
                break
        if chosen:
            break

    # Fall back to the longest candidate (usually the meatiest answer).
    if chosen is None:
        chosen = max(candidates, key=len)

    # Find the character offsets in the original transcript.
    start = text.find(chosen)
    if start < 0:
        # Be tolerant of whitespace differences.
        normalised = re.sub(r"\s+", " ", chosen).strip()
        if normalised:
            start = text.find(normalised.split(" ", 1)[0])
    if start < 0:
        return None
    end = start + len(chosen)
    return {"start": start, "end": end, "text": chosen}


@router.post("/transcribe")
async def transcribe_demo_audio(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    """Transcribe the user's demo answer with Whisper and return a
    response that mimics what the researcher will see in the real
    analysis view: transcript + a single highlighted span + a code
    label. Strictly preview — nothing persists."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio provided.",
        )
    # Cap at 5 MB — the real interview path has its own cap; this is
    # just a 20-30s clip so anything bigger is suspicious.
    if len(audio_bytes) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio file too large for the demo.",
        )

    filename = audio.filename or "demo.webm"
    try:
        transcript, _duration, segments = transcribe_audio(audio_bytes, filename)
    except Exception as exc:
        # Whisper / network failure — don't 500 the user; return a
        # graceful empty transcript so the FE can show the canned
        # skip-path content instead.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Transcription failed: {exc}",
        )

    transcript = (transcript or "").strip()
    code_label, code_color = _pick_code(transcript)
    highlight = _pick_highlight(transcript, segments)

    return {
        "transcript": transcript,
        "highlight": highlight,
        "code": {"label": code_label, "color": code_color},
    }
