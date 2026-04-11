"""Shared helpers for building business-context prompt blocks.

Every AI feature that reasons about a specific company (research suggestions,
analysis synthesis, quality scoring) should prepend the same grounding block
so the model knows who it's working for.

The context has two layers:
1. **Company context** — static facts about the business that apply to every
   study this company runs (what they sell, who their customers are, what
   stage they're in, who their competitors are).
2. **Project context** — study-specific facts that override or complement the
   company layer for a single study (the decision this study will unblock,
   who the target interviewees are for this particular project).

Keeping both in one module guarantees the analysis and research_assistant
pipelines never drift out of sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.project import Project


_CUSTOMER_TYPE_LABELS = {
    "b2c": "consumer (B2C)",
    "b2b": "business (B2B)",
    "b2b2c": "B2B2C platform",
    "internal": "internal users / employees",
}

_PRODUCT_STAGE_LABELS = {
    "idea": "idea / pre-launch",
    "mvp": "MVP / early traction",
    "growth": "growth stage",
    "scale": "scaled / mature",
}


def company_context_block(company: "Company") -> str:
    """Build a company-level context block for AI prompts.

    Returns an empty string when we have nothing useful to say, so callers
    can safely `f"{company_context_block(company)}..."` regardless of whether
    the company has filled in any onboarding fields.
    """
    lines: list[str] = []

    if getattr(company, "business_summary", None):
        lines.append(f"Business: {company.business_summary}")
    if getattr(company, "value_proposition", None):
        lines.append(f"Value proposition: {company.value_proposition}")
    if getattr(company, "customer_type", None):
        label = _CUSTOMER_TYPE_LABELS.get(company.customer_type, company.customer_type)
        lines.append(f"Customer type: {label}")
    if getattr(company, "product_stage", None):
        label = _PRODUCT_STAGE_LABELS.get(company.product_stage, company.product_stage)
        lines.append(f"Product stage: {label}")
    if getattr(company, "primary_competitors", None):
        lines.append(f"Primary competitors: {company.primary_competitors}")
    if getattr(company, "industry", None):
        lines.append(f"Industry: {company.industry}")
    if getattr(company, "primary_region", None):
        lines.append(f"Primary market: {company.primary_region}")

    if not lines:
        return ""

    body = "\n".join(f"- {line}" for line in lines)
    return (
        "BUSINESS CONTEXT (use this to ground your reasoning and make "
        "recommendations specific to this company):\n"
        f"{body}\n\n"
    )


def project_study_block(project: "Project") -> str:
    """Build a study-specific grounding block.

    Takes precedence over company context when the two conflict (e.g. this
    particular study might target a narrower customer segment than the
    company's general customer base).
    """
    lines: list[str] = []

    if getattr(project, "decision_to_inform", None):
        lines.append(f"Decision this study will unblock: {project.decision_to_inform}")
    if getattr(project, "target_customer_description", None):
        lines.append(f"Target interviewees: {project.target_customer_description}")
    if getattr(project, "research_context", None):
        lines.append(f"Additional research context: {project.research_context}")

    if not lines:
        return ""

    body = "\n".join(f"- {line}" for line in lines)
    return f"STUDY GROUNDING:\n{body}\n\n"


def full_context_block(
    company: Optional["Company"], project: Optional["Project"] = None
) -> str:
    """Combine company and project context blocks in the correct order.

    Designed to be dropped in front of any Claude prompt that's about a
    specific project. Both args are optional — pass ``None`` to skip a layer.
    """
    out = ""
    if company is not None:
        out += company_context_block(company)
    if project is not None:
        out += project_study_block(project)
    return out
