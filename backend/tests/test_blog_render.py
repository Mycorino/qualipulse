"""Server-rendered blog pages (/blog/pages, /blog/pages/{slug})."""

from datetime import datetime

import pytest

from app.models.blog import BlogPost


@pytest.fixture
def published_post(db_session):
    post = BlogPost(
        slug="entretien-test",
        title='Entretien <qualitatif> & "guillemets"',
        subtitle="Le sous-titre",
        content="<h2>Section</h2><p>Contenu de l'article avec un <a href=\"/signup\">lien</a>.</p>",
        excerpt="Un extrait descriptif.",
        meta_title="Meta titre entretien",
        meta_description="Une meta description dédiée.",
        author_name="QualiPulse",
        status="published",
        published_at=datetime(2026, 8, 1, 10, 0, 0),
    )
    db_session.add(post)
    db_session.add(
        BlogPost(
            slug="brouillon-cache",
            title="Brouillon secret",
            content="<p>pas public</p>",
            status="draft",
        )
    )
    db_session.commit()
    return post


class TestBlogPostPage:
    def test_renders_full_html_with_meta(self, client, published_post):
        resp = client.get("/blog/pages/entretien-test")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        page = resp.text
        # Content and structure
        assert "<h2>Section</h2>" in page
        assert "Contenu de l'article" in page
        assert "Le sous-titre" in page
        # Escaped title in <h1>, meta_title in <title>/og:title
        assert "Entretien &lt;qualitatif&gt;" in page
        assert "<title>Meta titre entretien</title>" in page
        assert 'property="og:title" content="Meta titre entretien"' in page
        assert 'name="description" content="Une meta description dédiée."' in page
        assert 'property="og:type" content="article"' in page
        # Canonical + JSON-LD grounded on APP_BASE_URL
        assert 'rel="canonical"' in page
        assert "/blog/entretien-test" in page
        assert '"@type": "Article"' in page
        assert '"datePublished": "2026-08-01"' in page
        # Default OG image fallback (no cover/og image set)
        assert "og-image.png" in page

    def test_draft_and_unknown_are_404(self, client, published_post):
        assert client.get("/blog/pages/brouillon-cache").status_code == 404
        assert client.get("/blog/pages/nope").status_code == 404

    def test_no_executable_scripts(self, client, published_post):
        """Only the JSON-LD data block; the strict HTML CSP allows nothing else."""
        page = client.get("/blog/pages/entretien-test").text
        assert page.count("<script") == 1
        assert '<script type="application/ld+json">' in page


class TestBlogListingPage:
    def test_lists_published_only_with_links(self, client, published_post):
        resp = client.get("/blog/pages")
        assert resp.status_code == 200
        page = resp.text
        assert 'href="/blog/entretien-test"' in page
        assert "Un extrait descriptif." in page
        assert "Brouillon secret" not in page

    def test_empty_listing_renders(self, client):
        resp = client.get("/blog/pages")
        assert resp.status_code == 200
        assert "articles arrivent" in resp.text
