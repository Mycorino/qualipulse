"""Study provisioning — keep every Project + Survey inside a Study.

Sprint 15 of the integration phase. v1 left a gap: projects created
after Alembic 0024 got ``study_id = NULL`` because no creation path
set it. This module is the single helper every project-creating path
now routes through, so no new orphans appear.

Decision 8 (implicit Study creation) holds: researchers never see a
"create a Study first" step. A Study is auto-created, named after the
instrument that spawned it.
"""

from sqlalchemy.orm import Session

from app.models.study import Study


def create_study(db: Session, company_id: str, name: str) -> Study:
    """Create + flush a new Study. Caller commits."""

    study = Study(company_id=company_id, name=name)
    db.add(study)
    db.flush()
    return study


def resolve_study(db: Session, company_id: str, study_id: str) -> Study | None:
    """Return the Study iff it exists AND belongs to this workspace.

    Returns None for a missing or cross-workspace id — callers that want
    a hard 404 check the None themselves.
    """

    return (
        db.query(Study)
        .filter(Study.id == study_id, Study.company_id == company_id)
        .first()
    )


def study_for_new_project(
    db: Session,
    company_id: str,
    project_name: str,
    study_id: str | None,
) -> Study:
    """Resolve the Study a brand-new Project should belong to.

    - `study_id` given + valid + owned → that Study (project is being
      created inside an existing Study, e.g. from the Study Overview).
    - `study_id` given but invalid → ValueError (the router turns this
      into a 404; we don't silently mis-file the project).
    - `study_id` omitted → a fresh Study named after the project
      (Decision 8 — implicit creation).
    """

    if study_id:
        study = resolve_study(db, company_id, study_id)
        if study is None:
            raise ValueError("Study not found")
        return study
    return create_study(db, company_id, project_name)
