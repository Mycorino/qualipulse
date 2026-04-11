"""Seed a rich, read-only showcase project for new users.

This seeds a single multilingual research project that demonstrates almost every
QualiPulse feature so a brand-new user can poke around and feel what a fully
populated project looks like before they run their own study:

- Two interview links (one EU, one NA paused) so the link manager has content
- A screening question with a disqualifying option
- Six completed participants in two languages (3x FR, 3x EN), with adaptive
  follow-ups, demographics for the segment heatmap, and one in-progress
  participant so the responses tab shows mixed states
- A manual codebook with four codes and a handful of tagged quotes
- A finished AI analysis (v1 = ai_discovery) with verbatim quotes pulled from
  the actual transcripts, plus a refined v2 (researcher_refined) showing the
  iterative analysis flow
- Three theme annotations (confirmed / needs_evidence / disputed) on the v2
- Six project memos (general + theme- and tension-linked)
- One transcript turn flagged as manually edited

The fixture content lives in `_demo_data_fr.py` and `_demo_data_en.py` so the
seeder logic stays readable. The seeder is idempotent at the call site via
`Company.demo_seeded_at` and via a name match in the on-demand router endpoint.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.coding import ManualCode, QuoteTag
from app.models.company import Company
from app.models.interview import (
    AnalysisThemeAnnotation,
    InterviewLink,
    InterviewTurn,
    Participant,
    ProjectAnalysis,
)
from app.models.memo import ProjectMemo
from app.models.project import InterviewGuideQuestion, Project, ScreeningQuestion
from app.services._demo_data_en import NOTABLE_QUOTES_EN, PARTICIPANTS_EN
from app.services._demo_data_fr import NOTABLE_QUOTES_FR, PARTICIPANTS_FR


DEMO_PROJECT_NAME = "[Demo] How modern teams work across borders"
DEMO_PROJECT_NAME_FR = "[Démo] Comment les équipes modernes travaillent à distance"

DEMO_RESEARCH_OBJECTIVE = (
    "Understand how distributed product and engineering teams stay aligned "
    "across time zones, languages, and tool stacks — and surface the moments "
    "where coordination breaks down so we can design a product that fixes the "
    "root cause rather than the symptoms."
)
DEMO_RESEARCH_OBJECTIVE_FR = (
    "Comprendre comment les équipes produit et engineering distribuées restent "
    "alignées à travers les fuseaux horaires, les langues et les outils — et "
    "faire émerger les moments où la coordination casse, pour concevoir un "
    "produit qui règle la cause racine plutôt que les symptômes."
)

DEMO_RESEARCH_CONTEXT = (
    "This is a demo project that QualiPulse seeded automatically so you can "
    "explore the platform with realistic data. It contains six completed "
    "interviews in English and French, a finished AI analysis with two "
    "versions, a researcher codebook, tagged quotes, and project memos. "
    "Feel free to edit anything, archive it, or delete it whenever you're ready "
    "to run your own study — it never counts against your project quota."
)
DEMO_RESEARCH_CONTEXT_FR = (
    "Ceci est un projet de démo que QualiPulse a créé automatiquement pour que "
    "vous puissiez explorer la plateforme avec des données réalistes. Il "
    "contient six entretiens complétés en anglais et en français, une analyse "
    "IA aboutie avec deux versions, un codebook chercheur, des verbatims "
    "taggués et des mémos. Modifiez, archivez ou supprimez quand vous voulez "
    "— ce projet ne compte pas dans votre quota."
)

DEMO_WELCOME_MESSAGE = (
    "Hi, thanks for taking the time to talk with us! This is a short, informal "
    "conversation about how you and your team work together day to day. There "
    "are no right or wrong answers — we just want to understand how things "
    "actually look from your side."
)
DEMO_WELCOME_MESSAGE_FR = (
    "Bonjour, merci de prendre le temps de discuter avec nous ! C'est une "
    "conversation courte et informelle sur la façon dont vous travaillez avec "
    "votre équipe au quotidien. Il n'y a pas de bonnes ou mauvaises réponses "
    "— on veut juste comprendre comment ça se passe vraiment de votre côté."
)

DEMO_GUIDE: list[dict] = [
    {
        "section": "Daily rhythm",
        "questions": [
            {
                "q": "Walk me through a typical work day. When do you focus alone, and when do you collaborate with your team?",
                "learning": "Baseline rhythm, focus vs collaboration ratio, async vs sync defaults.",
            },
            {
                "q": "Which tools do you use to stay aligned with your team, and how has your tool stack changed to get to where it is today?",
                "learning": "Tool stack, sprawl, tool consolidation history.",
            },
        ],
    },
    {
        "section": "Friction & breakdowns",
        "questions": [
            {
                "q": "Tell me about a recent moment where you felt blocked or frustrated working as a team. What happened?",
                "learning": "Coordination breakdowns, where decisions and context get lost.",
            },
            {
                "q": "When you need something from a teammate in a different time zone, what's your playbook?",
                "learning": "Async coping mechanisms, time-zone friction, rituals.",
            },
        ],
    },
    {
        "section": "Aspirations",
        "questions": [
            {
                "q": "If you could wave a magic wand and fix one thing about how your team works together, what would it be and why?",
                "learning": "Top-of-mind pain, wish list, jobs to be done.",
            },
        ],
    },
]

# Parallel FR guide — section order and question count mirror DEMO_GUIDE so
# both the seeder's question_index bookkeeping and the analysis quote lookups
# (which match by turn_index) continue to work.
DEMO_GUIDE_FR: list[dict] = [
    {
        "section": "Rythme quotidien",
        "questions": [
            {
                "q": "Racontez-moi une journée de travail type. Quand êtes-vous en focus seul, et quand collaborez-vous avec votre équipe ?",
                "learning": "Rythme de base, ratio focus vs collaboration, async vs synchrone par défaut.",
            },
            {
                "q": "Quels outils utilisez-vous pour rester aligné avec votre équipe, et comment votre stack a-t-elle évolué pour en arriver là ?",
                "learning": "Stack d'outils, sprawl, historique de consolidation.",
            },
        ],
    },
    {
        "section": "Frictions et ruptures",
        "questions": [
            {
                "q": "Parlez-moi d'un moment récent où vous vous êtes senti bloqué ou frustré en travaillant en équipe. Que s'est-il passé ?",
                "learning": "Ruptures de coordination, où se perdent les décisions et le contexte.",
            },
            {
                "q": "Quand vous avez besoin de quelque chose d'un collègue dans un autre fuseau horaire, quel est votre playbook ?",
                "learning": "Mécanismes d'adaptation async, friction liée aux fuseaux, rituels.",
            },
        ],
    },
    {
        "section": "Aspirations",
        "questions": [
            {
                "q": "Si vous aviez une baguette magique pour régler une seule chose dans la façon dont votre équipe travaille ensemble, ce serait quoi et pourquoi ?",
                "learning": "Douleur top-of-mind, wishlist, jobs-to-be-done.",
            },
        ],
    },
]


# Build a flat ordered list of main questions, mirroring how the seeder
# assigns turn_index → question_index. Used to look up question text.
def _flat_main_questions(guide: list[dict] | None = None) -> list[str]:
    flat: list[str] = []
    for section in (guide or DEMO_GUIDE):
        for item in section["questions"]:
            flat.append(item["q"])
    return flat


DEMO_SCREENING_QUESTION = {
    "question": "How many people are on your team today?",
    "options": ["Just me", "2 to 5", "6 to 15", "16 or more"],
    "disqualifying_options": ["Just me"],
}

DEMO_SCREENING_QUESTION_FR = {
    "question": "Combien de personnes sont dans votre équipe aujourd'hui ?",
    "options": ["Juste moi", "2 à 5", "6 à 15", "16 ou plus"],
    "disqualifying_options": ["Juste moi"],
}


DEMO_CODES = [
    {"name": "Pain point", "color": "#dc2626"},
    {"name": "Workaround", "color": "#f59e0b"},
    {"name": "Aha moment", "color": "#16a34a"},
    {"name": "Cultural difference", "color": "#2563eb"},
]


# (notable_quote_index_in_NOTABLE_QUOTES_*, language, code_name)
# These point at the quotes already validated as substring matches.
DEMO_TAG_PLAN: list[tuple[int, str, str]] = [
    (0, "fr", "Aha moment"),         # "annoncer une règle ça change rien…"
    (1, "fr", "Pain point"),         # "moteur de recherche humain"
    (2, "fr", "Aha moment"),         # "le décalage horaire nous a rendus plus disciplinés"
    (3, "fr", "Pain point"),         # Lucas focus impasse
    (4, "fr", "Cultural difference"),# "ringard de proposer une réu"
    (5, "fr", "Pain point"),         # "Les insights, ils meurent dans le rapport"
    (0, "en", "Pain point"),         # Sarah archaeologist
    (1, "en", "Cultural difference"),# Sarah room/shoulder
    (2, "en", "Aha moment"),         # "documentation is a task, not a byproduct"
    (3, "en", "Pain point"),         # Ben "seven or eight tools"
    (4, "en", "Pain point"),         # Ben senior engineer holds the system
    (5, "en", "Workaround"),         # James "announcing a process doesn't change anything"
    (6, "en", "Aha moment"),         # James "knowing and doing"
]


# ── AI analysis report ──────────────────────────────────────────────────────
#
# Shape matches `frontend/src/api/projects.ts → AnalysisReport`:
#   summary, themes[{title, summary, quotes, frequency}],
#   jobs_to_be_done[{job, insight, frequency}],
#   tensions[{tension, detail}], recommendations[], confidence, participant_count


def _build_quote(text: str, participant_name: str, q_idx: int) -> dict:
    return {
        "text": text,
        "participant_display_name": participant_name,
        "turn_index": q_idx,
    }


def _v1_report() -> dict:
    # Grab a few specific quotes by hand from the staging files. We use the
    # validated NOTABLE_QUOTES_* entries so the strings are guaranteed to also
    # appear inside the actual transcripts.
    fr = NOTABLE_QUOTES_FR
    en = NOTABLE_QUOTES_EN
    p_fr = PARTICIPANTS_FR
    p_en = PARTICIPANTS_EN

    def fr_q(i: int) -> dict:
        q = fr[i]
        return _build_quote(q["text"], p_fr[q["participant_index"]]["display_name"], q["turn_index"])

    def en_q(i: int) -> dict:
        q = en[i]
        return _build_quote(q["text"], p_en[q["participant_index"]]["display_name"], q["turn_index"])

    return {
        "summary": (
            "Across six interviews in French and English, distributed teams "
            "consistently described the same root problem: knowledge, decisions, "
            "and context routinely get lost between tools, people, and time "
            "zones. Participants are not asking for more tools — they are "
            "asking for fewer, better connected, with documentation that "
            "happens automatically as a side effect of doing the work. The "
            "strongest signal is that culture and tooling are inseparable: "
            "the most successful teams in the sample had leaders who modelled "
            "the behaviours they wanted (writing things down, protecting focus "
            "time) rather than announcing them in policies."
        ),
        "themes": [
            {
                "title": "Decisions evaporate the moment a meeting ends",
                "summary": (
                    "Every participant described the same scene: a decision is "
                    "made in a call, nobody writes it down in a single canonical "
                    "place, and three days later somebody asks the question again. "
                    "The cost is not the rework — it's the slow erosion of trust "
                    "in any shared source of truth. People stop believing the "
                    "docs and start treating their own memory as the system of "
                    "record."
                ),
                "quotes": [fr_q(1), en_q(0), en_q(2)],
                "frequency": "6 of 6 participants",
            },
            {
                "title": "Tool sprawl is the symptom, not the disease",
                "summary": (
                    "Teams average six to eight productivity tools and none of "
                    "them talk to each other. Participants do not want a new "
                    "task manager — they want the four they already have to "
                    "share state. The friction is the manual copy-paste between "
                    "Slack, the doc tool, the ticket tracker, and the calendar."
                ),
                "quotes": [en_q(3), fr_q(4)],
                "frequency": "5 of 6 participants",
            },
            {
                "title": "Focus time is socially expensive to defend",
                "summary": (
                    "Protecting deep work is described as a social negotiation, "
                    "not a calendar setting. Participants who succeeded did so "
                    "by quietly modelling the behaviour for weeks, not by "
                    "announcing a rule. The ones who failed all said the same "
                    "thing: announcing the rule changed nothing."
                ),
                "quotes": [fr_q(3), fr_q(0), en_q(5)],
                "frequency": "5 of 6 participants",
            },
            {
                "title": "Time-zone friction can quietly improve team hygiene",
                "summary": (
                    "Counter-intuitively, teams forced to operate across "
                    "non-overlapping time zones described their async "
                    "communication as more rigorous than co-located teams. "
                    "Constraint produced clarity. The participants who had "
                    "always worked across continents were noticeably more "
                    "structured than those whose teams sat in one room."
                ),
                "quotes": [fr_q(2), en_q(1)],
                "frequency": "4 of 6 participants",
            },
            {
                "title": "Leaders model culture or they don't have one",
                "summary": (
                    "The most candid quotes in the sample came from a founder "
                    "who openly admitted that values posted on a wall do nothing "
                    "if leadership doesn't enact them in tiny daily moments. "
                    "Other participants confirmed the same dynamic from the "
                    "receiving side: they ignored stated norms and watched what "
                    "their managers actually did."
                ),
                "quotes": [en_q(6), fr_q(0)],
                "frequency": "4 of 6 participants",
            },
        ],
        "jobs_to_be_done": [
            {
                "job": "When I leave a meeting where a decision was made, I want that decision captured automatically in one canonical place, so that I never have to be the team's archaeologist again.",
                "insight": "Manual note-taking is the bottleneck — participants who try to do it well burn out doing it; participants who don't do it at all create rework for everyone else.",
                "frequency": "6 of 6 participants",
            },
            {
                "job": "When I start my work day, I want to know what actually needs my attention right now, so I can spend my morning on deep work instead of triaging four inboxes.",
                "insight": "All participants triage across at least four surfaces (Slack, email, ticket tool, calendar). The triage itself is the work that prevents the work.",
                "frequency": "6 of 6 participants",
            },
            {
                "job": "When I need an answer from a teammate in a different time zone, I want the round-trip to be one cycle, so I don't lose a day to clarification ping-pong.",
                "insight": "Participants with mature async habits over-specify questions deliberately. Participants without those habits lose 12–24 hours per question on average.",
                "frequency": "4 of 6 participants",
            },
        ],
        "tensions": [
            {
                "tension": "Speed vs documentation",
                "detail": (
                    "Writing things down slows individual work but speeds team "
                    "work. Most participants resolve this in favour of "
                    "individual speed and then suffer later — but only the "
                    "person doing the writing pays the cost up front, while "
                    "the whole team pays the cost of not writing."
                ),
            },
            {
                "tension": "Async rigor vs in-person spontaneity",
                "detail": (
                    "Co-located teams have effortless tap-on-shoulder access "
                    "but build sloppy documentation habits. Distributed teams "
                    "have rigorous documentation habits but lose the lightness "
                    "of spontaneous conversation. Neither group wants to give "
                    "up what they have to gain what the other has."
                ),
            },
            {
                "tension": "Stated values vs enacted behaviour",
                "detail": (
                    "Every participant described a gap between what their team "
                    "claims to value and what their team actually rewards. The "
                    "most self-aware participants admitted they are part of the "
                    "problem they describe."
                ),
            },
        ],
        "recommendations": [
            "Treat decision capture as a first-class product surface, not a polite reminder bot — the moment a meeting ends is the moment the value evaporates.",
            "Don't build another task manager. Build the connective tissue between the four tools every team already has.",
            "Make modelled behaviour visible: surface to leaders the gap between what they say in all-hands and what they do in their actual calendar and Slack patterns.",
            "Design for async-first by default but with a clearly marked synchronous escape hatch — every participant uses both modes daily and resents tools that pretend only one exists.",
            "Pull research findings forward into the moment a decision is being made, not just into a report nobody reads after the fact.",
        ],
        "confidence": "high",
        "participant_count": 6,
    }


def _v2_report() -> dict:
    # Refined version. Same shape, slightly tightened summary, one extra
    # theme nuance reflecting the annotations.
    base = _v1_report()
    base["summary"] = (
        "Refined after researcher review. The strongest signal — that "
        "decisions evaporate the moment a meeting ends — is confirmed by all "
        "six participants and is the recommended product wedge. The secondary "
        "theme around time-zone friction needs more evidence: only four "
        "participants brought it up unprompted, and the framing shifted "
        "between languages (French participants emphasised the discipline "
        "benefit, English participants emphasised the lag cost). The tool "
        "sprawl finding is real but is downstream of the decision-capture "
        "problem rather than independent of it; we should not treat them as "
        "two separate product bets."
    )
    base["confidence"] = "high"
    return base


# Annotations applied to v2 themes (status: confirmed | disputed | needs_evidence)
DEMO_ANNOTATIONS = [
    {
        "theme_title": "Decisions evaporate the moment a meeting ends",
        "status": "confirmed",
        "researcher_note": (
            "Confirmed across all six interviews and across both languages. "
            "This is the wedge — recommend we lead the product narrative with "
            "decision capture rather than tool consolidation."
        ),
    },
    {
        "theme_title": "Time-zone friction can quietly improve team hygiene",
        "status": "needs_evidence",
        "researcher_note": (
            "Only 4/6 participants brought this up unprompted, and the framing "
            "differed by region (FR = discipline benefit, EN = lag cost). We "
            "should run 4–6 more interviews with US-only and APAC-only teams "
            "before treating this as a primary finding."
        ),
    },
    {
        "theme_title": "Tool sprawl is the symptom, not the disease",
        "status": "disputed",
        "researcher_note": (
            "I think this is real but it's downstream of the decision-capture "
            "problem, not independent of it. People reach for new tools because "
            "the old ones don't preserve decisions — fix that root cause and "
            "tool sprawl resolves itself. Recommend we don't position this as "
            "a separate finding in the next pitch."
        ),
    },
]


# Project memos
DEMO_MEMOS = [
    {
        "type": "general",
        "linked_key": None,
        "content": (
            "First pass through the data. Strong consensus around decision "
            "capture and tool fragmentation. Need to look closer at the "
            "language differences — French participants framed time-zone "
            "constraints positively, English participants framed them as "
            "pure cost. Worth probing in the next round."
        ),
    },
    {
        "type": "general",
        "linked_key": None,
        "content": (
            "Next steps: schedule 4–6 follow-ups with US-only teams (we are "
            "underweight on co-located US samples) and 2–3 with APAC. Aim to "
            "either confirm or kill the time-zone hygiene theme before the "
            "next product review."
        ),
    },
    {
        "type": "general",
        "linked_key": None,
        "content": (
            "Quote from James (founder, US) about the gap between knowing and "
            "doing in leadership is the most quotable line in the dataset. "
            "Use it on the landing page if we get permission."
        ),
    },
    {
        "type": "theme_note",
        "linked_key": "Decisions evaporate the moment a meeting ends",
        "content": (
            "Every single participant produced a verbatim version of this "
            "story. The detail that varied was *who* tries to fix it — in "
            "smaller teams it's the PM playing scribe, in larger teams it's "
            "either nobody or the most junior person. Either way, decision "
            "capture is performed as an unpaid second job rather than as a "
            "tool feature. Big opportunity."
        ),
    },
    {
        "type": "theme_note",
        "linked_key": "Leaders model culture or they don't have one",
        "content": (
            "James (Founder, US) was extraordinarily candid here — he openly "
            "admitted he sends Slack messages at 10 PM despite knowing it "
            "destroys his team's focus norms. Worth coming back to whether "
            "the product can hold a mirror up to leaders without being "
            "preachy. Risky but potentially very differentiating."
        ),
    },
    {
        "type": "tension_note",
        "linked_key": "Stated values vs enacted behaviour",
        "content": (
            "This tension showed up in every interview but was named most "
            "directly by the founder participant. Could be a wedge for a "
            "leadership-coaching feature — but be careful, this is the kind "
            "of thing that gets nodded at in interviews and never bought."
        ),
    },
]


# ── Seeder ──────────────────────────────────────────────────────────────────


def seed_demo_project(db: Session, company_id: str) -> Project:
    """Create and persist the full showcase demo project for `company_id`.

    Returns the created Project. The seeder is fully self-contained — it does
    not commit until everything is built, so a partial failure rolls back
    cleanly. The caller is responsible for setting `Company.demo_seeded_at`
    after success if it wants idempotency.

    The project scaffolding (name, objective, welcome, guide, screening) is
    emitted in the company's ``preferred_language`` — defaults to English if
    the company row can't be loaded. The *participant transcripts* stay
    bilingual on purpose (3 FR + 3 EN + 1 in-progress) so the seed showcases
    cross-language capability regardless of the researcher's UI locale.
    """
    now = datetime.now(timezone.utc)

    # Resolve the researcher's language so the project scaffolding is emitted
    # in the right tongue. The participant transcripts remain bilingual by
    # design — see the module docstring.
    company = db.query(Company).filter(Company.id == company_id).first()
    lang = (getattr(company, "preferred_language", None) or "en").strip().lower()[:2]
    if lang not in ("en", "fr"):
        lang = "en"

    if lang == "fr":
        demo_name = DEMO_PROJECT_NAME_FR
        demo_welcome = DEMO_WELCOME_MESSAGE_FR
        demo_objective = DEMO_RESEARCH_OBJECTIVE_FR
        demo_context = DEMO_RESEARCH_CONTEXT_FR
        demo_guide = DEMO_GUIDE_FR
        demo_screening = DEMO_SCREENING_QUESTION_FR
    else:
        demo_name = DEMO_PROJECT_NAME
        demo_welcome = DEMO_WELCOME_MESSAGE
        demo_objective = DEMO_RESEARCH_OBJECTIVE
        demo_context = DEMO_RESEARCH_CONTEXT
        demo_guide = DEMO_GUIDE
        demo_screening = DEMO_SCREENING_QUESTION

    project = Project(
        company_id=company_id,
        name=demo_name,
        language=lang,
        interview_duration_minutes=20,
        welcome_message=demo_welcome,
        research_objective=demo_objective,
        research_context=demo_context,
        is_demo=True,
        created_at=now - timedelta(days=14),
    )
    db.add(project)
    db.flush()

    # Guide questions
    sort_order = 0
    for section_index, section in enumerate(demo_guide):
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

    # Screening question
    db.add(
        ScreeningQuestion(
            project_id=project.id,
            sort_order=0,
            question=demo_screening["question"],
            options=json.dumps(demo_screening["options"]),
            disqualifying_options=json.dumps(demo_screening["disqualifying_options"]),
        )
    )

    # Two interview links — one active EU, one paused NA
    link_eu = InterviewLink(
        project_id=project.id,
        token=secrets.token_urlsafe(32),
        is_active=True,
        created_at=now - timedelta(days=14),
    )
    link_na = InterviewLink(
        project_id=project.id,
        token=secrets.token_urlsafe(32),
        is_active=False,
        created_at=now - timedelta(days=10),
    )
    db.add_all([link_eu, link_na])
    db.flush()

    # Manual codes
    code_by_name: dict[str, ManualCode] = {}
    for idx, c in enumerate(DEMO_CODES):
        code = ManualCode(
            project_id=project.id,
            name=c["name"],
            color=c["color"],
            sort_order=idx,
        )
        db.add(code)
        code_by_name[c["name"]] = code
    db.flush()

    # Helper to add a participant and their turns. Returns (participant, turns_by_index_dict).
    flat_questions = _flat_main_questions(demo_guide)

    def add_participant(
        data: dict,
        link: InterviewLink,
        days_ago: float,
        status: str = "completed",
        edit_first_turn: bool = False,
    ) -> tuple[Participant, list[InterviewTurn]]:
        started = now - timedelta(days=days_ago)
        completed_at = (
            started + timedelta(minutes=18) if status == "completed" else None
        )
        participant = Participant(
            link_id=link.id,
            project_id=project.id,
            display_name=data["display_name"],
            email=data["email"],
            profession=data["profession"],
            age_range=data["age_range"],
            country=data["country"],
            email_verified=True,
            status=status,
            started_at=started,
            completed_at=completed_at,
            quality_score=0.86 if status == "completed" else None,
            quality_label="high" if status == "completed" else None,
        )
        db.add(participant)
        db.flush()

        turns: list[InterviewTurn] = []
        for t_idx, turn in enumerate(data["turns"]):
            # If the turn references a 1-indexed question, we want a 0-indexed
            # question_index for the DB. The fixture uses 1-based question_index.
            q_idx_zero_based = max(0, int(turn.get("question_index", 1)) - 1)
            interview_turn = InterviewTurn(
                participant_id=participant.id,
                turn_index=t_idx,
                question_index=q_idx_zero_based,
                is_follow_up=bool(turn.get("is_follow_up", False)),
                follow_up_index=0,
                question_text=turn["question_text"],
                response_transcript=turn["response_transcript"],
                manually_edited=(edit_first_turn and t_idx == 0),
                edited_at=(now - timedelta(days=days_ago - 0.1)) if (edit_first_turn and t_idx == 0) else None,
                created_at=started + timedelta(minutes=t_idx * 2),
            )
            db.add(interview_turn)
            turns.append(interview_turn)
        db.flush()
        return participant, turns

    # FR participants
    fr_participants: list[tuple[Participant, list[InterviewTurn]]] = []
    for i, p_data in enumerate(PARTICIPANTS_FR):
        # First participant gets the manually-edited flag on its first turn
        result = add_participant(
            p_data,
            link_eu,
            days_ago=12 - i * 1.5,
            status="completed",
            edit_first_turn=(i == 0),
        )
        fr_participants.append(result)

    # EN participants
    en_participants: list[tuple[Participant, list[InterviewTurn]]] = []
    for i, p_data in enumerate(PARTICIPANTS_EN):
        result = add_participant(
            p_data,
            link_eu,
            days_ago=8 - i * 1.5,
            status="completed",
        )
        en_participants.append(result)

    # In-progress participant (no completion timestamp, partial turns)
    marco = Participant(
        link_id=link_eu.id,
        project_id=project.id,
        display_name="Marco P.",
        email="marco.demo@example.com",
        profession="Product Manager",
        age_range="30-39",
        country="Italy",
        email_verified=True,
        status="in_progress",
        started_at=now - timedelta(hours=3),
        completed_at=None,
    )
    db.add(marco)
    db.flush()
    db.add(
        InterviewTurn(
            participant_id=marco.id,
            turn_index=0,
            question_index=0,
            is_follow_up=False,
            follow_up_index=0,
            question_text=flat_questions[0],
            response_transcript=(
                "Sure, so my day usually starts around 9. I check Slack, "
                "I look at what the team in Berlin closed overnight, and "
                "then I try to block the morning for writing specs. After "
                "lunch it's mostly meetings — design reviews, one-on-ones, "
                "stakeholder syncs."
            ),
            created_at=now - timedelta(hours=3),
        )
    )
    db.add(
        InterviewTurn(
            participant_id=marco.id,
            turn_index=1,
            question_index=1,
            is_follow_up=False,
            follow_up_index=0,
            question_text=flat_questions[1],
            response_transcript=(
                "Slack, Linear, Notion, Figma, Google Calendar, and email. "
                "Six tools. None of them really know about each other."
            ),
            created_at=now - timedelta(hours=3) + timedelta(minutes=4),
        )
    )

    # Quote tags — compute offsets via .find() against the actual transcript text
    for notable_idx, lang, code_name in DEMO_TAG_PLAN:
        if lang == "fr":
            quote = NOTABLE_QUOTES_FR[notable_idx]
            participant, turns = fr_participants[quote["participant_index"]]
        else:
            quote = NOTABLE_QUOTES_EN[notable_idx]
            participant, turns = en_participants[quote["participant_index"]]
        turn = turns[quote["turn_index"]]
        text = quote["text"]
        if not turn.response_transcript:
            continue
        start = turn.response_transcript.find(text)
        if start < 0:
            # Should never happen — fixtures are validated — but skip silently
            # rather than blow up the entire onboarding flow.
            continue
        end = start + len(text)
        db.add(
            QuoteTag(
                turn_id=turn.id,
                manual_code_id=code_by_name[code_name].id,
                selected_text=text,
                start_index=start,
                end_index=end,
                created_by="demo",
            )
        )

    # Analysis v1 — ai_discovery
    v1 = ProjectAnalysis(
        project_id=project.id,
        version=1,
        version_label="ai_discovery",
        status="ready",
        participant_count=6,
        report=json.dumps(_v1_report()),
        share_token=secrets.token_urlsafe(32),
        generated_at=now - timedelta(days=4),
        created_at=now - timedelta(days=4),
    )
    db.add(v1)
    db.flush()

    # Analysis v2 — researcher_refined, parented to v1
    v2 = ProjectAnalysis(
        project_id=project.id,
        version=2,
        version_label="researcher_refined",
        status="ready",
        participant_count=6,
        report=json.dumps(_v2_report()),
        parent_version_id=v1.id,
        researcher_context=(
            "Reviewed v1 with the product team. Decision capture is the wedge. "
            "Time-zone hygiene needs more evidence. Tool sprawl should be folded "
            "into the decision-capture narrative rather than positioned as a "
            "separate finding."
        ),
        generated_at=now - timedelta(days=2),
        created_at=now - timedelta(days=2),
    )
    db.add(v2)
    db.flush()

    # Annotations on v2
    for ann in DEMO_ANNOTATIONS:
        db.add(
            AnalysisThemeAnnotation(
                analysis_id=v2.id,
                theme_title=ann["theme_title"],
                status=ann["status"],
                researcher_note=ann["researcher_note"],
            )
        )

    # Memos
    for memo in DEMO_MEMOS:
        db.add(
            ProjectMemo(
                project_id=project.id,
                type=memo["type"],
                linked_key=memo["linked_key"],
                content=memo["content"],
                created_by="demo",
            )
        )

    db.commit()
    db.refresh(project)
    return project
