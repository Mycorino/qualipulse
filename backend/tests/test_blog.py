"""
Blog platform tests: admin CRUD lifecycle, HTML sanitization, and image upload.
"""
import io

import pytest

from app.config import settings

ADMIN_KEY = "test-admin-secret-key"

# Minimal valid 1x1 PNG (signature + IHDR/IDAT/IEND)
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c62fcff9fa1a20000ffff0300060a02fe27499fbc"
    "0000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def admin_secret_configured():
    prev = settings.ADMIN_SECRET_KEY
    settings.ADMIN_SECRET_KEY = ADMIN_KEY
    try:
        yield
    finally:
        settings.ADMIN_SECRET_KEY = prev


@pytest.fixture(autouse=True)
def tmp_upload_dir(tmp_path):
    prev = settings.UPLOAD_DIR
    settings.UPLOAD_DIR = str(tmp_path)
    try:
        yield tmp_path
    finally:
        settings.UPLOAD_DIR = prev


def _headers():
    return {"Authorization": f"Bearer {ADMIN_KEY}", "X-Admin-Identity": "tester"}


# ── CRUD lifecycle ────────────────────────────────────────────────────────────


class TestBlogLifecycle:
    def test_create_publish_read_delete(self, client):
        created = client.post("/admin/blog", headers=_headers(), json={
            "title": "Hello World",
            "content": "<p>Body</p>",
            "tags": ["research"],
        })
        assert created.status_code == 201, created.text
        post = created.json()
        assert post["slug"] == "hello-world"
        assert post["status"] == "draft"
        assert post["published_at"] is None

        # Draft is invisible publicly
        assert client.get("/blog/posts/hello-world").status_code == 404
        assert client.get("/blog/posts").json()["total"] == 0

        # Publish
        updated = client.put(f"/admin/blog/{post['id']}", headers=_headers(), json={
            "status": "published",
        })
        assert updated.status_code == 200
        assert updated.json()["published_at"] is not None

        # Public read + tag filter
        assert client.get("/blog/posts/hello-world").status_code == 200
        assert client.get("/blog/posts", params={"tag": "research"}).json()["total"] == 1

        # Delete
        assert client.delete(f"/admin/blog/{post['id']}", headers=_headers()).status_code == 204
        assert client.get("/blog/posts/hello-world").status_code == 404

    def test_slug_collision_rejected(self, client):
        body = {"title": "Same Title", "content": ""}
        assert client.post("/admin/blog", headers=_headers(), json=body).status_code == 201
        assert client.post("/admin/blog", headers=_headers(), json=body).status_code == 409

    def test_content_sanitized(self, client):
        created = client.post("/admin/blog", headers=_headers(), json={
            "title": "XSS Check",
            "content": '<p>ok</p><script>alert(1)</script><img src="x" onerror="alert(2)">',
        })
        content = created.json()["content"]
        assert "<script" not in content
        assert "onerror" not in content
        assert "<p>ok</p>" in content

    def test_admin_endpoints_require_key(self, client):
        assert client.get("/admin/blog").status_code == 401
        assert client.post("/admin/blog", json={"title": "x"}).status_code == 401


# ── Image upload ──────────────────────────────────────────────────────────────


class TestBlogImageUpload:
    def _upload(self, client, data: bytes, content_type: str, headers=None):
        return client.post(
            "/admin/blog/upload-image",
            headers=_headers() if headers is None else headers,
            files={"file": ("pic.png", io.BytesIO(data), content_type)},
        )

    def test_upload_png_and_serve(self, client, tmp_upload_dir):
        resp = self._upload(client, PNG_BYTES, "image/png")
        assert resp.status_code == 201, resp.text
        url = resp.json()["url"]
        assert url.startswith("/api/files/blog-images/")
        assert url.endswith(".png")

        # Served by the backend /files route (the /api prefix is proxy-only)
        served = client.get(url.removeprefix("/api"))
        assert served.status_code == 200
        assert served.content == PNG_BYTES

    def test_rejects_unsupported_content_type(self, client):
        assert self._upload(client, b"%PDF-1.4", "application/pdf").status_code == 415

    def test_rejects_mismatched_magic_bytes(self, client):
        assert self._upload(client, b"not a png at all", "image/png").status_code == 415

    def test_rejects_oversized_image(self, client):
        big = PNG_BYTES + b"\x00" * (8 * 1024 * 1024)
        assert self._upload(client, big, "image/png").status_code == 413

    def test_requires_admin_key(self, client):
        assert self._upload(client, PNG_BYTES, "image/png", headers={}).status_code == 401

    def test_files_route_blocks_traversal_and_non_images(self, client):
        assert client.get("/files/../secrets.txt").status_code in (403, 404)
        assert client.get("/files/notes.txt").status_code == 403
