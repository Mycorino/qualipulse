"""v1.1 — anchor-quote verification.

Claude is instructed never to fabricate verbatim quotes, but the
post-generation verifier means even a prompt drift can't bypass the
methodology contract. These tests pin the verifier behaviour
independently of whether Claude is actually invoked.
"""

import json

from app.models.interview import InterviewTurn, Participant
from app.models.project import Project
from app.models.study import Study, StudyAnalysis
from app.services.study_analysis import _verify_anchor_quotes


def _make_study_with_transcript(
    db, *, quote_text: str
) -> Study:
    """Build the minimal entity chain a verifier needs: study → project →
    participant → turn."""

    from app.models.company import Company

    company = (
        db.query(Company).first()
        or Company(name="Anchor verifier co", email="anc@example.com", password_hash="x")
    )
    if company.id is None:
        db.add(company)
        db.flush()
    study = Study(company_id=company.id, name="Anchor verifier study")
    db.add(study)
    db.flush()
    project = Project(
        company_id=company.id,
        study_id=study.id,
        name="Sibling project",
        language="en",
    )
    db.add(project)
    db.flush()
    participant = Participant(
        link_id="dummy-link",  # not enforced — Participant.link_id is just a string FK in SQLite tests
        project_id=project.id,
        status="completed",
    )
    db.add(participant)
    db.flush()
    db.add(
        InterviewTurn(
            participant_id=participant.id,
            turn_index=0,
            question_text="What was your biggest friction?",
            response_transcript=quote_text,
        )
    )
    db.commit()
    return study


def _make_report(
    *,
    anchor_quote: str | None,
    confidence: str = "supported",
) -> str:
    return json.dumps(
        {
            "executive_summary": "test",
            "themes": [
                {
                    "title": "T1",
                    "survey_signal": None,
                    "interview_evidence": (
                        {
                            "x_of_y": "1 of 1",
                            "interview_count": 1,
                            "anchor_quote": anchor_quote,
                            "segments_mentioned": [],
                        }
                        if anchor_quote is not None
                        else None
                    ),
                    "recommendation": {
                        "kind": "next_research",
                        "action": "act",
                        "rationale": None,
                    },
                    "confidence": confidence,
                }
            ],
            "methodology_note": "test",
            "generated_with_survey_count": 0,
            "generated_with_response_count": 0,
            "generated_with_interview_count": 1,
        }
    )


def test_verifier_keeps_real_substring_quotes(db_session):
    transcript = "The pricing page made sense. The checkout asked for things I didn't expect."
    study = _make_study_with_transcript(db_session, quote_text=transcript)
    report = _make_report(anchor_quote="checkout asked for things I didn't expect")
    out = json.loads(_verify_anchor_quotes(db_session, study, report))
    assert out["themes"][0]["interview_evidence"] is not None


def test_verifier_strips_fabricated_quotes(db_session):
    transcript = "The pricing page made sense."
    study = _make_study_with_transcript(db_session, quote_text=transcript)
    fabricated = (
        "I gave up trying to make our existing tool do this. I just need it to work."
    )
    report = _make_report(anchor_quote=fabricated, confidence="strong")
    out = json.loads(_verify_anchor_quotes(db_session, study, report))
    theme = out["themes"][0]
    assert theme["interview_evidence"] is None
    # And confidence is downgraded from strong → supported.
    assert theme["confidence"] == "supported"


def test_verifier_strips_when_no_transcripts_exist(db_session):
    """A theme can't claim interview evidence on a study with no
    interview track at all."""

    from app.models.company import Company
    company = (
        db_session.query(Company).first()
        or Company(name="Solo co", email="solo@example.com", password_hash="x")
    )
    if company.id is None:
        db_session.add(company)
        db_session.flush()
    study = Study(company_id=company.id, name="No-interviews study")
    db_session.add(study)
    db_session.commit()

    report = _make_report(anchor_quote="anything plausible looking")
    out = json.loads(_verify_anchor_quotes(db_session, study, report))
    assert out["themes"][0]["interview_evidence"] is None


def test_verifier_handles_smart_quote_drift(db_session):
    """Claude often returns smart quotes; the verifier normalises both
    sides before comparison."""

    transcript = "I didn't expect them to ask me about my team size."
    study = _make_study_with_transcript(db_session, quote_text=transcript)
    # Claude returns with smart apostrophes — the most common drift.
    smart_quote = "I didn’t expect them to ask me about my team size"
    report = _make_report(anchor_quote=smart_quote)
    out = json.loads(_verify_anchor_quotes(db_session, study, report))
    assert out["themes"][0]["interview_evidence"] is not None
