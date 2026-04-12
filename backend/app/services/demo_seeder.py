"""Seed a showcase demo project for new users.

This seeds a single research project that demonstrates QualiPulse features
so a new user can explore the platform with realistic data before running
their own study:

- One interview link so the link manager has content
- A screening question with a disqualifying option
- Four completed participants in two languages (2× FR, 2× EN), with adaptive
  follow-ups and demographics for the segment heatmap
- A manual codebook with three codes and tagged quotes
- A finished AI analysis (v1 = ai_discovery) with verbatim quotes, plus a
  refined v2 (researcher_refined) showing the iterative analysis flow
- Two theme annotations (confirmed / needs_evidence) on v2
- Three project memos (general + theme-linked)

The fixture content lives in `_demo_data_fr.py` and `_demo_data_en.py` so the
seeder logic stays readable. The seeder is idempotent at the call site via
`Company.demo_seeded_at` and via a name match in the on-demand router endpoint.

Theme: Brand trust & repurchase intent for "Maison Aura", an imaginary premium
home wellness brand (candles, skincare). Universal consumer topic — works for
retail, DTC, services. Not tech/SaaS-specific.
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


DEMO_PROJECT_NAME = "[Demo] Brand trust — Maison Aura"
DEMO_PROJECT_NAME_FR = "[Démo] Confiance de marque — Maison Aura"

DEMO_RESEARCH_OBJECTIVE = (
    "Understand what builds or breaks trust for first-time buyers of a premium "
    "home-wellness brand, and identify the moments in the customer journey that "
    "determine whether someone becomes a repeat customer or walks away."
)
DEMO_RESEARCH_OBJECTIVE_FR = (
    "Comprendre ce qui construit ou détruit la confiance des primo-acheteurs "
    "d'une marque premium de bien-être pour la maison, et identifier les moments "
    "du parcours client qui déterminent si quelqu'un revient ou abandonne."
)

DEMO_RESEARCH_CONTEXT = (
    "This is a demo project that QualiPulse seeded automatically so you can "
    "explore the platform with realistic data. It contains four completed "
    "interviews in English and French, a finished AI analysis with two "
    "versions, a researcher codebook, tagged quotes, and project memos. "
    "Feel free to edit anything, archive it, or delete it whenever you're ready "
    "to run your own study — it never counts against your project quota."
)
DEMO_RESEARCH_CONTEXT_FR = (
    "Ceci est un projet de démo que QualiPulse a créé automatiquement pour que "
    "vous puissiez explorer la plateforme avec des données réalistes. Il "
    "contient quatre entretiens complétés en anglais et en français, une analyse "
    "IA avec deux versions, un codebook chercheur, des verbatims "
    "taggués et des mémos. Modifiez, archivez ou supprimez quand vous voulez "
    "— ce projet ne compte pas dans votre quota."
)

DEMO_WELCOME_MESSAGE = (
    "Hi, thanks for taking the time to chat with us! This is a short, informal "
    "conversation about your experience with Maison Aura — what you liked, "
    "what surprised you, and what could be better. There are no right or wrong "
    "answers."
)
DEMO_WELCOME_MESSAGE_FR = (
    "Bonjour, merci de prendre le temps de discuter avec nous ! C'est une "
    "conversation courte et informelle sur votre expérience avec Maison Aura "
    "— ce qui vous a plu, ce qui vous a surpris, et ce qui pourrait être "
    "amélioré. Il n'y a pas de bonnes ou mauvaises réponses."
)

DEMO_GUIDE: list[dict] = [
    {
        "section": "Discovery",
        "questions": [
            {
                "q": "How did you first hear about Maison Aura, and what made you want to try it?",
                "learning": "Discovery channel, first impression drivers, role of word-of-mouth vs ads.",
            },
        ],
    },
    {
        "section": "Experience",
        "questions": [
            {
                "q": "Walk me through your experience from the first purchase to receiving the product. What stood out?",
                "learning": "Purchase friction, unboxing experience, packaging perception, delivery expectations.",
            },
        ],
    },
    {
        "section": "Trust & return",
        "questions": [
            {
                "q": "What would make you — or has made you — come back to buy from Maison Aura? And what might stop you?",
                "learning": "Repeat purchase drivers, trust signals, barriers to loyalty, competitor switching triggers.",
            },
        ],
    },
]

DEMO_GUIDE_FR: list[dict] = [
    {
        "section": "Découverte",
        "questions": [
            {
                "q": "Comment avez-vous découvert Maison Aura, et qu'est-ce qui vous a donné envie d'essayer ?",
                "learning": "Canal de découverte, premiers déclencheurs, rôle du bouche-à-oreille vs pub.",
            },
        ],
    },
    {
        "section": "Expérience",
        "questions": [
            {
                "q": "Racontez-moi votre expérience du premier achat jusqu'à la réception du produit. Qu'est-ce qui vous a marqué ?",
                "learning": "Frictions à l'achat, expérience d'unboxing, perception du packaging, attentes de livraison.",
            },
        ],
    },
    {
        "section": "Confiance et retour",
        "questions": [
            {
                "q": "Qu'est-ce qui vous ferait — ou vous a fait — revenir acheter chez Maison Aura ? Et qu'est-ce qui pourrait vous en empêcher ?",
                "learning": "Moteurs de réachat, signaux de confiance, freins à la fidélisation, déclencheurs de switch.",
            },
        ],
    },
]


def _flat_main_questions(guide: list[dict] | None = None) -> list[str]:
    flat: list[str] = []
    for section in (guide or DEMO_GUIDE):
        for item in section["questions"]:
            flat.append(item["q"])
    return flat


DEMO_SCREENING_QUESTION = {
    "question": "Have you purchased a premium home-care or wellness product in the last 12 months?",
    "options": ["Yes, more than once", "Yes, once", "No"],
    "disqualifying_options": ["No"],
}

DEMO_SCREENING_QUESTION_FR = {
    "question": "Avez-vous acheté un produit premium de soin ou bien-être pour la maison au cours des 12 derniers mois ?",
    "options": ["Oui, plusieurs fois", "Oui, une fois", "Non"],
    "disqualifying_options": ["Non"],
}


DEMO_CODES = [
    {"name": "Trust signal", "color": "#16a34a"},
    {"name": "Friction", "color": "#dc2626"},
    {"name": "Price concern", "color": "#f59e0b"},
]


# (notable_quote_index_in_NOTABLE_QUOTES_*, language, code_name)
DEMO_TAG_PLAN: list[tuple[int, str, str]] = [
    (0, "fr", "Trust signal"),       # Claire — packaging = confiance
    (1, "fr", "Friction"),           # Claire — hidden return policy
    (2, "fr", "Price concern"),      # Thomas — paying for packaging not product
    (3, "fr", "Friction"),           # Thomas — trial barrier
    (0, "en", "Trust signal"),       # Emma — unboxing like a gift
    (1, "en", "Friction"),           # Emma — shipping too slow
    (2, "en", "Friction"),           # James — website navigation confusion
    (3, "en", "Trust signal"),       # James — quality you notice
]


# ── AI analysis report ──────────────────────────────────────────────────────

def _build_quote(text: str, participant_name: str, q_idx: int) -> dict:
    return {
        "text": text,
        "participant_display_name": participant_name,
        "turn_index": q_idx,
    }


def _v1_report() -> dict:
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
            "Across four interviews in French and English, a clear pattern "
            "emerges: Maison Aura's product quality and packaging create genuine "
            "trust and delight at first contact — but the purchase experience "
            "(website navigation, return policy visibility, shipping speed) "
            "erodes that trust before customers can become loyal. The brand wins "
            "on sensory experience and loses on convenience. Satisfied buyers "
            "return for the product; dissatisfied ones leave not because the "
            "product disappointed, but because the process around it did."
        ),
        "themes": [
            {
                "title": "Packaging is the product — first impressions build disproportionate trust",
                "summary": (
                    "All four participants described packaging as a primary trust "
                    "signal. The unboxing experience, handwritten-style notes, and "
                    "premium materials made buyers feel the product would match the "
                    "presentation. When it did, trust compounded. When it didn't "
                    "(one participant), the gap between packaging promise and "
                    "product reality felt like a betrayal."
                ),
                "quotes": [fr_q(0), en_q(0)],
                "frequency": "4 of 4 participants",
            },
            {
                "title": "Website friction costs more than lost sales — it costs trust",
                "summary": (
                    "Three of four participants struggled with website navigation. "
                    "Poetic category names confused task-oriented buyers. The "
                    "return policy was hard to find. One participant abandoned a "
                    "reorder entirely. The friction is not just a conversion "
                    "problem — it signals to buyers that the brand prioritises "
                    "aesthetics over their experience, undermining the premium "
                    "positioning."
                ),
                "quotes": [fr_q(1), en_q(2), en_q(1)],
                "frequency": "3 of 4 participants",
            },
            {
                "title": "Price is only a problem when the value gap is invisible",
                "summary": (
                    "The most price-sensitive participant (Thomas, 25-29, freelance) "
                    "didn't object to paying more per se — he objected to not "
                    "understanding why. The brand's website over-indexed on "
                    "storytelling and under-indexed on ingredient transparency and "
                    "product differentiation. Buyers who could feel the quality "
                    "difference (Claire, Emma) didn't question the price. The one "
                    "who couldn't (Thomas) felt deceived."
                ),
                "quotes": [fr_q(2), en_q(3)],
                "frequency": "2 of 4 participants",
            },
        ],
        "jobs_to_be_done": [
            {
                "job": "When I discover a new premium brand, I want the first purchase to feel like a gift to myself, so I can justify the price as an experience rather than just a product.",
                "insight": "Packaging and unboxing are doing the job of price justification. Participants who loved the unboxing never questioned the price.",
                "frequency": "4 of 4 participants",
            },
            {
                "job": "When I want to reorder or explore new products, I want to find what I need in under a minute, so I don't lose the impulse to buy.",
                "insight": "The website's aesthetic-first navigation works for browsing but fails for returning customers who know what they want.",
                "frequency": "3 of 4 participants",
            },
        ],
        "tensions": [
            {
                "tension": "Brand aesthetics vs user convenience",
                "detail": (
                    "The website's poetic category names and editorial design "
                    "reinforce the premium brand identity but actively frustrate "
                    "buyers trying to complete a simple task. The very thing that "
                    "attracts new visitors repels returning customers."
                ),
            },
            {
                "tension": "Storytelling vs transparency",
                "detail": (
                    "The brand invests heavily in founder stories and lifestyle "
                    "imagery but under-communicates concrete product benefits "
                    "(ingredients, sourcing, what justifies the price). Buyers who "
                    "are already sold don't mind; buyers on the fence feel the "
                    "brand is hiding behind style."
                ),
            },
        ],
        "recommendations": [
            "Add a search bar and allow filtering by scent, product type, and use case — don't make returning customers decode poetic category names.",
            "Make the return policy visible at checkout, not buried in terms. For a premium brand, generous returns are a trust accelerator, not a cost.",
            "Include a 'why this price' section on each product page with ingredient sourcing and production details — let quality speak for itself.",
            "Send a personalised post-purchase check-in (not a discount code) asking how the product worked — this was explicitly requested by the most skeptical participant.",
            "Consider a discovery kit at a lower price point to reduce the trial barrier for price-sensitive segments.",
        ],
        "confidence": "high",
        "participant_count": 4,
    }


def _v2_report() -> dict:
    base = _v1_report()
    base["summary"] = (
        "Refined after researcher review. The packaging-as-trust-signal finding "
        "is confirmed across all four participants and is the strongest asset "
        "the brand has — protect it. The website friction finding is actionable "
        "and should be the immediate product priority: three of four "
        "participants hit navigation problems, and one churned directly because "
        "of it. The price-transparency theme needs more evidence — only one "
        "participant framed it as a deal-breaker, though the others may simply "
        "not have been price-sensitive enough to surface it unprompted."
    )
    base["confidence"] = "high"
    return base


DEMO_ANNOTATIONS = [
    {
        "theme_title": "Packaging is the product — first impressions build disproportionate trust",
        "status": "confirmed",
        "researcher_note": (
            "Confirmed across all four interviews. The unboxing experience is "
            "the strongest trust driver — protect it in any cost-cutting "
            "exercise. Worth testing whether a sample in the first order "
            "(like Claire mentioned) amplifies this effect."
        ),
    },
    {
        "theme_title": "Price is only a problem when the value gap is invisible",
        "status": "needs_evidence",
        "researcher_note": (
            "Only Thomas framed this as a deal-breaker. The others were "
            "price-tolerant. Need 3-4 more interviews with price-sensitive "
            "segments (students, younger buyers) before making this a primary "
            "recommendation. Don't over-rotate on one participant's feedback."
        ),
    },
]


DEMO_MEMOS = [
    {
        "type": "general",
        "linked_key": None,
        "content": (
            "First pass through the data. Strong consensus on packaging as a "
            "trust driver, and equally strong frustration with the website. "
            "The price story is split — need more interviews with younger / "
            "more budget-conscious segments to know if Thomas is an outlier "
            "or the leading edge."
        ),
    },
    {
        "type": "theme_note",
        "linked_key": "Website friction costs more than lost sales — it costs trust",
        "content": (
            "James (US) literally churned because of website navigation, not "
            "because of product quality. His wife noticed the quality difference "
            "when he switched brands. This is the most actionable finding — "
            "a search bar and product-type filter could recover lost revenue "
            "with minimal investment."
        ),
    },
    {
        "type": "tension_note",
        "linked_key": "Storytelling vs transparency",
        "content": (
            "Thomas's quote about 'style without substance' is the most "
            "quotable line in the dataset. Worth using in the next brand "
            "strategy review — it's not an insult, it's a precisely stated "
            "gap that the team can close by adding ingredient transparency "
            "without sacrificing the aesthetic."
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
    bilingual on purpose (2 FR + 2 EN) so the seed showcases cross-language
    capability regardless of the researcher's UI locale.
    """
    now = datetime.now(timezone.utc)

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
        interview_duration_minutes=15,
        welcome_message=demo_welcome,
        research_objective=demo_objective,
        research_context=demo_context,
        is_demo=True,
        created_at=now - timedelta(days=10),
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

    # Interview link
    link = InterviewLink(
        project_id=project.id,
        token=secrets.token_urlsafe(32),
        is_active=True,
        created_at=now - timedelta(days=10),
    )
    db.add(link)
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

    # Helper to add a participant and their turns.
    flat_questions = _flat_main_questions(demo_guide)

    def add_participant(
        data: dict,
        days_ago: float,
        edit_first_turn: bool = False,
    ) -> tuple[Participant, list[InterviewTurn]]:
        started = now - timedelta(days=days_ago)
        completed_at = started + timedelta(minutes=14)
        participant = Participant(
            link_id=link.id,
            project_id=project.id,
            display_name=data["display_name"],
            email=data["email"],
            profession=data["profession"],
            age_range=data["age_range"],
            country=data["country"],
            email_verified=True,
            status="completed",
            started_at=started,
            completed_at=completed_at,
            quality_score=0.85,
            quality_label="high",
        )
        db.add(participant)
        db.flush()

        turns: list[InterviewTurn] = []
        for t_idx, turn in enumerate(data["turns"]):
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
                created_at=started + timedelta(minutes=t_idx * 3),
            )
            db.add(interview_turn)
            turns.append(interview_turn)
        db.flush()
        return participant, turns

    # FR participants
    fr_participants: list[tuple[Participant, list[InterviewTurn]]] = []
    for i, p_data in enumerate(PARTICIPANTS_FR):
        result = add_participant(p_data, days_ago=8 - i * 2, edit_first_turn=(i == 0))
        fr_participants.append(result)

    # EN participants
    en_participants: list[tuple[Participant, list[InterviewTurn]]] = []
    for i, p_data in enumerate(PARTICIPANTS_EN):
        result = add_participant(p_data, days_ago=6 - i * 2)
        en_participants.append(result)

    # Quote tags
    for notable_idx, lang_code, code_name in DEMO_TAG_PLAN:
        if lang_code == "fr":
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
        participant_count=4,
        report=json.dumps(_v1_report()),
        share_token=secrets.token_urlsafe(32),
        generated_at=now - timedelta(days=3),
        created_at=now - timedelta(days=3),
    )
    db.add(v1)
    db.flush()

    # Analysis v2 — researcher_refined
    v2 = ProjectAnalysis(
        project_id=project.id,
        version=2,
        version_label="researcher_refined",
        status="ready",
        participant_count=4,
        report=json.dumps(_v2_report()),
        parent_version_id=v1.id,
        researcher_context=(
            "Reviewed v1 with the brand team. Packaging trust is the asset — "
            "protect it. Website friction is the immediate fix. Price "
            "transparency needs more evidence before we invest."
        ),
        generated_at=now - timedelta(days=1),
        created_at=now - timedelta(days=1),
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
