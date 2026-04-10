"""Seed a read-only demo project for new users so they can explore the full app.

Creates a fully-populated sample project (with completed participants, transcripts,
and a finished AI analysis) so new researchers can click around, see themes, open
transcripts, and export CSV before they run their own study.

The seeded data is persisted like a regular project — the only thing that marks it
as a demo is its name prefix and the fact that `is_demo_seeded` is tracked on the
company record (so we only seed once per account).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.interview import (
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.project import InterviewGuideQuestion, Project


DEMO_PROJECT_NAME = "[Demo] Customer Discovery — Productivity App"

DEMO_RESEARCH_OBJECTIVE = (
    "Understand how knowledge workers currently manage their daily tasks and "
    "identify the biggest frustrations with existing productivity tools, so we "
    "can design a mobile-first app that feels effortless for busy professionals."
)

DEMO_WELCOME_MESSAGE = (
    "Hi, thanks for joining! This is a short conversation about how you manage "
    "your work day — there are no right or wrong answers, just share what comes "
    "to mind."
)

DEMO_GUIDE: list[dict] = [
    {
        "section": "Context",
        "questions": [
            {
                "q": "Tell me a bit about your typical work day. How do you currently plan what you'll get done?",
                "learning": "Baseline routine, existing habits, planning frequency.",
            },
        ],
    },
    {
        "section": "Tools in use",
        "questions": [
            {
                "q": "What tools or apps do you use to keep track of tasks and projects? Walk me through the ones you touch every day.",
                "learning": "Current tool stack, switching cost, native vs third-party.",
            },
            {
                "q": "Which of those do you actually enjoy using, and which feel like a chore?",
                "learning": "Emotional relationship with tools, pain points.",
            },
        ],
    },
    {
        "section": "Pain & desired outcomes",
        "questions": [
            {
                "q": "Think back to the last time you felt overwhelmed by your to-do list. What was going on?",
                "learning": "Overload triggers, coping mechanisms.",
            },
            {
                "q": "If a magic wand could fix one thing about how you organise your work, what would it be?",
                "learning": "Jobs-to-be-done, aspirational state.",
            },
        ],
    },
]


# A list of fake completed interviews (participant + turns). Quotes are realistic
# but fully synthetic — nothing here is from a real person.
DEMO_PARTICIPANTS: list[dict] = [
    {
        "display_name": "Alex M.",
        "email": "alex.demo@example.com",
        "profession": "Product Manager",
        "age_range": "30-39",
        "country": "United Kingdom",
        "answers": [
            "I usually start around 8:30 by checking Slack and then I open Notion where my backlog lives. I try to block the first hour for deep work but it rarely happens — there's always a meeting or a Slack ping that pulls me away.",
            "Mostly Notion for notes and tasks, Linear for engineering tickets, Slack for everything else. I keep Google Calendar open in a separate tab. Honestly it's too many tabs.",
            "I like Linear — it feels fast and it doesn't get in the way. Notion I have a love-hate relationship with; it's flexible but things get lost in nested pages.",
            "Last Thursday I had three product reviews back-to-back and my inbox was out of control. I ended up writing things on sticky notes because I couldn't even find my own to-do list.",
            "I'd want one place that actually merges my calendar, my tasks, and my notes — and that surfaces what matters right now instead of making me dig for it.",
        ],
    },
    {
        "display_name": "Priya S.",
        "email": "priya.demo@example.com",
        "profession": "Software Engineer",
        "age_range": "25-29",
        "country": "Germany",
        "answers": [
            "I roll into my day by reviewing GitHub notifications and my Linear queue. I'm mostly heads-down coding, so I batch Slack to twice a day otherwise I get nothing done.",
            "Linear, GitHub, VS Code, Slack. I also keep a markdown file in Obsidian for personal notes — nothing fancy, just a scratchpad.",
            "VS Code and Obsidian are great, they stay out of the way. Slack on the other hand is the biggest drain on my focus.",
            "Honestly I don't feel overwhelmed by tasks that often — my manager is good at shielding me. But I do feel overwhelmed by the sheer number of notifications across apps.",
            "I wish there was a single inbox for all my tools. Right now I check four different places just to know what I should be working on.",
        ],
    },
    {
        "display_name": "Sophie L.",
        "email": "sophie.demo@example.com",
        "profession": "Freelance Designer",
        "age_range": "30-39",
        "country": "France",
        "answers": [
            "I'm freelance so every day is a bit different. I usually plan the night before in a paper notebook — yes, paper — because writing it down helps me think.",
            "Figma for design, Notion for client briefs, Superhuman for email, and honestly iMessage for most of my client comms because they prefer it.",
            "Figma is a joy. Notion I find clunky on mobile. I hate that my tasks and my emails don't talk to each other at all.",
            "Two weeks ago I missed a deliverable because it was buried in an email thread. My client wasn't happy and I felt terrible. That's when I wrote everything down on paper for two weeks.",
            "I'd love a tool that understood that most of my work lives in client threads and could pull tasks out of them automatically without me having to copy-paste.",
        ],
    },
]


DEMO_ANALYSIS_REPORT: dict = {
    "overview": (
        "Knowledge workers are juggling too many disconnected tools to manage their "
        "daily work. The biggest source of frustration is not the tools themselves "
        "but the cognitive load of switching between them. Participants repeatedly "
        "described a desire for a single pane of glass that surfaces what matters "
        "right now across tasks, notifications, and communication."
    ),
    "themes": [
        {
            "title": "Tool fragmentation creates cognitive overhead",
            "description": (
                "All three participants described using 4+ tools daily with no "
                "cross-app view. Switching between them is itself a source of stress "
                "— especially when urgent items arrive via messaging apps rather than "
                "the dedicated task tool."
            ),
            "confidence": 0.92,
            "quotes": [
                {
                    "text": "I check four different places just to know what I should be working on.",
                    "participant_display_name": "Priya S.",
                },
                {
                    "text": "Honestly it's too many tabs.",
                    "participant_display_name": "Alex M.",
                },
            ],
        },
        {
            "title": "Notifications drown out intent",
            "description": (
                "Participants actively work against their own tools to protect focus "
                "— batching Slack, turning off email, falling back to paper. Slack "
                "was singled out as the biggest drain on attention."
            ),
            "confidence": 0.88,
            "quotes": [
                {
                    "text": "Slack on the other hand is the biggest drain on my focus.",
                    "participant_display_name": "Priya S.",
                },
                {
                    "text": "I try to block the first hour for deep work but it rarely happens.",
                    "participant_display_name": "Alex M.",
                },
            ],
        },
        {
            "title": "Critical work hides inside conversations",
            "description": (
                "Tasks, briefs, and deadlines routinely live inside email threads, "
                "Slack DMs, or iMessage — not inside the task manager. This is where "
                "things fall through the cracks."
            ),
            "confidence": 0.85,
            "quotes": [
                {
                    "text": "I missed a deliverable because it was buried in an email thread.",
                    "participant_display_name": "Sophie L.",
                },
                {
                    "text": "I ended up writing things on sticky notes because I couldn't even find my own to-do list.",
                    "participant_display_name": "Alex M.",
                },
            ],
        },
    ],
    "jobs_to_be_done": [
        {
            "statement": (
                "When I start my day, I want to know exactly what needs my attention, "
                "so I can protect my focus for deep work."
            ),
            "evidence_count": 3,
        },
        {
            "statement": (
                "When important information arrives in a conversation, I want it to "
                "show up in my task list automatically, so I don't miss anything."
            ),
            "evidence_count": 2,
        },
    ],
    "tensions": [
        {
            "title": "Flexibility vs focus",
            "description": (
                "Participants love that modern tools are flexible — but that same "
                "flexibility means every team uses them differently, creating "
                "inconsistent mental models."
            ),
        },
    ],
    "recommendations": [
        {
            "title": "Prioritise a unified daily view",
            "description": (
                "The strongest signal is the desire for one place that answers "
                "'what should I be doing right now?' — prioritise this over feature "
                "depth in any single tool category."
            ),
        },
        {
            "title": "Ingest from conversation channels",
            "description": (
                "Treat Slack, email, and iMessage as first-class task sources rather "
                "than afterthoughts. Manual copy-paste is where the product will lose."
            ),
        },
        {
            "title": "Respect focus mode",
            "description": (
                "Notifications are seen as adversarial. Ship quiet-by-default "
                "and let users explicitly opt into interruptions."
            ),
        },
    ],
    "metadata": {
        "is_demo": True,
        "note": "This is synthetic demo data to help you explore the platform.",
    },
}


def seed_demo_project(db: Session, company_id: str) -> Project:
    """Create and persist a complete demo project for a company. Returns the project."""
    now = datetime.now(timezone.utc)

    project = Project(
        company_id=company_id,
        name=DEMO_PROJECT_NAME,
        language="en",
        interview_duration_minutes=15,
        welcome_message=DEMO_WELCOME_MESSAGE,
        research_objective=DEMO_RESEARCH_OBJECTIVE,
        research_context=(
            "This is a demo project created automatically so you can explore "
            "QualiPulse with real-looking data. Feel free to edit, archive, or "
            "delete it whenever you want."
        ),
        created_at=now,
    )
    db.add(project)
    db.flush()  # assign id

    # Guide questions
    sort_order = 0
    for section_index, section in enumerate(DEMO_GUIDE):
        for question_index, item in enumerate(section["questions"]):
            db.add(
                InterviewGuideQuestion(
                    project_id=project.id,
                    section_index=section_index,
                    section_title=section["section"],
                    question_index=question_index,
                    main_question=item["q"],
                    interview_notes="",
                    desired_learning=item["learning"],
                    sort_order=sort_order,
                )
            )
            sort_order += 1

    # Interview link (so the Overview tab has something to copy)
    link = InterviewLink(
        project_id=project.id,
        token=secrets.token_urlsafe(32),
        is_active=True,
        created_at=now,
    )
    db.add(link)
    db.flush()

    # Build flat ordered question list for turn generation
    flat_questions: list[str] = []
    for section in DEMO_GUIDE:
        for item in section["questions"]:
            flat_questions.append(item["q"])

    # Participants with completed turns
    for p_idx, p_data in enumerate(DEMO_PARTICIPANTS):
        started = now - timedelta(days=3 - p_idx, hours=p_idx * 2)
        completed = started + timedelta(minutes=12 + p_idx)

        participant = Participant(
            link_id=link.id,
            project_id=project.id,
            display_name=p_data["display_name"],
            email=p_data["email"],
            profession=p_data["profession"],
            age_range=p_data["age_range"],
            country=p_data["country"],
            status="completed",
            started_at=started,
            completed_at=completed,
            quality_score=0.85 + (p_idx * 0.03),
            quality_label="high",
        )
        db.add(participant)
        db.flush()

        for turn_idx, (q_text, answer) in enumerate(zip(flat_questions, p_data["answers"])):
            db.add(
                InterviewTurn(
                    participant_id=participant.id,
                    turn_index=turn_idx,
                    question_index=turn_idx,
                    is_follow_up=False,
                    follow_up_index=0,
                    question_text=q_text,
                    response_transcript=answer,
                    audio_recording_url=None,
                    tts_audio_url=None,
                    created_at=started + timedelta(minutes=turn_idx * 2),
                )
            )

    # Pre-built AI analysis (so the Analysis tab shows themes immediately)
    analysis = ProjectAnalysis(
        project_id=project.id,
        version=1,
        status="ready",
        version_label="ai_discovery",
        participant_count=len(DEMO_PARTICIPANTS),
        report=json.dumps(DEMO_ANALYSIS_REPORT),
        generated_at=now,
    )
    db.add(analysis)

    db.commit()
    db.refresh(project)
    return project
