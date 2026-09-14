"""Project template catalogue: shape invariants + the marketing entry points.

The homepage use-case cards and /use-cases/* pages deep-link into these ids
(``?template=<id>`` on /signup), so the ids they rely on are pinned here.
"""

import pytest

from app.services.templates import TEMPLATES, get_template_by_id, get_templates

# Templates the marketing site links to. Renaming one silently breaks the
# "Start a churn study" CTA, so the ids are asserted explicitly.
MARKETING_TEMPLATE_IDS = ("customer-churn", "brand-perception", "nps-deep-dive")


class TestCatalogueShape:
    def test_ids_are_unique(self):
        ids = [t["id"] for t in TEMPLATES]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("template_id", MARKETING_TEMPLATE_IDS)
    def test_marketing_entry_points_exist(self, template_id):
        assert get_template_by_id(template_id) is not None

    @pytest.mark.parametrize("lang", ["en", "fr"])
    def test_question_indexes_are_consistent(self, lang):
        for t in get_templates(lang):
            assert len(t["questions"]) > 0, t["id"]
            for pos, q in enumerate(t["questions"]):
                assert q["question_index"] == pos, (t["id"], lang, pos)
                assert q["main_question"].strip(), (t["id"], lang, pos)
            sections = [q["section_index"] for q in t["questions"]]
            assert sections == sorted(sections), (t["id"], lang)

    @pytest.mark.parametrize("lang", ["en", "fr"])
    def test_disqualifying_options_are_real_options(self, lang):
        for t in get_templates(lang):
            for sq in t["screening_questions"]:
                assert set(sq["disqualifying_options"]) <= set(sq["options"]), (t["id"], lang)

    def test_no_em_dashes_in_participant_facing_copy(self):
        """Participants hear these questions; the em dash is banned from copy."""
        for lang in ("en", "fr"):
            for t in get_templates(lang):
                for q in t["questions"]:
                    assert "—" not in q["main_question"], (t["id"], lang, q["main_question"])
                for sq in t["screening_questions"]:
                    assert "—" not in sq["question"], (t["id"], lang)


class TestNpsDeepDive:
    def test_english_shape(self):
        t = get_template_by_id("nps-deep-dive")
        assert t["category"] == "research"
        assert t["duration_minutes"] <= 15
        assert len(t["questions"]) == 6
        assert t["screening_questions"][0]["disqualifying_options"] == ["I did not answer the survey"]

    def test_french_override_merges_positionally(self):
        en = get_template_by_id("nps-deep-dive", "en")
        fr = get_template_by_id("nps-deep-dive", "fr")
        assert fr["name"] == "Comprendre une note NPS ou CSAT"
        assert len(fr["questions"]) == len(en["questions"])
        for en_q, fr_q in zip(en["questions"], fr["questions"]):
            assert fr_q["section_index"] == en_q["section_index"]
            assert fr_q["question_index"] == en_q["question_index"]
            assert fr_q["main_question"] != en_q["main_question"]
        # Screening options and disqualifiers are translated together so the
        # disqualifier still matches an option.
        sq = fr["screening_questions"][0]
        assert set(sq["disqualifying_options"]) <= set(sq["options"])

    def test_english_source_is_untouched_by_fr_render(self):
        get_template_by_id("nps-deep-dive", "fr")
        assert get_template_by_id("nps-deep-dive", "en")["name"] == "NPS & CSAT Deep Dive"


class TestTemplatesApi:
    def test_public_listing_includes_marketing_ids(self, client):
        resp = client.get("/templates?lang=fr")
        assert resp.status_code == 200
        ids = {t["id"] for t in resp.json()["templates"]}
        assert set(MARKETING_TEMPLATE_IDS) <= ids

    def test_detail_localises(self, client):
        resp = client.get("/templates/nps-deep-dive?lang=fr")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Comprendre une note NPS ou CSAT"
