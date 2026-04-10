"""
Research project templates API.

Exposes pre-built templates that the CreateProjectWizard can load to skip
the blank-canvas problem. Templates are fully public (no auth required) so
users can preview them before signing up — this is a marketing asset too.
"""

from fastapi import APIRouter, HTTPException

from app.services.templates import get_template_by_id, get_templates

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def list_templates():
    """List all available project templates."""
    templates = get_templates()
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
def get_template(template_id: str):
    """Return the full template payload (objective, questions, screening)."""
    template = get_template_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template
