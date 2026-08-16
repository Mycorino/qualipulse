"""Seed the FR SEO article cluster into the blog CMS as DRAFTS.

Six articles (five methodology pieces + one recruitment guide) around
"entretien qualitatif", authored in scripts/_blog_seo_articles_fr.py. They
are inserted with status="draft" so nothing goes public until reviewed and
published from the admin blog tab.

Idempotent: an existing post with the same slug is left untouched by default
(so later human edits in the CMS are never clobbered). Pass --update to
overwrite existing drafts with the current fixture content; published posts
are never overwritten, even with --update.

Usage (from backend/, with the target DATABASE_URL exported):

    python -m scripts.seed_blog_articles --dry-run   # report only
    python -m scripts.seed_blog_articles             # insert missing drafts
    python -m scripts.seed_blog_articles --update    # also refresh existing drafts
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.blog import BlogPost  # noqa: E402
from scripts._blog_seo_articles_fr import ARTICLES  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--update", action="store_true", help="refresh existing drafts from fixtures")
    args = parser.parse_args()

    db = SessionLocal()
    created, updated, skipped = [], [], []
    try:
        for article in ARTICLES:
            existing = db.query(BlogPost).filter(BlogPost.slug == article["slug"]).first()
            if existing is not None:
                if not args.update or existing.status == "published":
                    skipped.append(article["slug"])
                    continue
                for field in ("title", "subtitle", "content", "excerpt", "meta_title", "meta_description", "author_name"):
                    setattr(existing, field, article[field])
                existing.tags = json.dumps(article["tags"], ensure_ascii=False)
                updated.append(article["slug"])
                continue

            db.add(
                BlogPost(
                    slug=article["slug"],
                    title=article["title"],
                    subtitle=article["subtitle"],
                    content=article["content"],
                    excerpt=article["excerpt"],
                    meta_title=article["meta_title"],
                    meta_description=article["meta_description"],
                    author_name=article["author_name"],
                    tags=json.dumps(article["tags"], ensure_ascii=False),
                    status="draft",
                )
            )
            created.append(article["slug"])

        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    mode = "DRY RUN, nothing written" if args.dry_run else "written"
    print(f"seed_blog_articles ({mode})")
    print(f"  created as draft: {created or 'none'}")
    print(f"  updated drafts:   {updated or 'none'}")
    print(f"  skipped existing: {skipped or 'none'}")


if __name__ == "__main__":
    main()
