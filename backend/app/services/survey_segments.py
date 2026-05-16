"""Segment filtering for the screener-bridge wedge.

A "segment" is a set of StudyParticipants who answered a survey in a
particular way. The frontend builds a list of filter clauses ("Q3
score <= 6 AND Q5 chose option 'pricing'"), the backend resolves them
to a list of StudyParticipant IDs, and that list is what the bridge
invites to AI interviews.

Operators per question type:
  - likert / nps: `eq` (==), `lte` (<=), `gte` (>=), `between` ([lo, hi])
  - mc_single / mc_multi: `in` (any selected choice id matches)
  - open_text / short_text: not filterable in v1 (clustering ships in
    Sprint 13)

The intersection logic: each clause produces a SET of completed-response
participants; the segment is the intersection across all clauses. Empty
filter list → no constraint, return every completed-response participant.

We deliberately only count COMPLETED responses (`completed_at IS NOT
NULL`) — partial responses aren't a candidate pool because we don't have
their full answer profile.
"""

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.models.study import StudyParticipant
from app.models.survey import (
    Survey,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)

NumericOp = Literal["eq", "lte", "gte", "between"]
ChoiceOp = Literal["in"]


@dataclass
class FilterClause:
    """One filter condition on one question.

    operator semantics depend on question type:
      - likert/nps + eq/lte/gte: value is a number
      - likert/nps + between:    value is [low, high]
      - mc_*       + in:         value is a list of choice ids
    """

    question_id: str
    operator: str
    value: Any


def _matches_numeric_clause(answer: SurveyResponseAnswer, clause: FilterClause) -> bool:
    v = answer.value_numeric
    if v is None:
        return False
    if clause.operator == "eq":
        return v == float(clause.value)
    if clause.operator == "lte":
        return v <= float(clause.value)
    if clause.operator == "gte":
        return v >= float(clause.value)
    if clause.operator == "between":
        lo, hi = clause.value
        return float(lo) <= v <= float(hi)
    return False


def _matches_choice_clause(answer: SurveyResponseAnswer, clause: FilterClause) -> bool:
    if clause.operator != "in":
        return False
    target = set(clause.value or [])
    if not target:
        return False
    chosen = set(answer.choice_ids_list)
    return bool(chosen & target)


def resolve_segment(
    db: Session,
    survey: Survey,
    clauses: list[FilterClause],
) -> list[StudyParticipant]:
    """Resolve filter clauses → de-duped list of matching StudyParticipants.

    Always restricts to completed responses with a non-null
    study_participant_id. Participants without an email or with their
    `is_anonymous` flag won't be invitable downstream, but they DO count
    here — that filter happens at invite time, not segment-resolution
    time, so the count is "how many distinct people qualify" not "how
    many can we email."
    """

    # Build a set of question_ids referenced for validation + faster lookup.
    question_ids = [c.question_id for c in clauses]
    questions = (
        db.query(SurveyQuestion)
        .filter(SurveyQuestion.survey_id == survey.id, SurveyQuestion.id.in_(question_ids))
        .all()
    )
    by_id = {q.id: q for q in questions}
    # Drop clauses pointing at unknown questions (defensive — the API will already 404).
    valid_clauses = [c for c in clauses if c.question_id in by_id]

    # All completed responses for this survey.
    responses = (
        db.query(SurveyResponse)
        .filter(
            SurveyResponse.survey_id == survey.id,
            SurveyResponse.completed_at.isnot(None),
            SurveyResponse.study_participant_id.isnot(None),
            SurveyResponse.is_excluded.is_(False),
        )
        .all()
    )

    # For each clause, build the set of participant ids that match it.
    matching_per_clause: list[set[str]] = []
    if not valid_clauses:
        # No filter → every completed respondent qualifies.
        matching_per_clause.append({r.study_participant_id for r in responses if r.study_participant_id})
    else:
        for clause in valid_clauses:
            q = by_id[clause.question_id]
            participant_ids: set[str] = set()
            answers = (
                db.query(SurveyResponseAnswer)
                .join(SurveyResponse, SurveyResponseAnswer.response_id == SurveyResponse.id)
                .filter(
                    SurveyResponseAnswer.question_id == clause.question_id,
                    SurveyResponse.completed_at.isnot(None),
                    SurveyResponse.study_participant_id.isnot(None),
                    SurveyResponse.is_excluded.is_(False),
                )
                .all()
            )
            for a in answers:
                if q.type in ("likert", "nps") and _matches_numeric_clause(a, clause):
                    participant_ids.add(a.response.study_participant_id)
                elif q.type in ("mc_single", "mc_multi") and _matches_choice_clause(a, clause):
                    participant_ids.add(a.response.study_participant_id)
            matching_per_clause.append(participant_ids)

    # Intersect.
    if not matching_per_clause:
        return []
    intersection = set.intersection(*matching_per_clause) if matching_per_clause else set()

    if not intersection:
        return []

    participants = (
        db.query(StudyParticipant)
        .filter(StudyParticipant.id.in_(list(intersection)))
        .all()
    )
    return participants


def invitable_participants(
    participants: list[StudyParticipant],
) -> tuple[list[StudyParticipant], list[StudyParticipant]]:
    """Split into (invitable, skipped).

    Invitable = has a normalised email. Skipped = no email on record
    (most likely came in through an anonymous link). Skipped participants
    are surfaced in the bridge UI so the researcher knows their segment
    is a slight superset of who'll actually get an invite.
    """

    invitable: list[StudyParticipant] = []
    skipped: list[StudyParticipant] = []
    for p in participants:
        if p.email_normalized:
            invitable.append(p)
        else:
            skipped.append(p)
    return invitable, skipped
