"""Cross-study synthesis endpoints — decision memos across several Studies."""

import json
import logging
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.study import Study
from app.models.synthesis import CrossStudySynthesis
from app.services.report_export import render_decision_memo_html
from app.services.study_synthesis import gather_study_evidence, run_cross_synthesis

logger = logging.getLogger("auto_interview.synthesis")
router = APIRouter(prefix="/synthesis", tags=["synthesis"])

MAX_STUDIES_PER_MEMO = 8


class SynthesisCreateRequest(BaseModel):
    study_ids: list[str] = Field(min_length=2, max_length=MAX_STUDIES_PER_MEMO)
    name: str | None = None
    decision_question: str | None = None


def _spawn_synthesis_thread(synthesis_id: str) -> None:
    """Run the memo generation on a fresh session — module-level so tests can
    monkeypatch it away and drive run_cross_synthesis synchronously."""

    def _run() -> None:
        bg_db = SessionLocal()
        try:
            run_cross_synthesis(synthesis_id, bg_db)
        finally:
            bg_db.close()

    threading.Thread(target=_run, daemon=True).start()


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
def create_synthesis(
    body: SynthesisCreateRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Kick off a decision memo across 2..N of the company's studies.

    Validates eligibility upfront (every study must have at least one ready
    analysis) so the researcher gets an actionable 400 instead of a memo row
    that fails minutes later.
    """
    unique_ids = list(dict.fromkeys(body.study_ids))
    studies = (
        db.query(Study)
        .filter(Study.id.in_(unique_ids), Study.company_id == company.id)
        .all()
    )
    if len(studies) != len(unique_ids):
        raise HTTPException(status_code=404, detail="One or more studies not found.")

    not_ready = [s.name for s in studies if gather_study_evidence(s, db) is None]
    if not_ready:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "studies_not_ready",
                "message": "Every study needs a ready analysis before it can join a memo.",
                "studies": not_ready,
            },
        )

    name = (body.name or "").strip() or " × ".join(s.name for s in studies[:3])
    synthesis = CrossStudySynthesis(
        company_id=company.id,
        name=name[:255],
        decision_question=(body.decision_question or "").strip() or None,
        study_ids=json.dumps(unique_ids),
        language=(company.preferred_language or "en"),
        status="generating",
    )
    db.add(synthesis)
    db.commit()

    _spawn_synthesis_thread(synthesis.id)
    return {"id": synthesis.id, "status": "generating"}


@router.get("/")
def list_syntheses(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    rows = (
        db.query(CrossStudySynthesis)
        .filter(CrossStudySynthesis.company_id == company.id)
        .order_by(CrossStudySynthesis.created_at.desc())
        .all()
    )
    out = []
    for r in rows:
        try:
            study_ids = json.loads(r.study_ids)
        except Exception:
            study_ids = []
        names = [
            s.name
            for s in db.query(Study).filter(Study.id.in_(study_ids)).all()
        ] if study_ids else []
        out.append({
            "id": r.id,
            "name": r.name,
            "status": r.status,
            "study_count": len(study_ids),
            "study_names": names,
            "decision_question": r.decision_question,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "error": r.error,
        })
    return out


@router.get("/{synthesis_id}")
def get_synthesis(
    synthesis_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    synthesis = _get_synthesis_or_404(synthesis_id, company.id, db)
    return {
        "id": synthesis.id,
        "name": synthesis.name,
        "status": synthesis.status,
        "decision_question": synthesis.decision_question,
        "study_ids": json.loads(synthesis.study_ids),
        "report": json.loads(synthesis.report) if synthesis.report else None,
        "error": synthesis.error,
        "generated_at": synthesis.generated_at.isoformat() if synthesis.generated_at else None,
    }


@router.get("/{synthesis_id}/report.html", response_class=HTMLResponse)
def export_synthesis_memo(
    synthesis_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Render the decision memo as a standalone, print-ready HTML document."""
    synthesis = _get_synthesis_or_404(synthesis_id, company.id, db)
    if synthesis.status != "ready" or not synthesis.report:
        raise HTTPException(status_code=404, detail="Memo is not ready yet.")

    study_ids = json.loads(synthesis.study_ids)
    studies = db.query(Study).filter(Study.id.in_(study_ids)).all()
    studies_meta = []
    for s in studies:
        evidence = gather_study_evidence(s, db)
        qual = evidence.get("project_analysis") if evidence else None
        studies_meta.append({
            "name": s.name,
            "participant_count": qual.participant_count if qual else None,
            "confidence": (json.loads(qual.report).get("confidence") if qual and qual.report else None),
            "generated_at": qual.generated_at if qual else None,
            "has_mixed_methods": bool(evidence and evidence.get("study_analysis")),
        })

    html_doc = render_decision_memo_html(synthesis, studies_meta, company_name=company.name)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", synthesis.name).strip("_") or "memo"
    return HTMLResponse(
        content=html_doc,
        headers={"Content-Disposition": f'inline; filename="{slug}_decision_memo.html"'},
    )


@router.delete("/{synthesis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_synthesis(
    synthesis_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    synthesis = _get_synthesis_or_404(synthesis_id, company.id, db)
    db.delete(synthesis)
    db.commit()


def _get_synthesis_or_404(synthesis_id: str, company_id: str, db: Session) -> CrossStudySynthesis:
    synthesis = (
        db.query(CrossStudySynthesis)
        .filter(
            CrossStudySynthesis.id == synthesis_id,
            CrossStudySynthesis.company_id == company_id,
        )
        .first()
    )
    if synthesis is None:
        raise HTTPException(status_code=404, detail="Synthesis not found")
    return synthesis
