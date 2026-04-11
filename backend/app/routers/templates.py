"""
Research project templates API.

Exposes pre-built templates that the CreateProjectWizard can load to skip
the blank-canvas problem. Templates are fully public (no auth required) so
users can preview them before signing up — this is a marketing asset too.

Localisation: authenticated callers get copy in their
``company.preferred_language`` automatically; unauthenticated callers and the
marketing-site preview can pass ``?lang=fr`` explicitly.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_company_optional
from app.models.company import Company
from app.services.templates import get_template_by_id, get_templates

router = APIRouter(prefix="/templates", tags=["templates"])


def _resolve_lang(explicit: str | None, company: Company | None) -> str | None:
    """Pick the language for a template render.

    Explicit ``?lang=`` wins so the marketing preview can request FR even
    when unauthenticated. Otherwise fall back to the authenticated company's
    ``preferred_language`` (defaults to FR in the model) and finally English
    if neither is available.
    """
    if explicit:
        return explicit
    if company is not None:
        return getattr(company, "preferred_language", None)
    return None


@router.get("")
def list_templates(
    lang: str | None = Query(None),
    company: Company | None = Depends(get_current_company_optional),
):
    """List all available project templates (localised when possible)."""
    resolved = _resolve_lang(lang, company)
    templates = get_templates(lang=resolved)
    return {
        "templates": [
            {
                "id": t["id"],
                "name": t["name"],
                "category": t["category"],
                "icon": t["icon"],
                "description": t["description"],
                "best_for": t["best_for"],
                "duration_minutes": t["duration_minutes"],
                "question_count": len(t["questions"]),
                "has_screening": len(t["screening_questions"]) > 0,
            }
            for t in templates
        ]
    }


@router.get("/{template_id}")
def get_template(
    template_id: str,
    lang: str | None = Query(None),
    company: Company | None = Depends(get_current_company_optional),
):
    """Return the full template payload (objective, questions, screening)."""
    resolved = _resolve_lang(lang, company)
    template = get_template_by_id(template_id, lang=resolved)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template
