"""One-off backfill: refresh seeded demo analyses with the richer report shape.

The demo project is seeded once per company and then frozen (idempotent via
``Company.demo_seeded_at`` + an existing-demo name check). Accounts that
onboarded before the report-exhibits upgrade therefore still have their demo
``ProjectAnalysis`` rows stored in the *old* shape — string recommendations, no
personas, no journey. This script re-derives those reports from the current
builders in ``demo_seeder`` and overwrites the stored JSON so legacy accounts
showcase the same exhibits (object recommendations, personas, experience
journey) as freshly-seeded ones.

Only the flagship study's v1/v2 and the exit-study's v1 ProjectAnalysis reports
are rewritten. The quantified-themes ``StudyAnalysis`` (recs already object
shaped) and the decision memo (string recs by schema) are left untouched, as
are theme annotations (a separate table). No transcripts or quotes change —
persona/journey anchors reuse the report's own verbatim theme quotes.

Idempotent: a report already in the current shape is skipped, so re-running
only does the remaining work. Requires NO Anthropic key (reports are
hand-authored fixtures, not model calls).

Usage (from backend/, with the target env so it hits the intended DB):

    python -m scripts.backfill_demo_reports --dry-run          # report only
    python -m scripts.backfill_demo_reports                     # apply
    python -m scripts.backfill_demo_reports --company <id>      # one company
    python -m scripts.backfill_demo_reports --limit 50          # cap analyses
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.interview import ProjectAnalysis  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.demo_seeder import (  # noqa: E402
    DEMO_PROJECT_NAME,
    DEMO_PROJECT_NAME_FR,
    DEMO2_PROJECT_NAME,
    DEMO2_PROJECT_NAME_FR,
    _v1_report,
    _v2_report,
    _study2_report,
)

_FLAGSHIP = {DEMO_PROJECT_NAME, DEMO_PROJECT_NAME_FR}
_STUDY2 = {DEMO2_PROJECT_NAME, DEMO2_PROJECT_NAME_FR}
_FR_NAMES = {DEMO_PROJECT_NAME_FR, DEMO2_PROJECT_NAME_FR}
_ALL_DEMO_NAMES = _FLAGSHIP | _STUDY2


def _builder_for(project: Project, analysis: ProjectAnalysis):
    """Return the report builder for this analysis, or None to skip.

    Matches on (which demo project) × (version_label). Anything unrecognised is
    left alone so we never rewrite a report we didn't author here.
    """
    name = project.name
    if name in _FLAGSHIP:
        if analysis.version_label == "researcher_refined":
            return _v2_report
        if analysis.version_label == "ai_discovery":
            return _v1_report
    elif name in _STUDY2:
        if analysis.version_label == "ai_discovery":
            return _study2_report
    return None


def run(dry_run: bool, limit: int | None, company_id: str | None) -> int:
    db = SessionLocal()
    updated = 0
    try:
        q = (
            db.query(ProjectAnalysis)
            .join(Project, ProjectAnalysis.project_id == Project.id)
            .filter(Project.is_demo.is_(True), Project.name.in_(_ALL_DEMO_NAMES))
        )
        if company_id:
            q = q.filter(Project.company_id == company_id)
        rows = q.all()

        print(f"{len(rows)} demo analysis row(s) found{' (dry-run)' if dry_run else ''}.")
        skipped = 0
        for analysis in rows:
            if limit is not None and updated >= limit:
                print(f"Reached --limit {limit}; stopping.")
                break
            project = db.query(Project).filter(Project.id == analysis.project_id).first()
            if project is None:
                continue
            builder = _builder_for(project, analysis)
            if builder is None:
                skipped += 1
                continue
            lang = "fr" if project.name in _FR_NAMES else "en"
            fresh = builder(lang)
            try:
                current = json.loads(analysis.report) if analysis.report else None
            except (TypeError, ValueError):
                current = None
            if current == fresh:
                skipped += 1
                continue  # already in the current shape
            label = f"{project.company_id[:8]}… · {project.name[:40]} · v{analysis.version} ({analysis.version_label})"
            print(("WOULD refresh " if dry_run else "refreshed ") + label)
            if not dry_run:
                analysis.report = json.dumps(fresh)
            updated += 1

        if not dry_run and updated:
            db.commit()
        print(
            f"\nDone: {updated} refreshed, {skipped} already-current/unmapped"
            f"{' (dry-run — nothing written)' if dry_run else ''}."
        )
        return updated
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Refresh seeded demo analyses with the richer report shape.")
    ap.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of analyses refreshed")
    ap.add_argument("--company", type=str, default=None, help="restrict to one company id")
    args = ap.parse_args()
    run(dry_run=args.dry_run, limit=args.limit, company_id=args.company)


if __name__ == "__main__":
    main()
