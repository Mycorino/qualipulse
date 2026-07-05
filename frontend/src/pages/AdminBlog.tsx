import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useEditor, EditorContent, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import Placeholder from "@tiptap/extension-placeholder";
import axios from "axios";
import DOMPurify from "dompurify";

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

const UPLOADABLE_IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

async function uploadBlogImage(adminKey: string, file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await adminClient(adminKey).post<{ url: string }>("/admin/blog/upload-image", form);
  return res.data.url;
}

// ── Toolbar ────────────────────────────────────────────────────────────────

function Toolbar({
  editor,
  onUploadImage,
  uploadingImage,
}: {
  editor: ReturnType<typeof useEditor>;
  onUploadImage: (file: File) => void;
  uploadingImage: boolean;
}) {
  const { t } = useTranslation("blog");
  const fileInputRef = useRef<HTMLInputElement>(null);
  if (!editor) return null;

  function addImageUrl() {
    const url = window.prompt(t("admin.imageUrlPrompt"));
    if (url) editor!.chain().focus().setImage({ src: url }).run();
  }

  function addLink() {
    const url = window.prompt(t("admin.linkUrlPrompt"));
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
      <button type="button" onClick={() => editor!.chain().focus().toggleBulletList().run()} className={editor!.isActive("bulletList") ? "is-active" : ""}>{t("admin.toolbarList")}</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleOrderedList().run()} className={editor!.isActive("orderedList") ? "is-active" : ""}>1.2.3</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleBlockquote().run()} className={editor!.isActive("blockquote") ? "is-active" : ""}>{t("admin.toolbarQuote")}</button>
      <button type="button" onClick={() => editor!.chain().focus().toggleCodeBlock().run()} className={editor!.isActive("codeBlock") ? "is-active" : ""}>{t("admin.toolbarCode")}</button>
      <span style={{ width: 1, background: "var(--border)", margin: "0 4px" }} />
      <button type="button" onClick={addLink}>{t("admin.toolbarLink")}</button>
      <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploadingImage}>
        {uploadingImage ? t("admin.uploading") : t("admin.toolbarImage")}
      </button>
      <button type="button" onClick={addImageUrl}>{t("admin.toolbarImageUrl")}</button>
      <button type="button" onClick={() => editor!.chain().focus().setHorizontalRule().run()}>HR</button>
      <input
        ref={fileInputRef}
        type="file"
        accept={UPLOADABLE_IMAGE_TYPES.join(",")}
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUploadImage(file);
          e.target.value = "";
        }}
      />
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
  const { t, i18n } = useTranslation("blog");
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
  const [uploadingImage, setUploadingImage] = useState(false);
  const editorRef = useRef<Editor | null>(null);

  const uploadAndInsert = useCallback(
    async (file: File) => {
      if (!UPLOADABLE_IMAGE_TYPES.includes(file.type)) return;
      setError("");
      setUploadingImage(true);
      try {
        const url = await uploadBlogImage(adminKey, file);
        editorRef.current?.chain().focus().setImage({ src: url }).run();
      } catch (err: any) {
        setError(err.response?.data?.detail || t("admin.uploadFailed"));
      } finally {
        setUploadingImage(false);
      }
    },
    [adminKey, t]
  );

  const editor = useEditor({
    extensions: [
      StarterKit,
      Link.configure({ openOnClick: false }),
      Image,
      Placeholder.configure({ placeholder: t("admin.contentPlaceholder") }),
    ],
    content: post?.content ?? "",
    editorProps: {
      // Paste / drop an image file straight into the editor → upload → insert.
      handlePaste: (_view, event) => {
        const file = Array.from(event.clipboardData?.files ?? []).find((f) =>
          UPLOADABLE_IMAGE_TYPES.includes(f.type)
        );
        if (file) {
          uploadAndInsert(file);
          return true;
        }
        return false;
      },
      handleDrop: (_view, event) => {
        const file = Array.from(event.dataTransfer?.files ?? []).find((f) =>
          UPLOADABLE_IMAGE_TYPES.includes(f.type)
        );
        if (file) {
          event.preventDefault();
          uploadAndInsert(file);
          return true;
        }
        return false;
      },
    },
  });

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  const [uploadingCover, setUploadingCover] = useState(false);
  const coverInputRef = useRef<HTMLInputElement>(null);

  async function uploadCover(file: File) {
    setError("");
    setUploadingCover(true);
    try {
      setCoverUrl(await uploadBlogImage(adminKey, file));
    } catch (err: any) {
      setError(err.response?.data?.detail || t("admin.uploadFailed"));
    } finally {
      setUploadingCover(false);
    }
  }

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
      setError(err.response?.data?.detail || t("admin.saveFailed"));
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
        <h2 style={{ fontSize: 20, fontWeight: 600 }}>{post ? t("admin.editPost") : t("admin.newPost")}</h2>
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
          >{showPreview ? t("admin.hidePreview") : t("admin.preview")}</button>
          <button onClick={onCancel} style={{ padding: "8px 16px", border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--bg-surface)", color: "var(--text-secondary)", fontSize: 13, cursor: "pointer" }}>{t("admin.cancel")}</button>
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
          >{saving ? t("admin.saving") : t("admin.save")}</button>
        </div>
      </div>

      {error && <div style={{ color: "var(--danger)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: showPreview ? "1fr 1fr" : "1fr", gap: 24 }}>
        {/* Editor column */}
        <div>
          {/* Title */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>{t("admin.fieldTitle")}</label>
            <input value={title} onChange={(e) => handleTitleChange(e.target.value)} style={{ ...inputStyle, fontSize: 18, fontWeight: 600 }} placeholder={t("admin.fieldTitlePlaceholder")} />
          </div>

          {/* Subtitle */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>{t("admin.fieldSubtitle")}</label>
            <input value={subtitle} onChange={(e) => setSubtitle(e.target.value)} style={inputStyle} placeholder={t("admin.fieldSubtitlePlaceholder")} />
          </div>

          {/* Slug + Status row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={labelStyle}>{t("admin.fieldSlug")}</label>
              <input
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugManual(true); }}
                style={inputStyle}
                placeholder={t("admin.fieldSlugPlaceholder")}
              />
            </div>
            <div>
              <label style={labelStyle}>{t("admin.fieldStatus")}</label>
              <select
                value={postStatus}
                onChange={(e) => setPostStatus(e.target.value)}
                style={{ ...inputStyle, cursor: "pointer" }}
              >
                <option value="draft">{t("admin.statusDraft")}</option>
                <option value="published">{t("admin.statusPublished")}</option>
              </select>
            </div>
          </div>

          {/* Content editor */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>{t("admin.fieldContent")}</label>
            <div className="tiptap-editor">
              <Toolbar editor={editor} onUploadImage={uploadAndInsert} uploadingImage={uploadingImage} />
              <EditorContent editor={editor} />
            </div>
          </div>

          {/* Excerpt */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>{t("admin.fieldExcerpt")}</label>
            <textarea value={excerpt} onChange={(e) => setExcerpt(e.target.value)} style={{ ...inputStyle, minHeight: 60, resize: "vertical" }} placeholder={t("admin.fieldExcerptPlaceholder")} />
          </div>

          {/* Cover image + Author row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            <div>
              <label style={labelStyle}>{t("admin.fieldCoverImage")}</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input value={coverUrl} onChange={(e) => setCoverUrl(e.target.value)} style={inputStyle} placeholder="https://..." />
                <button
                  type="button"
                  onClick={() => coverInputRef.current?.click()}
                  disabled={uploadingCover}
                  style={{
                    padding: "8px 12px",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    background: "var(--bg-surface)",
                    color: "var(--text-secondary)",
                    fontSize: 13,
                    cursor: uploadingCover ? "default" : "pointer",
                    whiteSpace: "nowrap",
                  }}
                >{uploadingCover ? t("admin.uploading") : t("admin.uploadButton")}</button>
                <input
                  ref={coverInputRef}
                  type="file"
                  accept={UPLOADABLE_IMAGE_TYPES.join(",")}
                  style={{ display: "none" }}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadCover(file);
                    e.target.value = "";
                  }}
                />
              </div>
            </div>
            <div>
              <label style={labelStyle}>{t("admin.fieldAuthor")}</label>
              <input value={authorName} onChange={(e) => setAuthorName(e.target.value)} style={inputStyle} />
            </div>
          </div>

          {/* Tags */}
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>{t("admin.fieldTags")}</label>
            <input value={tagsStr} onChange={(e) => setTagsStr(e.target.value)} style={inputStyle} placeholder={t("admin.fieldTagsPlaceholder")} />
          </div>

          {/* SEO section */}
          <details style={{ marginBottom: 12 }}>
            <summary style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", cursor: "pointer", marginBottom: 8 }}>{t("admin.seoSection")}</summary>
            <div style={{ display: "grid", gap: 12 }}>
              <div>
                <label style={labelStyle}>{t("admin.fieldMetaTitle")}</label>
                <input value={metaTitle} onChange={(e) => setMetaTitle(e.target.value)} style={inputStyle} placeholder={t("admin.fieldMetaTitlePlaceholder")} />
              </div>
              <div>
                <label style={labelStyle}>{t("admin.fieldMetaDescription")}</label>
                <textarea value={metaDesc} onChange={(e) => setMetaDesc(e.target.value)} style={{ ...inputStyle, minHeight: 50, resize: "vertical" }} placeholder={t("admin.fieldMetaDescriptionPlaceholder")} />
              </div>
              <div>
                <label style={labelStyle}>{t("admin.fieldOgImage")}</label>
                <input value={ogImage} onChange={(e) => setOgImage(e.target.value)} style={inputStyle} placeholder={t("admin.fieldOgImagePlaceholder")} />
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
              {t("admin.previewLabel")}
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
            <h1 style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.2, marginBottom: 8 }}>{title || t("admin.untitled")}</h1>
            {subtitle && <p style={{ fontSize: 18, color: "var(--text-secondary)", marginBottom: 12 }}>{subtitle}</p>}
            <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid var(--border-subtle)" }}>
              {authorName} &middot; {new Date().toLocaleDateString(i18n.language, { month: "long", day: "numeric", year: "numeric" })}
            </div>
            <div
              className="blog-content"
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(editor?.getHTML() ?? "") }}
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
  const { t } = useTranslation("blog");
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
    if (!window.confirm(t("admin.deleteConfirm"))) return;
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
            <option value="">{t("admin.allStatuses")}</option>
            <option value="draft">{t("admin.statusDraft")}</option>
            <option value="published">{t("admin.statusPublished")}</option>
          </select>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{t("admin.postCount", { count: total })}</span>
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
        >{t("admin.newPost")}</button>
      </div>

      {/* Posts list */}
      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>{t("list.loading")}</div>
      ) : posts.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "var(--text-muted)" }}>
          {t("admin.emptyList")}
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>{t("admin.tableTitle")}</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>{t("admin.tableStatus")}</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>{t("admin.tablePublished")}</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>{t("admin.tableUpdated")}</th>
              <th style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>{t("admin.tableActions")}</th>
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
                  }}>{p.status === "published" ? t("admin.statusPublished") : t("admin.statusDraft")}</span>
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
                    >{t("admin.edit")}</button>
                    {p.status === "published" && (
                      <a
                        href={`/blog/${p.slug}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ padding: "4px 12px", fontSize: 12, border: "1px solid var(--border)", borderRadius: "var(--radius-xs)", background: "var(--bg-surface)", color: "var(--primary)", textDecoration: "none", display: "inline-flex", alignItems: "center" }}
                      >{t("admin.view")}</a>
                    )}
                    <button
                      onClick={() => handleDelete(p.id)}
                      style={{ padding: "4px 12px", fontSize: 12, border: "1px solid var(--danger-border)", borderRadius: "var(--radius-xs)", background: "var(--danger-bg)", cursor: "pointer", color: "var(--danger)" }}
                    >{t("admin.delete")}</button>
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
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius)", fontSize: 13, cursor: page <= 1 ? "default" : "pointer", background: "var(--bg-surface)", color: page <= 1 ? "var(--text-disabled)" : "var(--text-primary)" }}>{t("admin.prev")}</button>
          <span style={{ padding: "6px 10px", fontSize: 13, color: "var(--text-secondary)" }}>{t("admin.pageOf", { page, totalPages })}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} style={{ padding: "6px 14px", border: "1px solid var(--border)", borderRadius: "var(--radius)", fontSize: 13, cursor: page >= totalPages ? "default" : "pointer", background: "var(--bg-surface)", color: page >= totalPages ? "var(--text-disabled)" : "var(--text-primary)" }}>{t("admin.next")}</button>
        </div>
      )}
    </div>
  );
}
