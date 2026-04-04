import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    QuestionPatch,
    QuestionResponse,
    ScreeningQuestionResponse,
)
from app.services.feature_gates import require_project_limit
from app.services.guide_parser import parse_guide_csv

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    current_count = db.query(Project).filter(Project.company_id == company.id).count()
    require_project_limit(company, current_count)
    project = Project(
        company_id=company.id,
        name=body.name,
        language=body.language,
        interview_duration_minutes=body.interview_duration_minutes,
        system_prompt=body.system_prompt or Project.__table__.columns["system_prompt"].default.arg,
        research_objective=body.research_objective or None,
    )
    db.add(project)
    db.flush()

    for idx, q in enumerate(body.questions):
        question = InterviewGuideQuestion(
            project_id=project.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes or "",
            desired_learning=q.desired_learning or "",
            sort_order=idx,
        )
        db.add(question)

    for idx, sq in enumerate(body.screening_questions):
        db.add(ScreeningQuestion(
            project_id=project.id,
            sort_order=idx,
            question=sq.question,
            options=json.dumps(sq.options),
            disqualifying_options=json.dumps(sq.disqualifying_options),
        ))

    db.commit()
    db.refresh(project)

    return _project_to_response(project)


@router.post("/import", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def import_project_from_csv(
    name: str = Form(...),
    language: str = Form("en"),
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    content = await csv_file.read()
    questions = parse_guide_csv(content)

    project = Project(
        company_id=company.id,
        name=name,
        language=language,
    )
    db.add(project)
    db.flush()

    for idx, q in enumerate(questions):
        question = InterviewGuideQuestion(
            project_id=project.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes or "",
            desired_learning=q.desired_learning or "",
            sort_order=idx,
        )
        db.add(question)

    db.commit()
    db.refresh(project)

    return _project_to_response(project)


@router.get("/", response_model=list[ProjectListResponse])
def list_projects(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[ProjectListResponse]:
    projects = (
        db.query(Project)
        .filter(Project.company_id == company.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    from app.models.interview import Participant, ProjectAnalysis
    results = []
    for p in projects:
        completed = sum(1 for pt in p.participants if pt.status == "completed")
        in_progress = sum(1 for pt in p.participants if pt.status == "in_progress")
        latest_analysis = (
            db.query(ProjectAnalysis)
            .filter(ProjectAnalysis.project_id == p.id)
            .order_by(ProjectAnalysis.version.desc())
            .first()
        )
        results.append(
            ProjectListResponse(
                id=p.id,
                name=p.name,
                language=p.language,
                created_at=p.created_at,
                question_count=len(p.guide_questions),
                completed_count=completed,
                in_progress_count=in_progress,
                analysis_status=latest_analysis.status if latest_analysis else None,
            )
        )
    return results


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    project = _get_project_or_404(project_id, company.id, db)
    return _project_to_response(project)


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    body: ProjectCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
    project = _get_project_or_404(project_id, company.id, db)

    project.name = body.name
    project.language = body.language
    project.interview_duration_minutes = body.interview_duration_minutes
    project.research_objective = body.research_objective or None
    project.welcome_message = body.welcome_message or None
    if body.system_prompt is not None:
        project.system_prompt = body.system_prompt

    # Replace all questions and screening questions
    for q in list(project.guide_questions):
        db.delete(q)
    for sq in list(project.screening_questions):
        db.delete(sq)
    db.flush()

    for idx, q in enumerate(body.questions):
        question = InterviewGuideQuestion(
            project_id=project.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes or "",
            desired_learning=q.desired_learning or "",
            sort_order=idx,
        )
        db.add(question)

    for idx, sq in enumerate(body.screening_questions):
        db.add(ScreeningQuestion(
            project_id=project.id,
            sort_order=idx,
            question=sq.question,
            options=json.dumps(sq.options),
            disqualifying_options=json.dumps(sq.disqualifying_options),
        ))

    db.commit()
    db.refresh(project)
    return _project_to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> None:
    project = _get_project_or_404(project_id, company.id, db)
    db.delete(project)
    db.commit()


@router.patch("/{project_id}/questions/{question_id}", response_model=QuestionResponse)
def patch_question(
    project_id: str,
    question_id: str,
    body: QuestionPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> QuestionResponse:
    """Update researcher_notes and/or deprecated_at for a guide question."""
    project = _get_project_or_404(project_id, company.id, db)

    question = (
        db.query(InterviewGuideQuestion)
        .filter(
            InterviewGuideQuestion.id == question_id,
            InterviewGuideQuestion.project_id == project.id,
        )
        .first()
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    if body.researcher_notes is not None:
        question.researcher_notes = body.researcher_notes
    if body.interview_notes is not None:
        question.interview_notes = body.interview_notes
    if body.desired_learning is not None:
        question.desired_learning = body.desired_learning
    # Allow setting deprecated_at to a value or clearing it (None = un-deprecate)
    if "deprecated_at" in body.model_fields_set:
        question.deprecated_at = body.deprecated_at

    db.commit()
    db.refresh(question)

    return QuestionResponse(
        id=question.id,
        section_index=question.section_index,
        section_title=question.section_title,
        question_index=question.question_index,
        main_question=question.main_question,
        interview_notes=question.interview_notes,
        desired_learning=question.desired_learning,
        researcher_notes=question.researcher_notes,
        deprecated_at=question.deprecated_at,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_project_or_404(project_id: str, company_id: str, db: Session) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _project_to_response(project: Project) -> ProjectResponse:
    questions = [
        QuestionResponse(
            id=q.id,
            section_index=q.section_index,
            section_title=q.section_title,
            question_index=q.question_index,
            main_question=q.main_question,
            interview_notes=q.interview_notes,
            desired_learning=q.desired_learning,
            researcher_notes=q.researcher_notes,
            deprecated_at=q.deprecated_at,
        )
        for q in sorted(project.guide_questions, key=lambda q: (q.section_index, q.question_index))
    ]
    screening = [
        ScreeningQuestionResponse(
            id=sq.id,
            question=sq.question,
            options=sq.options_list,
            disqualifying_options=sq.disqualifying_options_list,
            sort_order=sq.sort_order,
        )
        for sq in sorted(project.screening_questions, key=lambda sq: sq.sort_order)
    ]
    return ProjectResponse(
        id=project.id,
        company_id=project.company_id,
        name=project.name,
        language=project.language,
        interview_duration_minutes=project.interview_duration_minutes,
        system_prompt=project.system_prompt,
        research_objective=project.research_objective,
        welcome_message=project.welcome_message,
        created_at=project.created_at,
        questions=questions,
        screening_questions=screening,
    )
