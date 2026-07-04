import json
import re
import uuid
from datetime import datetime
from typing import Optional

import bleach
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.limiter import limiter
from app.models.blog import BlogPost
from app.routers.admin import require_admin
from app.services.storage import upload_image

router = APIRouter(tags=["blog"])


# ── HTML sanitization (defense in depth for TipTap content) ─────────────────
# The admin blog editor is trusted, but admin creds can leak and the endpoint
# accepts raw HTML in the request body (not via the TipTap client). Strip
# anything dangerous before persisting so /blog/:slug can render via
# dangerouslySetInnerHTML without giving attackers XSS.
ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "s", "code", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "a", "img",
    "hr", "span", "div",
    "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "span": ["class"],
    "div": ["class"],
    "code": ["class"],
    "pre": ["class"],
}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(html: str | None) -> str:
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    subtitle: str | None = None
    slug: str | None = None  # auto-generated from title if omitted
    content: str = ""
    excerpt: str | None = None
    cover_image_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    og_image_url: str | None = None
    author_name: str = "QualiPulse Team"
    tags: list[str] | None = None
    status: str = "draft"


class BlogPostUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    slug: str | None = None
    content: str | None = None
    excerpt: str | None = None
    cover_image_url: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    og_image_url: str | None = None
    author_name: str | None = None
    tags: list[str] | None = None
    status: str | None = None


class BlogPostResponse(BaseModel):
    id: str
    slug: str
    title: str
    subtitle: str | None
    content: str
    excerpt: str | None
    cover_image_url: str | None
    meta_title: str | None
    meta_description: str | None
    og_image_url: str | None
    author_name: str
    tags: list[str]
    status: str
    published_at: str | None
    created_at: str
    updated_at: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def serialize_post(post: BlogPost) -> dict:
    tags_list = []
    if post.tags:
        try:
            tags_list = json.loads(post.tags)
        except (json.JSONDecodeError, TypeError):
            tags_list = []
    return {
        "id": post.id,
        "slug": post.slug,
        "title": post.title,
        "subtitle": post.subtitle,
        "content": post.content,
        "excerpt": post.excerpt,
        "cover_image_url": post.cover_image_url,
        "meta_title": post.meta_title,
        "meta_description": post.meta_description,
        "og_image_url": post.og_image_url,
        "author_name": post.author_name,
        "tags": tags_list,
        "status": post.status,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
    }


# ── Public endpoints ─────────────────────────────────────────────────────────

@router.get("/blog/posts")
def list_published_posts(
    tag: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = db.query(BlogPost).filter(BlogPost.status == "published")
    if tag:
        if not re.match(r'^[a-zA-Z0-9\s\-àâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ]{1,50}$', tag):
            raise HTTPException(400, "Invalid tag format")
        query = query.filter(BlogPost.tags.contains(f'"{tag}"'))
    total = query.count()
    posts = (
        query.order_by(BlogPost.published_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "posts": [serialize_post(p) for p in posts],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/blog/posts/{slug}")
def get_published_post(slug: str, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(
        BlogPost.slug == slug,
        BlogPost.status == "published",
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return serialize_post(post)


# ── Admin endpoints ──────────────────────────────────────────────────────────

# Image upload for the blog editor (TipTap content + cover images).
# Stored in R2 in production (absolute public URL) or under UPLOAD_DIR in
# local dev (served via /files, reachable as /api/files/* through the proxy).
MAX_IMAGE_SIZE_MB = 8
_IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _matches_image_magic(data: bytes, ext: str) -> bool:
    """Cheap signature check so a mislabelled file can't be stored as an image."""
    if ext == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".jpg":
        return data.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


@router.post("/admin/blog/upload-image", dependencies=[Depends(require_admin)], status_code=201)
async def admin_upload_blog_image(file: UploadFile = File(...)):
    ext = _IMAGE_EXTENSIONS.get(file.content_type or "")
    if not ext:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Allowed: PNG, JPEG, WebP, GIF.",
        )
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Image too large. Max size is {MAX_IMAGE_SIZE_MB}MB.")
    if not _matches_image_magic(data, ext):
        raise HTTPException(status_code=415, detail="File content does not match its image type.")
    key = f"blog-images/{uuid.uuid4()}{ext}"
    return {"url": upload_image(data, key)}

@router.get("/admin/blog", dependencies=[Depends(require_admin)])
def admin_list_posts(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(BlogPost)
    if status_filter:
        query = query.filter(BlogPost.status == status_filter)
    total = query.count()
    posts = (
        query.order_by(BlogPost.updated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return {
        "posts": [serialize_post(p) for p in posts],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/admin/blog/{post_id}", dependencies=[Depends(require_admin)])
def admin_get_post(post_id: str, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return serialize_post(post)


@router.post("/admin/blog", dependencies=[Depends(require_admin)], status_code=201)
def admin_create_post(body: BlogPostCreate, db: Session = Depends(get_db)):
    slug = body.slug or slugify(body.title)

    # Ensure slug uniqueness
    existing = db.query(BlogPost).filter(BlogPost.slug == slug).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Slug '{slug}' already exists")

    now = datetime.utcnow()
    post = BlogPost(
        slug=slug,
        title=body.title,
        subtitle=body.subtitle,
        content=sanitize_html(body.content),
        excerpt=body.excerpt,
        cover_image_url=body.cover_image_url,
        meta_title=body.meta_title or body.title,
        meta_description=body.meta_description or body.excerpt,
        og_image_url=body.og_image_url or body.cover_image_url,
        author_name=body.author_name,
        tags=json.dumps(body.tags) if body.tags else None,
        status=body.status,
        published_at=now if body.status == "published" else None,
        created_at=now,
        updated_at=now,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return serialize_post(post)


@router.put("/admin/blog/{post_id}", dependencies=[Depends(require_admin)])
def admin_update_post(post_id: str, body: BlogPostUpdate, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    update_data = body.model_dump(exclude_unset=True)

    # Handle slug uniqueness
    if "slug" in update_data and update_data["slug"]:
        existing = db.query(BlogPost).filter(
            BlogPost.slug == update_data["slug"],
            BlogPost.id != post_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Slug '{update_data['slug']}' already exists")

    # Handle tags serialization
    if "tags" in update_data:
        update_data["tags"] = json.dumps(update_data["tags"]) if update_data["tags"] else None

    # Sanitize HTML content (defense in depth — see sanitize_html above)
    if "content" in update_data:
        update_data["content"] = sanitize_html(update_data["content"])

    # Handle publish transition
    if "status" in update_data:
        if update_data["status"] == "published" and post.status != "published":
            update_data["published_at"] = datetime.utcnow()
        elif update_data["status"] == "draft":
            update_data["published_at"] = None

    for key, value in update_data.items():
        setattr(post, key, value)

    post.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    return serialize_post(post)


@router.delete("/admin/blog/{post_id}", dependencies=[Depends(require_admin)], status_code=204)
def admin_delete_post(post_id: str, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(BlogPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    db.delete(post)
    db.commit()
