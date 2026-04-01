from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.project import InterviewGuideQuestion, Project
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    QuestionResponse,
)
from app.services.guide_parser import parse_guide_csv

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ProjectResponse:
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
    results = []
    for p in projects:
        results.append(
            ProjectListResponse(
                id=p.id,
                name=p.name,
                language=p.language,
                created_at=p.created_at,
                question_count=len(p.guide_questions),
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
    if body.system_prompt is not None:
        project.system_prompt = body.system_prompt

    # Replace all questions
    for q in list(project.guide_questions):
        db.delete(q)
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
        )
        for q in sorted(project.guide_questions, key=lambda q: (q.section_index, q.question_index))
    ]
    return ProjectResponse(
        id=project.id,
        company_id=project.company_id,
        name=project.name,
        language=project.language,
        interview_duration_minutes=project.interview_duration_minutes,
        system_prompt=project.system_prompt,
        research_objective=project.research_objective,
        created_at=project.created_at,
        questions=questions,
    )
