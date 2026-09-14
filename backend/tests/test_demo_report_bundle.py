"""The homepage bundles the demo study's report; it must match the seeder fixture."""

import json
from pathlib import Path

import pytest

from scripts.export_demo_report import OUT_DIR, payload


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_bundled_report_matches_fixture(lang):
    bundled = json.loads((OUT_DIR / f"demoReport.{lang}.json").read_text())
    assert bundled == payload(lang), (
        f"frontend/src/marketing/demoReport.{lang}.json is out of date; run "
        "python -c 'from scripts.export_demo_report import main; main()' in backend/"
    )


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_bundled_report_is_renderable(lang):
    data = json.loads((OUT_DIR / f"demoReport.{lang}.json").read_text())
    assert data["project_name"]
    assert data["participant_count"] >= 3, "the panel must not show a small-sample warning"
    report = data["report"]
    assert len(report["themes"]) >= 3
    assert all(theme.get("quotes") for theme in report["themes"])
    assert report["recommendations"]
