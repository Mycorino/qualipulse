"""GET /sitemap.xml — generated from the published blog posts + static routes."""

from datetime import datetime
from xml.etree import ElementTree

import pytest

from app.models.blog import BlogPost

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@pytest.fixture
def posts(db_session):
    db_session.add(
        BlogPost(
            slug="article-publie",
            title="Publié",
            content="<p>x</p>",
            status="published",
            published_at=datetime(2026, 8, 1),
            updated_at=datetime(2026, 8, 15),
        )
    )
    db_session.add(
        BlogPost(slug="article-brouillon", title="Brouillon", content="<p>x</p>", status="draft")
    )
    db_session.commit()


def _locs(xml: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    return [el.text for el in root.findall(".//sm:loc", _NS)]


class TestSitemap:
    def test_is_valid_xml_with_static_routes(self, client):
        resp = client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/xml")
        locs = _locs(resp.text)
        for path in ("/", "/signup", "/blog", "/terms", "/privacy", "/retention-policy"):
            assert any(loc.endswith(path) for loc in locs), path

    def test_lists_published_posts_only(self, client, posts):
        locs = _locs(client.get("/sitemap.xml").text)
        assert any(loc.endswith("/blog/article-publie") for loc in locs)
        assert not any("article-brouillon" in loc for loc in locs)

    def test_post_carries_lastmod(self, client, posts):
        root = ElementTree.fromstring(client.get("/sitemap.xml").text)
        entry = next(
            u for u in root.findall("sm:url", _NS)
            if u.find("sm:loc", _NS).text.endswith("/blog/article-publie")
        )
        assert entry.find("sm:lastmod", _NS).text == "2026-08-15"

    def test_no_auth_walled_routes_leak(self, client, posts):
        """Everything robots.txt disallows must stay out of the sitemap."""
        locs = _locs(client.get("/sitemap.xml").text)
        for blocked in ("/dashboard", "/welcome", "/admin", "/interview/", "/reports/", "/affiliate"):
            assert not any(blocked in loc for loc in locs), blocked

    def test_empty_blog_still_renders(self, client):
        locs = _locs(client.get("/sitemap.xml").text)
        assert len(locs) == 11
