"""Participant-facing unfurl card for interview links.

Interview links are shared with participants, so the preview must speak to
them (in the study's language) and must never leak the identity of an
anonymous study. nginx routes only link unfurlers here; see
`services/interview_preview.py` and `frontend/nginx.conf.template`.
"""
import pytest

from app.models.company import Company
from app.models.interview import InterviewLink
from app.models.project import Project


@pytest.fixture
def study(client, db_session):
    company = Company(
        name="Acme Research", email="owner@acme.com", password_hash="x", email_verified=True
    )
    db_session.add(company)
    db_session.flush()
    project = Project(
        company_id=company.id,
        name="Courses en ligne",
        language="fr",
        interview_duration_minutes=20,
    )
    db_session.add(project)
    db_session.flush()
    link = InterviewLink(project_id=project.id, token="tok-preview", is_active=True)
    db_session.add(link)
    db_session.commit()
    return {"company": company, "project": project, "link": link}


def test_preview_is_participant_facing_in_the_study_language(client, study):
    resp = client.get("/interview/tok-preview/preview")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text

    # Study name leads the card, exactly like the participant landing screen.
    assert '<meta property="og:title" content="Courses en ligne" />' in html
    # Description is French (the study language), names the inviter, and
    # carries the real duration.
    assert "Acme Research vous invite à un entretien vocal." in html
    assert "environ 20 minutes" in html
    # Participant artwork, not the marketing card.
    assert "og-interview-fr.png" in html
    assert "og-image.png" not in html
    # Token URLs never belong in a search index.
    assert '<meta name="robots" content="noindex, nofollow" />' in html


def test_preview_uses_researcher_name_when_set(client, db_session, study):
    study["project"].researcher_name = "Studio Métro"
    db_session.commit()

    html = client.get("/interview/tok-preview/preview").text

    assert "Studio Métro vous invite" in html
    assert "Acme Research" not in html


def test_anonymous_study_never_names_the_organisation(client, db_session, study):
    study["project"].branding_mode = "anonymous"
    study["project"].researcher_name = "Studio Métro"
    db_session.commit()

    html = client.get("/interview/tok-preview/preview").text

    assert "Acme Research" not in html
    assert "Studio Métro" not in html
    assert "Vous êtes invité·e à participer à un entretien de recherche." in html


def test_english_study_gets_english_copy_and_artwork(client, db_session, study):
    study["project"].language = "en"
    db_session.commit()

    html = client.get("/interview/tok-preview/preview").text

    assert "invites you to a voice interview." in html
    assert "og-interview-en.png" in html


def test_study_name_is_escaped(client, db_session, study):
    study["project"].name = 'Pricing <script>alert("x")</script>'
    db_session.commit()

    html = client.get("/interview/tok-preview/preview").text

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_unknown_or_inactive_link_renders_a_useful_card(client, db_session, study):
    study["link"].is_active = False
    db_session.commit()

    for path in ("/interview/tok-preview/preview", "/interview/nope/preview"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        # Default language when there is no study to read it from.
        assert "This interview link is no longer active" in resp.text
        # Nothing to open, so no CTA either.
        assert "app=1" not in resp.text


def test_preview_offers_an_escape_hatch_out_of_the_preview(client, study):
    html = client.get("/interview/tok-preview/preview").text

    # The visible CTA must carry ?app=1: nginx never routes that back here,
    # so a human misdetected as a crawler reaches the real interview.
    assert "/i/tok-preview?app=1" in html
