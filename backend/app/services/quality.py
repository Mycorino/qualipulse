"""Heuristic quality scoring persisted to the Participant model."""
from sqlalchemy.orm import Session

from app.models.interview import Participant

_FILLERS = {"yes", "no", "ok", "okay", "sure", "yep", "nope", "yeah", "nah", "uh", "um"}


def _score_turns(turns) -> tuple[float | None, str | None]:
    responses = [
        t.response_transcript
        for t in turns
        if t.response_transcript and t.response_transcript.strip()
    ]
    if not responses:
        return None, None

    total = 0.0
    for text in responses:
        words = text.lower().split()
        wc = len(words)
        normalized = text.lower().strip().rstrip(".!?")
        is_filler = normalized in _FILLERS or (wc <= 3 and any(f in normalized for f in _FILLERS))

        if is_filler or wc <= 2:
            score = 0.0
        elif wc <= 8:
            score = 0.2
        elif wc <= 20:
            score = 0.5
        elif wc <= 50:
            score = 0.8
        else:
            score = 1.0
        total += score

    avg = total / len(responses)
    if avg < 0.25:
        label = "low"
    elif avg < 0.5:
        label = "fair"
    elif avg < 0.75:
        label = "good"
    else:
        label = "strong"
    return round(avg, 3), label


def score_participant_heuristic(participant_id: str, db: Session) -> None:
    """Compute and persist quality score for a participant."""
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        return
    score, label = _score_turns(participant.turns)
    participant.quality_score = score
    participant.quality_label = label
    db.commit()
