"""The quality_status the API reports, versus the one stored on the row.

An assessment that dies with its Cloud Run instance never reaches the except
branch that stamps quality_status="failed", so the column stays NULL and the
panel would offer "still running" forever with no way to retry. Rows that
failed before the stamp existed have the same shape. The API therefore
derives the status it reports rather than echoing the column.
"""

from datetime import datetime, timedelta

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.routers.export import _effective_quality_status


def _participant(db_session, **kwargs):
    suffix = kwargs.pop("suffix", "1")
    company = Company(name="Co", email=f"status{suffix}@example.com", password_hash="x")
    db_session.add(company)
    db_session.commit()
    project = Project(company_id=company.id, name="Study", language="en")
    db_session.add(project)
    db_session.commit()
    link = InterviewLink(project_id=project.id, token=f"tok-status-{suffix}")
    db_session.add(link)
    db_session.commit()
    p = Participant(link_id=link.id, project_id=project.id, display_name="P", **kwargs)
    db_session.add(p)
    db_session.commit()
    db_session.add(
        InterviewTurn(
            participant_id=p.id,
            turn_index=0,
            question_index=0,
            question_text="Q?",
            response_transcript="A reasonably long answer about the topic at hand.",
        )
    )
    db_session.commit()
    return p


class TestEffectiveQualityStatus:
    def test_summary_present_reads_ok_even_on_a_legacy_row(self, db_session):
        # Rows assessed before the column existed carry NULL but a summary.
        p = _participant(
            db_session,
            suffix="legacy",
            status="completed",
            completed_at=datetime.utcnow() - timedelta(days=30),
            quality_summary="An assessment from before quality_status existed.",
            quality_status=None,
        )
        assert _effective_quality_status(p) == "ok"

    def test_recent_completion_without_a_summary_is_still_in_flight(self, db_session):
        p = _participant(
            db_session,
            suffix="inflight",
            status="completed",
            completed_at=datetime.utcnow() - timedelta(seconds=30),
        )
        assert _effective_quality_status(p) is None

    def test_old_completion_without_a_summary_reads_failed(self, db_session):
        # The case that stranded a real interview: it crashed before the stamp
        # existed, so nothing ever recorded the failure.
        p = _participant(
            db_session,
            suffix="stranded",
            status="completed",
            completed_at=datetime.utcnow() - timedelta(hours=3),
        )
        assert _effective_quality_status(p) == "failed"

    def test_explicit_failure_stamp_is_honoured_immediately(self, db_session):
        p = _participant(
            db_session,
            suffix="stamped",
            status="completed",
            completed_at=datetime.utcnow(),
            quality_status="failed",
        )
        assert _effective_quality_status(p) == "failed"

    def test_in_progress_participant_is_never_marked_failed(self, db_session):
        p = _participant(db_session, suffix="running", status="in_progress")
        assert _effective_quality_status(p) is None

    def test_completed_without_a_timestamp_is_never_marked_failed(self, db_session):
        p = _participant(
            db_session, suffix="nots", status="completed", completed_at=None
        )
        assert _effective_quality_status(p) is None


class TestParticipantListReportsDerivedStatus:
    def test_list_endpoint_surfaces_failed_for_a_stranded_row(
        self, client, db_session, auth_headers, registered_company
    ):
        company = (
            db_session.query(Company)
            .filter(Company.email == registered_company["email"])
            .first()
        )
        test_project = Project(company_id=company.id, name="Study", language="en")
        db_session.add(test_project)
        db_session.commit()
        link = InterviewLink(project_id=test_project.id, token="tok-status-api")
        db_session.add(link)
        db_session.commit()
        p = Participant(
            link_id=link.id,
            project_id=test_project.id,
            display_name="Stranded",
            status="completed",
            completed_at=datetime.utcnow() - timedelta(hours=3),
        )
        db_session.add(p)
        db_session.commit()
        db_session.add(
            InterviewTurn(
                participant_id=p.id,
                turn_index=0,
                question_index=0,
                question_text="Q?",
                response_transcript="A long enough answer to score on.",
            )
        )
        db_session.commit()

        r = client.get(f"/projects/{test_project.id}/participants", headers=auth_headers)
        assert r.status_code == 200
        row = next(x for x in r.json() if x["id"] == p.id)
        assert row["quality_status"] == "failed"
        # The heuristic label is still populated, which is exactly why it can
        # never be used as proof that an assessment ran.
        assert row["quality_label"]
        assert not row["quality_summary"]
