import { useState, useEffect, useCallback } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import axios from "axios";

interface BlogPost {
  id: string;
  slug: string;
  title: string;
  subtitle: string | null;
  content: string;
  excerpt: string | null;
  cover_image_url: string | null;
  meta_title: string | null;
  meta_description: string | null;
  og_image_url: string | null;
  author_name: string;
  tags: string[];
  status: string;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

function adminClient(key: string) {
  return axios.create({
    baseURL: "/api",
    headers: { Authorization: `Bearer ${key}` },
  });
}

// ── Toolbar ────────────────────────────────────────────────────────────────

function Toolbar({ editor }: { editor: ReturnType<typeof useEditor> }) {
  if (!editor) return null;

  function addImage() {
    const url = window.prompt("Image URL:");
    if (url) editor!.chain().focus().setImage({ src: url }).run();
  }

  function addLink() {
    const url = window.prompt("Link URL:");
    if (url) {
      editor!.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    } else {
      editor!.chain().focus().unsetLink().run();
    }
  }

  return (
    <div className="tiptap-toolbar">
      <button type="button" onClick={() => editor!.chain().focus().toggleBold().run()} className={editor!.isActive("bold") ? "is-active" : ""}>B</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleItalic().run()} className={editor!.isActive("italic") ? "is-active" : ""}>I</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleStrike().run()} className={editor!.isActive("strike") ? "is-active" : ""}>S</button>
      <span style={{ width: 1, background: "var(--border)", margin: "0 4px" }} />
      <button type="button" onClick={() => editor!.chain().focus().toggleHeading({ level: 2 }).run()} className={editor!.isActive("heading", { level: 2 }) ? "is-active" : ""}>H2</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleHeading({ level: 3 }).run()} className={editor!.isActive("heading", { level: 3 }) ? "is-active" : ""}>H3</button>
      <span style={{ width: 1, background: "var(--border)", margin: "0 4px" }} />
      <button type="button" onClick={() => editor!.chain().focus().toggleBulletList().run()} className={editor!.isActive("bulletList") ? "is-active" : ""}>List</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleOrderedList().run()} className={editor!.isActive("orderedList") ? "is-active" : ""}>1.2.3</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleBlockquote().run()} className={editor!.isActive("blockquote") ? "is-active" : ""}>Quote</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleCodeBlock().run()} className={editor!.isActive("codeBlock") ? "is-active" : ""}>Code</button>
      <span style={{ width: 1, background: "var(--border)", margin: "0 4px" }} />
      <button type="button" onClick={addLink}>Link</button>
      <button type="button" onClick={addImage}>Image</button>
      <button type="button" onClick={() => editor!.chain().focus().setHorizontalRule().run()}>HR</button>
    </div>
  );
}

// ── Slugify ────────────────────────────────────────────────────────────────

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

// ── Post Editor ────────────────────────────────────────────────────────────

function PostEditor({
  post,
  adminKey,
  onSaved,
  onCancel,
}: {
  post: BlogPost | null; // null = new
  adminKey: string;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(post?.title ?? "");
  const [subtitle, setSubtitle] = useState(post?.subtitle ?? "");
  const [slug, setSlug] = useState(post?.slug ?? "");
  const [slugManual, setSlugManual] = useState(!!post);
  const [excerpt, setExcerpt] = useState(post?.excerpt ?? "");
  const [coverUrl, setCoverUrl] = useState(post?.cover_image_url ?? "");
  const [metaTitle, setMetaTitle] = useState(post?.meta_title ?? "");
  const [metaDesc, setMetaDesc] = useState(post?.meta_description ?? "");
  const [ogImage, setOgImage] = useState(post?.og_image_url ?? "");
  const [authorName, setAuthorName] = useState(post?.author_name ?? "QualiPulse Team");
  const [tagsStr, setTagsStr] = useState((post?.tags ?? []).join(", "));
  const [postStatus, setPostStatus] = useState(post?.status ?? "draft");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [showPreview, setShowPreview] = useState(false);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Link.configure({ openOnClick: false }),
      Image,
      Placeholder.configure({ placeholder: "Write your article..." }),
    ],
    content: post?.content ?? "",
  });

  function handleTitleChange(val: string) {
    setTitle(val);
    if (!slugManual) setSlug(slugify(val));
  }

  async function handleSave() {
    setError("");
    setSaving(true);
    const client = adminClient(adminKey);
    const tags = tagsStr
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    const body = {
      title,
      subtitle: subtitle || null,
      slug,
      content: editor?.getHTML() ?? "",
      excerpt: excerpt || null,
      cover_image_url: coverUrl || null,
      meta_title: metaTitle || null,
      meta_description: metaDesc || null,
      og_image_url: ogImage || null,
      author_name: authorName,
      tags,
      status: postStatus,
    };
    try {
      if (post) {
        await client.put(`/admin/blog/${post.id}`, body);
      } else {
        await client.post("/admin/blog", body);
      }
      onSaved();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 12px",
    borderRadius: "var(--radius)",
    border: "1px solid var(--border)",
    fontSize: 14,
    background: "var(--bg-surface)",
    color: "var(--text-primary)",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-secondary)",
    marginBottom: 4,
    display: "block",
  };

  return (
    <div>
      {/* Top bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>{post ? "Edit Post" : "New Post"}</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => setShowPreview(!showPreview)}
            style={{
              padding: "8px 16px",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              background: showPreview ? "var(--brand-50)" : "var(--bg-surface)",
              color: showPreview ? "var(--primary)" : "var(--text-secondary)",
              fontSize: 13,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >{showPreview ? "Hide Preview" : "Preview"}</button>
          <button onClick={onCancel} style={{ padding: "8px 16px", border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--bg-surface)", color: "var(--text-secondary)", fontSize: 13, cursor: "pointer" }}>Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving || !title.trim()}
            style={{
              padding: "8px 20px",
              border: "none",
              borderRadius: "var(--radius)",
              background: "var(--primary)",
              color: "#fff",
              fontSize: 13,
              fontWeight: 600,
              cursor: saving ? "default" : "pointer",
              opacity: saving || !title.trim() ? 0.6 : 1,
            }}
          >{saving ? "Saving..." : "Save"}</button>
        </div>
      </div>

      {error && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: showPreview ? "1fr 1fr" : "1fr", gap: 24 }}>
        {/* Editor column */}
        <div>
          {/* Title */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Title</label>
            <input value={title} onChange={(e) => handleTitleChange(e.target.value)} style={{ ...inputStyle, fontSize: 18, fontWeight: 600 }} placeholder="Post title" />
          </div>

          {/* Subtitle */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Subtitle</label>
            <input value={subtitle} onChange={(e) => setSubtitle(e.target.value)} style={inputStyle} placeholder="Optional subtitle" />
          </div>

          {/* Slug + Status row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={labelStyle}>Slug</label>
              <input
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugManual(true); }}
                style={inputStyle}
                placeholder="post-url-slug"
              />
            </div>
            <div>
              <label style={labelStyle}>Status</label>
              <select
                value={postStatus}
                onChange={(e) => setPostStatus(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                <option value="draft">Draft</option>
                <option value="published">Published</option>
              </select>
            </div>
          </div>

          {/* Content editor */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Content</label>
            <div className="tiptap-editor">
              <Toolbar editor={editor} />
              <EditorContent editor={editor} />
            </div>
          </div>

          {/* Excerpt */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Excerpt</label>
            <textarea value={excerpt} onChange={(e) => setExcerpt(e.target.value)} style={{ ...inputStyle, minHeight: 60, resize: "vertical" }} placeholder="Short description for cards and SEO" />
          </div>

          {/* Cover image + Author row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={labelStyle}>Cover Image URL</label>
              <input value={coverUrl} onChange={(e) => setCoverUrl(e.target.value)} style={inputStyle} placeholder="https://..." />
            </div>
            <div>
              <label style={labelStyle}>Author</label>
              <input value={authorName} onChange={(e) => setAuthorName(e.target.value)} style={inputStyle} />
            </div>
          </div>

          {/* Tags */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Tags (comma-separated)</label>
            <input value={tagsStr} onChange={(e) => setTagsStr(e.target.value)} style={inputStyle} placeholder="research, product, ux" />
          </div>

          {/* SEO section */}
          <details style={{ marginBottom: 12 }}>
            <summary style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", cursor: "pointer", marginBottom: 8 }}>SEO / Open Graph</summary>
            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <label style={labelStyle}>Meta Title</label>
                <input value={metaTitle} onChange={(e) => setMetaTitle(e.target.value)} style={inputStyle} placeholder="Defaults to post title" />
              </div>
              <div>
                <label style={labelStyle}>Meta Description</label>
                <textarea value={metaDesc} onChange={(e) => setMetaDesc(e.target.value)} style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} placeholder="Defaults to excerpt" />
              </div>
              <div>
                <label style={labelStyle}>OG Image URL</label>
                <input value={ogImage} onChange={(e) => setOgImage(e.target.value)} style={inputStyle} placeholder="Defaults to cover image" />
              </div>
            </div>
          </details>
        </div>

        {/* Preview column */}
        {showPreview && (
          <div style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-lg)",
            padding: "32px 28px",
            maxHeight: "calc(100vh - 200px)",
            overflowY: "auto",
          }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 16, fontWeight: 600 }}>
              Preview
            </div>
            {coverUrl && (
              <img src={coverUrl} alt="" style={{ width: "100%", maxHeight: 200, objectFit: "cover", borderRadius: "var(--radius)", marginBottom: 16 }} />
            )}
            {tagsStr && (
              <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
                {tagsStr.split(",").map((t) => t.trim()).filter(Boolean).map((tag) => (
                  <span key={tag} style={{ fontSize: 11, fontWeight: 600, color: "var(--primary)", background: "var(--brand-50)", padding: "2px 8px", borderRadius: "var(--radius-xs)", textTransform: "uppercase", letterSpacing: "0.5px" }}>{tag}</span>
                ))}
              </div>
            )}
            <h1 style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.2, marginBottom: 8 }}>{title || "Untitled"}</h1>
            {subtitle && <p style={{ fontSize: 18, color: "var(--text-secondary)", marginBottom: 12 }}>{subtitle}</p>}
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid var(--border-subtle)" }}>
              {authorName} &middot; {new Date().toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })}
            </div>
            <div
              className="blog-content"
              dangerouslySetInnerHTML={{ __html: editor?.getHTML() ?? "" }}
              style={{ fontSize: 15, lineHeight: 1.75 }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Admin Blog Component ──────────────────────────────────────────────

export default function AdminBlog({ adminKey }: { adminKey: string }) {
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [editing, setEditing] = useState<BlogPost | null | "new">(null); // null = list, "new" = create, BlogPost = edit

  const client = useCallback(() => adminClient(adminKey), [adminKey]);

  function loadPosts() {
    setLoading(true);
    const params: Record<string, any> = { page };
    if (statusFilter) params.status = statusFilter;
    client()
      .get("/admin/blog", { params })
      .then((res) => {
        setPosts(res.data.posts);
        setTotal(res.data.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (editing === null) loadPosts();
  }, [page, statusFilter, editing]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this post permanently?")) return;
    try {
      await client().delete(`/admin/blog/${id}`);
      loadPosts();
    } catch {}
  }

  // Editing mode
  if (editing !== null) {
    return (
      <PostEditor
        post={editing === "new" ? null : editing}
        adminKey={adminKey}
        onSaved={() => setEditing(null)}
        onCancel={() => setEditing(null)}
      />
    );
  }

  const totalPages = Math.ceil(total / 20);

  return (
    <div>
      {/* Toolbar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            style={{
              padding: "8px 12px",
              borderRadius: "var(--radius)",
              border: "1px solid var(--border)",
              fontSize: 13,
              background: "var(--bg-surface)",
              color: "var(--text-primary)",
            }}
          >
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="published">Published</option>
          </select>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{total} posts</span>
        </div>
        <button
          onClick={() => setEditing("new")}
          style={{
            padding: "8px 20px",
            border: "none",
            borderRadius: "var(--radius)",
            background: "var(--primary)",
            color: "#fff",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >New Post</button>
      </div>

      {/* Posts list */}
      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>Loading...</div>
      ) : posts.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--text-muted)" }}>
          No posts yet. Create your first blog post!
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Title</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Status</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Published</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Updated</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {posts.map((p) => (
              <tr key={p.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                <td style={{ padding: "12px", fontSize: 14 }}>
                  <div style={{ fontWeight: 500, color: "var(--text-primary)" }}>{p.title}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>/{p.slug}</div>
                </td>
                <td style={{ padding: "12px" }}>
                  <span style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "2px 10px",
                    borderRadius: 12,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    background: p.status === "published" ? "var(--success-bg)" : "var(--bg-sunken)",
                    color: p.status === "published" ? "var(--success)" : "var(--text-muted)",
                  }}>{p.status}</span>
                </td>
                <td style={{ padding: "12px", fontSize: 13, color: "var(--text-secondary)" }}>
                  {p.published_at ? new Date(p.published_at).toLocaleDateString() : "—"}
                </td>
                <td style={{ padding: "12px", fontSize: 13, color: "var(--text-secondary)" }}>
                  {new Date(p.updated_at).toLocaleDateString()}
                </td>
                <td style={{ padding: "12px" }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={() => setEditing(p)}
                      style={{ padding: "4px 12px", fontSize: 12, border: "1px solid var(--border)", borderRadius: "var(--radius-xs)", background: "var(--bg-surface)", cursor: "pointer", color: "var(--text-secondary)" }}
                    >Edit</button>
                    {p.status === "published" && (
                      <a
                        href={`/blog/${p.slug}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ padding: "4px 12px", fontSize: 12, border: "1px solid var(--border)", borderRadius: "var(--radius-xs)", background: "var(--bg-surface)", color: "var(--primary)", textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                      >View</a>
                    )}
                    <button
                      onClick={() => handleDelete(p.id)}
                      style={{ padding: "4px 12px", fontSize: 12, border: "1px solid var(--danger-border)", borderRadius: "var(--radius-xs)", background: "var(--danger-bg)", cursor: "pointer", color: "var(--danger)" }}
                    >Delete</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 20 }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius)", fontSize: 13, cursor: page <= 1 ? "default" : "pointer", background: "var(--bg-surface)", color: page <= 1 ? "var(--text-disabled)" : "var(--text-primary)" }}>Prev</button>
          <span style={{ padding: "6px 10px", fontSize: 13, color: "var(--text-secondary)" }}>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius)", fontSize: 13, cursor: page >= totalPages ? "default" : "pointer", background: "var(--bg-surface)", color: page >= totalPages ? "var(--text-disabled)" : "var(--text-primary)" }}>Next</button>
        </div>
      )}
    </div>
  );
}
