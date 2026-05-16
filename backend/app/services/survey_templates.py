"""Curated survey templates.

Templates are pre-populated surveys researchers can spin up with one
click — much faster than building from scratch when they want to test
the dashboard end-to-end. The "churn_pricing_onboarding" template
mirrors the study from the design-system QuantiReportDemo page so the
two surfaces feel like one consistent product.

Templates are deliberately small (3-5 questions) — enough to feel like
a real survey but not enough to overwhelm a tester. Each template also
ships a recommended ROLE (screener / standalone / validation) so the
mixed-methods report can place it correctly when Sprint 11 wires up.

To add a template:
  1. Append an entry to `TEMPLATES` below.
  2. Each question's config must validate against the same Pydantic
     schemas used for user-authored questions (`validate_question_config`).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TemplateQuestion:
    """One question definition inside a template."""

    type: str
    prompt: str
    is_required: bool = False
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class SurveyTemplate:
    """A complete survey blueprint. Created via POST /surveys/from-template/{id}."""

    id: str
    name: str
    description: str
    role: str  # "screener" | "standalone" | "validation"
    summary: str  # Short pitch shown on the "use template" tile
    questions: list[TemplateQuestion]


# ── Catalogue ─────────────────────────────────────────────────────────


TEMPLATES: dict[str, SurveyTemplate] = {
    "churn_pricing_onboarding": SurveyTemplate(
        id="churn_pricing_onboarding",
        name="Why new users churn — pricing, trust, and the checkout cliff",
        description=(
            "Five-question screener mirroring the example study from the design system. "
            "Mixes pricing-clarity Likert, NPS, an open-text 'what would you change', and "
            "a multi-choice on the biggest friction. Use to populate a dashboard quickly."
        ),
        role="screener",
        summary="Sample 5-question study used in the example report",
        questions=[
            TemplateQuestion(
                type="likert",
                prompt="The pricing page makes it clear what I'm paying for.",
                is_required=True,
                config={
                    "scale": 5,
                    "anchors": ["Strongly disagree", "Strongly agree"],
                    "reverse_coded": False,
                },
            ),
            TemplateQuestion(
                type="likert",
                prompt="When I reached checkout, I knew exactly what I was being charged.",
                is_required=True,
                config={
                    "scale": 5,
                    "anchors": ["Strongly disagree", "Strongly agree"],
                    "reverse_coded": False,
                },
            ),
            TemplateQuestion(
                type="nps",
                prompt="How likely are you to recommend us to a friend or colleague?",
                is_required=True,
                config={"context": ""},
            ),
            TemplateQuestion(
                type="mc_multi",
                prompt="Which of these caused you the most friction in the first week? (Select all that apply.)",
                is_required=False,
                config={
                    "choices": [
                        {"id": "pricing", "label": "Understanding what plan I needed"},
                        {"id": "checkout", "label": "The checkout step itself"},
                        {"id": "onboarding", "label": "The initial onboarding flow"},
                        {"id": "import", "label": "Getting my data in"},
                        {"id": "team", "label": "Inviting teammates"},
                        {"id": "none", "label": "Nothing — it was smooth"},
                    ],
                    "randomize": True,
                    "has_other": False,
                    "max_selectable": None,
                },
            ),
            TemplateQuestion(
                type="open_text",
                prompt="If you could change one thing to make your first week easier, what would it be?",
                is_required=False,
                config={"max_chars": 500, "ai_cluster": True},
            ),
        ],
    ),
    "post_interview_validation": SurveyTemplate(
        id="post_interview_validation",
        name="Theme validation — does this resonate?",
        description=(
            "Three-question micro-survey to size the themes that came out of a "
            "qualitative interview round. Pair with a study where the qualitative "
            "phase has already produced 1-3 hypotheses to test at scale."
        ),
        role="validation",
        summary="3-question post-interview validator",
        questions=[
            TemplateQuestion(
                type="likert",
                prompt="Hypothesis 1 from our interviews — replace this prompt with your theme.",
                is_required=True,
                config={
                    "scale": 5,
                    "anchors": ["Doesn't resonate at all", "Resonates strongly"],
                    "reverse_coded": False,
                },
            ),
            TemplateQuestion(
                type="likert",
                prompt="Hypothesis 2 from our interviews — replace this prompt with your theme.",
                is_required=False,
                config={
                    "scale": 5,
                    "anchors": ["Doesn't resonate at all", "Resonates strongly"],
                    "reverse_coded": False,
                },
            ),
            TemplateQuestion(
                type="open_text",
                prompt="Is there a theme we missed that you'd flag as important?",
                is_required=False,
                config={"max_chars": 400, "ai_cluster": False},
            ),
        ],
    ),
}


def list_templates() -> list[dict[str, Any]]:
    """Returns the public listing — id, name, summary, role, question count."""

    return [
        {
            "id": t.id,
            "name": t.name,
            "summary": t.summary,
            "role": t.role,
            "question_count": len(t.questions),
        }
        for t in TEMPLATES.values()
    ]


def get_template(template_id: str) -> SurveyTemplate | None:
    return TEMPLATES.get(template_id)
