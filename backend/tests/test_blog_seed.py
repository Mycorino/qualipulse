"""Editorial + integrity guardrails for the FR SEO article cluster fixtures."""

import re

from scripts._blog_seo_articles_fr import ARTICLES, CLUSTER_SLUGS

# Routes the articles may link to besides the cluster itself.
_ALLOWED_ROUTES = {"/signup", "/", "/dpa", "/participant-notice", "/retention-policy"}

# Tags the blog sanitizer allows (routers/blog.py ALLOWED_TAGS); tables are not.
_ALLOWED_HTML_TAGS = {
    "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a", "img",
}


def _all_text(article):
    return " ".join(
        article[f] or ""
        for f in ("title", "subtitle", "excerpt", "meta_title", "meta_description", "content")
    )


class TestArticleFixtures:
    def test_cluster_shape(self):
        assert [a["slug"] for a in ARTICLES] == CLUSTER_SLUGS
        assert len(set(CLUSTER_SLUGS)) == len(CLUSTER_SLUGS)

    def test_no_banned_dashes(self):
        """House copy rule: no em/en dashes or double hyphens in prose."""
        for article in ARTICLES:
            text = _all_text(article)
            for banned in ("—", "–", "--"):
                assert banned not in text, f"{article['slug']} contains banned dash {banned!r}"

    def test_no_research_tool_artifacts(self):
        for article in ARTICLES:
            assert "citeturn" not in _all_text(article)
            assert "mermaid" not in article["content"]

    def test_meta_description_length(self):
        for article in ARTICLES:
            assert len(article["meta_description"]) <= 160, article["slug"]

    def test_only_sanitizer_allowed_html_tags(self):
        for article in ARTICLES:
            tags = set(re.findall(r"</?([a-zA-Z0-9]+)", article["content"]))
            unknown = tags - _ALLOWED_HTML_TAGS
            assert not unknown, f"{article['slug']} uses disallowed tags: {unknown}"

    def test_internal_links_resolve(self):
        """Every href points at a cluster article or a known product route."""
        for article in ARTICLES:
            for href in re.findall(r'href="([^"]+)"', article["content"]):
                if href.startswith("/blog/"):
                    assert href.removeprefix("/blog/") in CLUSTER_SLUGS, f"{article['slug']} -> {href}"
                else:
                    assert href in _ALLOWED_ROUTES, f"{article['slug']} -> unexpected href {href}"

    def test_cluster_is_interlinked(self):
        """Each article links at least one other cluster article and a signup CTA."""
        for article in ARTICLES:
            internal = [
                s for s in CLUSTER_SLUGS
                if s != article["slug"] and f'/blog/{s}' in article["content"]
            ]
            assert internal, f"{article['slug']} links no other cluster article"
            assert '/signup' in article["content"], f"{article['slug']} has no signup CTA"

    def test_french_typography_applied(self):
        """Prose punctuation (: ! ? ;) is preceded by a no-break space, never a plain space."""
        for article in ARTICLES:
            for punct in (":", "!", "?", ";"):
                assert f" {punct}" not in article["content"], (
                    f"{article['slug']} has a breaking space before '{punct}'"
                )


class TestSeedScript:
    def _run(self, db_session, argv):
        import sys
        from unittest.mock import patch

        import scripts.seed_blog_articles as seeder

        with patch.object(seeder, "SessionLocal", lambda: db_session), patch.object(
            sys, "argv", ["seed_blog_articles"] + argv
        ):
            # The script closes the session; give it a no-op close so the
            # fixture-managed session survives for assertions.
            close = db_session.close
            db_session.close = lambda: None
            try:
                seeder.main()
            finally:
                db_session.close = close

    def test_seeds_drafts_idempotently(self, db_session):
        from app.models.blog import BlogPost

        self._run(db_session, [])
        posts = db_session.query(BlogPost).all()
        assert len(posts) == len(ARTICLES)
        assert all(p.status == "draft" for p in posts)

        # Re-run: no duplicates, human edits preserved without --update.
        post = db_session.query(BlogPost).filter_by(slug=CLUSTER_SLUGS[0]).one()
        post.title = "Edited by a human"
        db_session.commit()
        self._run(db_session, [])
        assert db_session.query(BlogPost).count() == len(ARTICLES)
        assert db_session.query(BlogPost).filter_by(slug=CLUSTER_SLUGS[0]).one().title == "Edited by a human"

        # --update refreshes drafts from fixtures...
        self._run(db_session, ["--update"])
        assert db_session.query(BlogPost).filter_by(slug=CLUSTER_SLUGS[0]).one().title == ARTICLES[0]["title"]

        # ...but never touches published posts.
        post = db_session.query(BlogPost).filter_by(slug=CLUSTER_SLUGS[1]).one()
        post.status = "published"
        post.title = "Published and edited"
        db_session.commit()
        self._run(db_session, ["--update"])
        assert db_session.query(BlogPost).filter_by(slug=CLUSTER_SLUGS[1]).one().title == "Published and edited"

    def test_dry_run_writes_nothing(self, db_session):
        from app.models.blog import BlogPost

        self._run(db_session, ["--dry-run"])
        assert db_session.query(BlogPost).count() == 0
