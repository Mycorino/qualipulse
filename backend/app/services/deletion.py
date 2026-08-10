"""GDPR cascade deletion — participant, project, and company scopes.

Single source of truth for "what happens when X is erased". Used by:
- DELETE /projects/{id}/participants/{pid}  (routers/export.py)
- DELETE /projects/{id}                     (routers/projects.py)
- POST   /auth/delete-account               (routers/auth.py, self-serve GDPR)
- DELETE /admin/users/{company_id}          (routers/admin.py)

Design notes:
- SQLite dev does not enforce FK constraints, and Postgres FK cascades only
  cover tables whose constraints exist — so every child table is deleted
  explicitly here, in dependency order.
- Audio files (participant recordings + TTS clips) are deleted best-effort
  via storage.delete_audio_by_url; a missing blob never aborts the cascade.
- Deliberately retained on participant/project deletion:
  * CreditLedger / UsageEvent rows — financial audit trail; they carry only
    a pseudonymous participant/project id (no FK), kept on purpose.
  * AIUsageLog rows — cost accounting; their participant_id/project_id FKs
    are SET NULL, which we mirror explicitly for SQLite parity.
  On company deletion the billing rows go too (the workspace itself is being
  erased; the FKs are ON DELETE CASCADE on Postgres anyway).
"""

import logging

from sqlalchemy import delete as sql_delete, update as sql_update
from sqlalchemy.orm import Session

from app.models.affiliate import Affiliate, AffiliateReferral
from app.models.admin_audit import AdminAuditLog
from app.models.billing import (
    CreditBalance,
    CreditLedger,
    UsageEvent,
    WorkspaceSubscription,
)
from app.models.coding import ManualCode, QuoteTag
from app.models.company import Company, EmailVerificationToken, PasswordResetToken
from app.models.copilot import CopilotConversation, CopilotMemory
from app.models.email_log import EmailSendLog
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.memo import ProjectMemo
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.models.research_plan import ResearchPlan, ResearchPlanStep
from app.models.study import (
    ConsentAcknowledgment,
    Study,
    StudyAnalysis,
    StudyParticipant,
)
from app.models.survey import (
    Survey,
    SurveyLink,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.models.synthesis import CrossStudySynthesis
from app.models.team import WorkspaceInvitation, WorkspaceMember
from app.models.usage import AIUsageLog
from app.services.storage import delete_audio_by_url

logger = logging.getLogger(__name__)


def _delete_turn_audio(urls: list[str | None]) -> int:
    """Best-effort deletion of a batch of audio URLs. Returns files removed."""
    deleted = 0
    for url in urls:
        if url and delete_audio_by_url(url):
            deleted += 1
    return deleted


def _collect_turn_audio_urls(db: Session, turn_ids: list[str]) -> list[str | None]:
    if not turn_ids:
        return []
    rows = (
        db.query(InterviewTurn.audio_recording_url, InterviewTurn.tts_audio_url)
        .filter(InterviewTurn.id.in_(turn_ids))
        .all()
    )
    urls: list[str | None] = []
    for recording_url, tts_url in rows:
        urls.append(recording_url)
        urls.append(tts_url)
    return urls


def _delete_interview_graph(
    db: Session, participant_ids: list[str], *, delete_files: bool
) -> dict:
    """Delete QuoteTags → InterviewTurns for a set of participants (+ audio).

    Does NOT delete the Participant rows themselves — callers handle that
    (participant scope deletes one row; project scope bulk-deletes by project).
    """
    counts = {"quote_tags": 0, "turns": 0, "audio_files": 0}
    if not participant_ids:
        return counts

    turn_ids = [
        row[0]
        for row in db.query(InterviewTurn.id)
        .filter(InterviewTurn.participant_id.in_(participant_ids))
        .all()
    ]
    if turn_ids:
        audio_urls = _collect_turn_audio_urls(db, turn_ids) if delete_files else []
        result = db.execute(sql_delete(QuoteTag).where(QuoteTag.turn_id.in_(turn_ids)))
        counts["quote_tags"] = result.rowcount or 0
        result = db.execute(
            sql_delete(InterviewTurn).where(InterviewTurn.id.in_(turn_ids))
        )
        counts["turns"] = result.rowcount or 0
        if delete_files:
            counts["audio_files"] = _delete_turn_audio(audio_urls)

    # AIUsageLog.participant_id is ON DELETE SET NULL on Postgres; mirror it
    # explicitly so SQLite dev behaves identically. Rows stay (cost audit).
    db.execute(
        sql_update(AIUsageLog)
        .where(AIUsageLog.participant_id.in_(participant_ids))
        .values(participant_id=None)
    )
    return counts


def delete_participant_data(
    db: Session, participant: Participant, *, delete_files: bool = True
) -> dict:
    """Erase one participant: quote tags, turns, audio files, participant row.

    CreditLedger / UsageEvent rows referencing the participant id are kept on
    purpose — financial audit trail, pseudonymous id only.
    """
    counts = _delete_interview_graph(db, [participant.id], delete_files=delete_files)
    db.execute(sql_delete(Participant).where(Participant.id == participant.id))
    counts["participants"] = 1
    db.commit()
    return counts


def delete_project_data(
    db: Session, project: Project, *, delete_files: bool = True
) -> dict:
    """Erase one project and everything hanging off it.

    Leaves the parent Study row alone (surveys may still live under it) and
    nulls ResearchPlanStep.project_id instead of deleting the plan step.
    """
    project_id = project.id

    participant_ids = [
        row[0]
        for row in db.query(Participant.id)
        .filter(Participant.project_id == project_id)
        .all()
    ]
    counts = _delete_interview_graph(db, participant_ids, delete_files=delete_files)
    result = db.execute(
        sql_delete(Participant).where(Participant.project_id == project_id)
    )
    counts["participants"] = result.rowcount or 0

    analysis_ids = [
        row[0]
        for row in db.query(ProjectAnalysis.id)
        .filter(ProjectAnalysis.project_id == project_id)
        .all()
    ]
    if analysis_ids:
        db.execute(
            sql_delete(AnalysisThemeAnnotation).where(
                AnalysisThemeAnnotation.analysis_id.in_(analysis_ids)
            )
        )
    result = db.execute(
        sql_delete(ProjectAnalysis).where(ProjectAnalysis.project_id == project_id)
    )
    counts["analyses"] = result.rowcount or 0

    for model in (ManualCode, ProjectMemo, InterviewGuideQuestion, ScreeningQuestion, InterviewLink):
        db.execute(sql_delete(model).where(model.project_id == project_id))

    # A research-plan step drafted as this project keeps its place in the
    # plan — only the link is cleared.
    db.execute(
        sql_update(ResearchPlanStep)
        .where(ResearchPlanStep.project_id == project_id)
        .values(project_id=None, status="pending")
    )

    # AIUsageLog.project_id is ON DELETE SET NULL; mirror explicitly.
    db.execute(
        sql_update(AIUsageLog)
        .where(AIUsageLog.project_id == project_id)
        .values(project_id=None)
    )

    # The copilot chat thread about this project can quote its data.
    db.execute(
        sql_delete(CopilotConversation).where(
            CopilotConversation.scope_kind == "project",
            CopilotConversation.scope_id == project_id,
        )
    )

    db.execute(sql_delete(Project).where(Project.id == project_id))
    counts["projects"] = 1
    db.commit()
    return counts


def delete_company_data(db: Session, company: Company, *, delete_files: bool = True) -> dict:
    """Full GDPR erasure of a company/workspace and all data it owns.

    Shared by admin DELETE /admin/users/{id} and self-serve
    POST /auth/delete-account. Commits. Returns a summary dict.
    """
    company_id = company.id
    summary: dict = {
        "projects": 0,
        "participants": 0,
        "turns": 0,
        "audio_files": 0,
    }

    projects = db.query(Project).filter(Project.company_id == company_id).all()
    for project in projects:
        counts = delete_project_data(db, project, delete_files=delete_files)
        summary["projects"] += counts.get("projects", 0)
        summary["participants"] += counts.get("participants", 0)
        summary["turns"] += counts.get("turns", 0)
        summary["audio_files"] += counts.get("audio_files", 0)

    # ── Study graph (surveys, responses, study participants) ──────────────
    study_ids = [
        row[0]
        for row in db.query(Study.id).filter(Study.company_id == company_id).all()
    ]
    survey_ids = [
        row[0]
        for row in db.query(Survey.id).filter(Survey.company_id == company_id).all()
    ]
    response_ids = [
        row[0]
        for row in db.query(SurveyResponse.id)
        .filter(SurveyResponse.company_id == company_id)
        .all()
    ]
    if response_ids:
        db.execute(
            sql_delete(SurveyResponseAnswer).where(
                SurveyResponseAnswer.response_id.in_(response_ids)
            )
        )
        db.execute(
            sql_delete(SurveyResponse).where(SurveyResponse.id.in_(response_ids))
        )
    if survey_ids:
        db.execute(sql_delete(SurveyLink).where(SurveyLink.survey_id.in_(survey_ids)))
        db.execute(
            sql_delete(SurveyQuestion).where(SurveyQuestion.survey_id.in_(survey_ids))
        )
        db.execute(sql_delete(Survey).where(Survey.id.in_(survey_ids)))
    if study_ids:
        participant_row_ids = [
            row[0]
            for row in db.query(StudyParticipant.id)
            .filter(StudyParticipant.study_id.in_(study_ids))
            .all()
        ]
        if participant_row_ids:
            db.execute(
                sql_delete(ConsentAcknowledgment).where(
                    ConsentAcknowledgment.study_participant_id.in_(participant_row_ids)
                )
            )
            db.execute(
                sql_delete(StudyParticipant).where(
                    StudyParticipant.id.in_(participant_row_ids)
                )
            )
        db.execute(
            sql_delete(StudyAnalysis).where(StudyAnalysis.study_id.in_(study_ids))
        )
        db.execute(sql_delete(Study).where(Study.id.in_(study_ids)))
    summary["studies"] = len(study_ids)

    # ── Research plans ────────────────────────────────────────────────────
    plan_ids = [
        row[0]
        for row in db.query(ResearchPlan.id)
        .filter(ResearchPlan.company_id == company_id)
        .all()
    ]
    if plan_ids:
        db.execute(
            sql_delete(ResearchPlanStep).where(ResearchPlanStep.plan_id.in_(plan_ids))
        )
        db.execute(sql_delete(ResearchPlan).where(ResearchPlan.id.in_(plan_ids)))

    # ── Company-scoped rows ───────────────────────────────────────────────
    db.execute(
        sql_delete(CrossStudySynthesis).where(
            CrossStudySynthesis.company_id == company_id
        )
    )
    db.execute(sql_delete(CopilotMemory).where(CopilotMemory.company_id == company_id))
    db.execute(
        sql_delete(CopilotConversation).where(
            CopilotConversation.company_id == company_id
        )
    )
    db.execute(sql_delete(EmailSendLog).where(EmailSendLog.company_id == company_id))
    db.execute(
        sql_delete(EmailVerificationToken).where(
            EmailVerificationToken.company_id == company_id
        )
    )
    db.execute(
        sql_delete(PasswordResetToken).where(
            PasswordResetToken.company_id == company_id
        )
    )

    # ── Team workspace links (both directions) ────────────────────────────
    db.execute(
        sql_delete(WorkspaceMember).where(
            (WorkspaceMember.workspace_company_id == company_id)
            | (WorkspaceMember.member_company_id == company_id)
        )
    )
    db.execute(
        sql_delete(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_company_id == company_id
        )
    )
    db.execute(
        sql_update(WorkspaceInvitation)
        .where(WorkspaceInvitation.invited_by_company_id == company_id)
        .values(invited_by_company_id=None)
    )

    # ── Billing (the workspace itself is being erased; FKs are ON DELETE
    # CASCADE on Postgres, so mirror that explicitly for SQLite parity) ────
    db.execute(sql_delete(CreditLedger).where(CreditLedger.workspace_id == company_id))
    db.execute(
        sql_delete(CreditBalance).where(CreditBalance.workspace_id == company_id)
    )
    db.execute(
        sql_delete(WorkspaceSubscription).where(
            WorkspaceSubscription.workspace_id == company_id
        )
    )
    db.execute(sql_delete(UsageEvent).where(UsageEvent.workspace_id == company_id))
    db.execute(sql_delete(AIUsageLog).where(AIUsageLog.company_id == company_id))

    # ── Affiliate + audit references (mirror their SET NULL / CASCADE) ────
    db.execute(
        sql_update(Affiliate)
        .where(Affiliate.company_id == company_id)
        .values(company_id=None)
    )
    db.execute(
        sql_delete(AffiliateReferral).where(
            AffiliateReferral.referred_company_id == company_id
        )
    )
    db.execute(
        sql_update(AdminAuditLog)
        .where(AdminAuditLog.target_company_id == company_id)
        .values(target_company_id=None)
    )

    db.execute(sql_delete(Company).where(Company.id == company_id))
    summary["company"] = 1
    db.commit()
    return summary
