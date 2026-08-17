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
        # Hero copy matches the SPA blog page
        assert "Le blog QualiPulse" in page

    def test_empty_listing_renders(self, client):
        resp = client.get("/blog/pages")
        assert resp.status_code == 200
        assert "Aucun article pour le moment" in resp.text


class TestChrome:
    """Both rendered pages carry the site's real header and footer, since
    visitors arriving from search or a shared link read THIS page, not the SPA."""

    @pytest.mark.parametrize("path", ["/blog/pages", "/blog/pages/entretien-test"])
    def test_header_and_footer(self, client, published_post, path):
        page = client.get(path).text
        # Header: brand home link + nav + signup CTA
        assert 'class="qp-brand" href="/"' in page
        assert 'href="/#pricing"' in page
        assert 'href="/login"' in page
        assert 'href="/signup"' in page
        # Footer: site + legal links and copyright
        assert 'href="/terms"' in page
        assert 'href="/privacy"' in page
        assert "Tous droits réservés" in page

    def test_post_links_back_to_listing(self, client, published_post):
        page = client.get("/blog/pages/entretien-test").text
        assert 'class="qp-back" href="/blog"' in page

    def test_cover_image_renders_on_card_and_article(self, client, db_session):
        """Images uploaded from the admin editor show up in both rendered views."""
        db_session.add(
            BlogPost(
                slug="avec-couverture",
                title="Avec couverture",
                content="<p>corps</p>",
                cover_image_url="https://cdn.example.com/cover.png",
                status="published",
                published_at=datetime(2026, 8, 2),
            )
        )
        db_session.commit()
        listing = client.get("/blog/pages").text
        assert 'class="qp-card-cover" src="https://cdn.example.com/cover.png"' in listing
        article = client.get("/blog/pages/avec-couverture").text
        assert "https://cdn.example.com/cover.png" in article

    def test_french_date_is_localized(self, client, published_post):
        """Byline shows "1 août 2026", not the ISO date (which stays in JSON-LD)."""
        page = client.get("/blog/pages/entretien-test").text
        assert "1 août 2026" in page
        assert '"datePublished": "2026-08-01"' in page
