"""One-off backfill: bring existing seeded demo projects up to the showcase
upgrade (interviewer notes, eight-question survey, refreshed decision report).

The demo is seeded once per company (idempotent via ``Company.demo_seeded_at``),
so accounts that onboarded before the showcase upgrade still have:

- guide questions with empty ``interview_notes`` / ``researcher_notes``,
- the legacy five-question demo survey (no stack-size question, no likert
  battery), and
- a ``StudyAnalysis`` decision report whose survey-signal strings predate the
  price-rise numbers.

This script patches all three in place from the current fixtures in
``demo_seeder``, per demo project/survey:

1. **Guide notes** — matched by exact ``main_question`` text; only fills fields
   that are currently empty, so researcher edits are never overwritten.
2. **Survey upgrade** — only fires on a survey that still has the exact legacy
   five-question signature. Existing questions are re-sorted, the three new
   questions inserted, and answers generated for the 44 seeded responses using
   the same cohort plans as the seeder (oldest 44 by ``started_at``; the first
   26 are the heavy/régulières cohort). Surveys with any other shape, or fewer
   than 44 responses, are left alone.
3. **Decision report** — the flagship Study's ``decision_v1`` ``StudyAnalysis``
   report is replaced with the current ``_decision_integration`` output when it
   differs. (``ProjectAnalysis`` reports are unchanged by this upgrade — use
   ``backfill_demo_reports`` for those.)

Idempotent: re-running skips anything already current. Requires NO Anthropic
key (fixtures, not model calls).

Usage (from backend/, with the target env so it hits the intended DB):

    python -m scripts.backfill_demo_showcase --dry-run          # report only
    python -m scripts.backfill_demo_showcase                     # apply
    python -m scripts.backfill_demo_showcase --company <id>      # one company
"""

import argparse
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.project import InterviewGuideQuestion, Project  # noqa: E402
from app.models.study import StudyAnalysis  # noqa: E402
from app.models.survey import (  # noqa: E402
    Survey,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.services.demo_seeder import (  # noqa: E402
    DEMO_GUIDE,
    DEMO_GUIDE_FR,
    DEMO_PROJECT_NAME,
    DEMO_PROJECT_NAME_FR,
    DEMO_SURVEY_EN,
    DEMO_SURVEY_FR,
    DEMO_SURVEY_NAME,
    DEMO_SURVEY_NAME_FR,
    _decision_integration,
)

_FLAGSHIP = {DEMO_PROJECT_NAME, DEMO_PROJECT_NAME_FR}
_ALL_DEMO_NAMES = _FLAGSHIP

# Exact main-question text → (interview_notes, researcher_notes) from the
# current fixtures, both languages.
_NOTES_BY_QUESTION: dict[str, tuple[str, str | None]] = {
    item["q"]: (item.get("notes", ""), item.get("researcher"))
    for guide in (DEMO_GUIDE, DEMO_GUIDE_FR)
    for section in guide
    for item in section["questions"]
}

# The legacy five-question instrument, by (type, key-order). Anything else is
# not the shape this script knows how to upgrade.
_LEGACY_KEYS = ["freq", "services", "value", "nps", "churn"]
_LEGACY_TYPES = ["mc_single", "mc_multi", "likert", "nps", "open_text"]
_NEW_KEYS = ["stack_size", "price_rise", "browse"]
_HEAVY_COHORT_COUNT = 26
_SEEDED_RESPONSE_COUNT = 44


def _backfill_guide_notes(db, dry_run: bool, company_id: str | None) -> int:
    q = (
        db.query(InterviewGuideQuestion)
        .join(Project, InterviewGuideQuestion.project_id == Project.id)
        .filter(Project.is_demo.is_(True), Project.name.in_(_ALL_DEMO_NAMES))
    )
    if company_id:
        q = q.filter(Project.company_id == company_id)
    updated = 0
    for question in q.all():
        fixture = _NOTES_BY_QUESTION.get(question.main_question)
        if fixture is None:
            continue  # researcher rewrote the question — leave it alone
        notes, researcher = fixture
        changed = False
        if notes and not question.interview_notes:
            if not dry_run:
                question.interview_notes = notes
            changed = True
        if researcher and not question.researcher_notes:
            if not dry_run:
                question.researcher_notes = researcher
            changed = True
        if changed:
            updated += 1
    return updated


def _survey_plan_by_key(cfg: dict) -> dict[str, dict]:
    return {q["key"]: q for q in cfg["questions"]}


def _upgrade_survey(db, survey: Survey, cfg: dict, dry_run: bool) -> bool:
    questions = (
        db.query(SurveyQuestion)
        .filter(SurveyQuestion.survey_id == survey.id)
        .order_by(SurveyQuestion.sort_order)
        .all()
    )
    if [q.type for q in questions] != _LEGACY_TYPES:
        return False  # already upgraded, or not a shape we recognise

    plan_by_key = _survey_plan_by_key(cfg)
    # New layout: freq 0, services 1, stack_size 2, value 3, price_rise 4,
    # browse 5, nps 6, churn 7.
    new_sort = {"freq": 0, "services": 1, "value": 3, "nps": 6, "churn": 7}
    responses = (
        db.query(SurveyResponse)
        .filter(SurveyResponse.survey_id == survey.id)
        .order_by(SurveyResponse.started_at)
        .all()
    )
    seedable = len(responses) >= _SEEDED_RESPONSE_COUNT
    if not seedable:
        print(
            f"  ! survey {survey.id[:8]}… has {len(responses)} responses "
            f"(expected >= {_SEEDED_RESPONSE_COUNT}) — inserting questions "
            "without answers."
        )
    if dry_run:
        return True

    for legacy_key, question in zip(_LEGACY_KEYS, questions):
        question.sort_order = new_sort[legacy_key]

    inserted: dict[str, SurveyQuestion] = {}
    for i, key in enumerate(_NEW_KEYS):
        q_plan = plan_by_key[key]
        question = SurveyQuestion(
            survey_id=survey.id,
            sort_order={"stack_size": 2, "price_rise": 4, "browse": 5}[key],
            type=q_plan["type"],
            prompt=q_plan["prompt"],
            is_required=True,
            config=json.dumps(q_plan.get("config") or {}),
        )
        db.add(question)
        inserted[key] = question
    db.flush()

    if seedable:
        # The seeded responses are the oldest 44; the first 26 belong to the
        # heavy/régulières cohort — same order the seeder created them in.
        for i, response in enumerate(responses[:_SEEDED_RESPONSE_COUNT]):
            cohort = cfg["cohorts"][0 if i < _HEAVY_COHORT_COUNT else 1]
            j = i if i < _HEAVY_COHORT_COUNT else i - _HEAVY_COHORT_COUNT
            for key in _NEW_KEYS:
                plan = cohort["answers"][key]
                value = plan[j % len(plan)]
                answer = SurveyResponseAnswer(
                    response_id=response.id,
                    question_id=inserted[key].id,
                    answered_at=response.started_at + timedelta(minutes=2),
                )
                if inserted[key].type == "mc_single":
                    answer.value_choice_ids = json.dumps([value])
                else:  # likert
                    answer.value_numeric = float(value)
                db.add(answer)
    return True


def _backfill_surveys(db, dry_run: bool, company_id: str | None) -> int:
    q = db.query(Survey).filter(
        Survey.name.in_([DEMO_SURVEY_NAME, DEMO_SURVEY_NAME_FR])
    )
    if company_id:
        q = q.filter(Survey.company_id == company_id)
    upgraded = 0
    for survey in q.all():
        cfg = DEMO_SURVEY_FR if survey.name == DEMO_SURVEY_NAME_FR else DEMO_SURVEY_EN
        if _upgrade_survey(db, survey, cfg, dry_run):
            upgraded += 1
    return upgraded


def _backfill_decision_reports(db, dry_run: bool, company_id: str | None) -> int:
    q = (
        db.query(StudyAnalysis, Project)
        .join(Project, StudyAnalysis.study_id == Project.study_id)
        .filter(Project.is_demo.is_(True), Project.name.in_(_FLAGSHIP))
    )
    if company_id:
        q = q.filter(Project.company_id == company_id)
    updated = 0
    for analysis, project in q.all():
        try:
            current = json.loads(analysis.report) if analysis.report else None
        except (TypeError, ValueError):
            current = None
        if not isinstance(current, dict) or current.get("schema") != "decision_v1":
            continue  # a real regenerated analysis — never touch it
        lang = "fr" if project.name == DEMO_PROJECT_NAME_FR else "en"
        fresh = _decision_integration(lang)
        if current == fresh:
            continue
        if not dry_run:
            analysis.report = json.dumps(fresh)
        updated += 1
    return updated


def run(dry_run: bool, company_id: str | None, db=None) -> dict:
    owns_session = db is None
    if owns_session:
        db = SessionLocal()
    try:
        notes = _backfill_guide_notes(db, dry_run, company_id)
        surveys = _backfill_surveys(db, dry_run, company_id)
        reports = _backfill_decision_reports(db, dry_run, company_id)
        if not dry_run:
            db.commit()
        verb = "would update" if dry_run else "updated"
        print(
            f"Done: {verb} {notes} guide question(s), upgraded {surveys} "
            f"survey(s), refreshed {reports} decision report(s)"
            f"{' (dry-run — nothing written)' if dry_run else ''}."
        )
        return {"guide_questions": notes, "surveys": surveys, "reports": reports}
    finally:
        if owns_session:
            db.close()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Backfill existing demo projects with the showcase upgrade."
    )
    ap.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    ap.add_argument("--company", type=str, default=None, help="restrict to one company id")
    args = ap.parse_args()
    run(dry_run=args.dry_run, company_id=args.company)


if __name__ == "__main__":
    main()
