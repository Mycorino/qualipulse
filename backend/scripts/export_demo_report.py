"""Export the demo study's refined analysis report for the marketing site.

The homepage's "open the real report" panel renders the same report every
new account's demo study ships with, bundled as JSON so it needs no house
account or share token. Run after touching ``_v2_report`` / the demo fixture:

    cd backend && python -c "from scripts.export_demo_report import main; main()"
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services import demo_seeder

OUT_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "marketing"
PROJECT_NAMES = {"en": demo_seeder.DEMO_PROJECT_NAME, "fr": demo_seeder.DEMO_PROJECT_NAME_FR}


def payload(lang: str) -> dict:
    report = demo_seeder._v2_report(lang)
    return {
        "project_name": PROJECT_NAMES[lang],
        "participant_count": report.get("participant_count", 0),
        "generated_at": None,
        "report": report,
    }


def main() -> None:
    for lang in ("en", "fr"):
        path = OUT_DIR / f"demoReport.{lang}.json"
        path.write_text(json.dumps(payload(lang), ensure_ascii=False, indent=2) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
