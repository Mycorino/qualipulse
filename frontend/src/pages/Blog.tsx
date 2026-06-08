import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { getPublishedPosts, type BlogPost } from "../api/blog";

export default function Blog() {
  const { t } = useTranslation("blog");
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    getPublishedPosts(page, selectedTag ?? undefined)
      .then((res) => {
        setPosts(res.data.posts);
        setTotal(res.data.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, selectedTag]);

  const allTags = [...new Set(posts.flatMap((p) => p.tags))];
  const totalPages = Math.ceil(total / 12);

  function formatDate(iso: string | null) {
    if (!iso) return "";
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  return (
    <>
      <Helmet>
        <title>{t("list.metaTitle")}</title>
        <meta name="description" content={t("list.metaDescription")} />
        <meta property="og:title" content={t("list.ogTitle")} />
        <meta property="og:description" content={t("list.ogDescription")} />
        <meta property="og:type" content="website" />
      </Helmet>

      <div style={{ minHeight: "100vh", background: "var(--bg-base)" }}>
        {/* Header */}
        <header style={{
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border)",
          padding: "16px 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <Link to="/" style={{ textDecoration: "none", color: "var(--text-primary)", fontWeight: 700, fontSize: "18px" }}>
            QualiPulse
          </Link>
          <nav style={{ display: "flex", gap: "24px", alignItems: "center" }}>
            <Link to="/blog" style={{ color: "var(--primary)", textDecoration: "none", fontWeight: 500, fontSize: "14px" }}>{t("footer.blog")}</Link>
            <Link to="/login" style={{ color: "var(--text-secondary)", textDecoration: "none", fontSize: "14px" }}>{t("footer.logIn")}</Link>
            <Link to="/signup" style={{
              background: "var(--primary)",
              color: "#fff",
              padding: "8px 16px",
              borderRadius: "var(--radius)",
              textDecoration: "none",
              fontSize: "14px",
              fontWeight: 500,
            }}>{t("footer.getStartedFree")}</Link>
          </nav>
        </header>

        {/* Hero */}
        <section style={{
          maxWidth: "800px",
          margin: "0 auto",
          padding: "64px 24px 32px",
          textAlign: "center",
        }}>
          <h1 style={{ fontSize: "36px", fontWeight: 700, color: "var(--text-primary)", marginBottom: "12px" }}>
            {t("list.heroTitle")}
          </h1>
          <p style={{ fontSize: "18px", color: "var(--text-secondary)", lineHeight: 1.6 }}>
            {t("list.heroSubtitle")}
          </p>
        </section>

        {/* Tag filter */}
        {allTags.length > 0 && (
          <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "0 24px 24px", display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "center" }}>
            <button
              onClick={() => { setSelectedTag(null); setPage(1); }}
              style={{
                padding: "6px 14px",
                borderRadius: "var(--radius-xl)",
                border: "1px solid var(--border)",
                background: !selectedTag ? "var(--primary)" : "var(--bg-surface)",
                color: !selectedTag ? "#fff" : "var(--text-secondary)",
                fontSize: "13px",
                cursor: "pointer",
                fontWeight: 500,
              }}
            >{t("list.allTags")}</button>
            {allTags.map((tag) => (
              <button
                key={tag}
                onClick={() => { setSelectedTag(tag); setPage(1); }}
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--radius-xl)",
                  border: "1px solid var(--border)",
                  background: selectedTag === tag ? "var(--primary)" : "var(--bg-surface)",
                  color: selectedTag === tag ? "#fff" : "var(--text-secondary)",
                  fontSize: "13px",
                  cursor: "pointer",
                  fontWeight: 500,
                }}
              >{tag}</button>
            ))}
          </div>
        )}

        {/* Posts grid */}
        <section style={{ maxWidth: "1100px", margin: "0 auto", padding: "0 24px 64px" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text-muted)" }}>{t("list.loading")}</div>
          ) : posts.length === 0 ? (
            <div style={{ textAlign: "center", padding: "40px 20px" }}>
              <p style={{ fontSize: "16px", color: "var(--text-secondary)", marginBottom: "12px" }}>{t("list.emptyTitle")}</p>
              <p style={{ fontSize: "14px", color: "var(--text-muted)" }}>{t("list.emptyBody")}</p>
            </div>
          ) : (
            <>
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                gap: "24px",
              }}>
                {posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/blog/${post.slug}`}
                    style={{ textDecoration: "none", color: "inherit" }}
                  >
                    <article style={{
                      background: "var(--bg-surface)",
                      borderRadius: "var(--radius-lg)",
                      border: "1px solid var(--border)",
                      overflow: "hidden",
                      transition: "box-shadow 0.2s, transform 0.2s",
                      cursor: "pointer",
                    }}
                      onMouseEnter={(e) => { e.currentTarget.style.boxShadow = "var(--shadow-md)"; e.currentTarget.style.transform = "translateY(-2px)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "none"; e.currentTarget.style.transform = "none"; }}
                    >
                      {post.cover_image_url && (
                        <div style={{
                          width: "100%",
                          height: "180px",
                          background: `url(${post.cover_image_url}) center / cover no-repeat`,
                          borderBottom: "1px solid var(--border-subtle)",
                        }} />
                      )}
                      <div style={{ padding: "20px" }}>
                        <div style={{ display: "flex", gap: "8px", marginBottom: "10px", flexWrap: "wrap" }}>
                          {post.tags.map((tag) => (
                            <span key={tag} style={{
                              fontSize: "11px",
                              fontWeight: 600,
                              color: "var(--primary)",
                              background: "var(--brand-50)",
                              padding: "2px 8px",
                              borderRadius: "var(--radius-xs)",
                              textTransform: "uppercase",
                              letterSpacing: "0.5px",
                            }}>{tag}</span>
                          ))}
                        </div>
                        <h2 style={{ fontSize: "18px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "8px", lineHeight: 1.3 }}>
                          {post.title}
                        </h2>
                        {post.excerpt && (
                          <p style={{ fontSize: "14px", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "12px" }}>
                            {post.excerpt}
                          </p>
                        )}
                        <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                          {t("list.byline", { author: post.author_name, date: formatDate(post.published_at) })}
                        </div>
                      </div>
                    </article>
                  </Link>
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div style={{ display: "flex", justifyContent: "center", gap: "8px", marginTop: "40px" }}>
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                    style={{
                      padding: "8px 16px",
                      borderRadius: "var(--radius)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-surface)",
                      color: page <= 1 ? "var(--text-disabled)" : "var(--text-primary)",
                      cursor: page <= 1 ? "default" : "pointer",
                      fontSize: "14px",
                    }}
                  >{t("list.previous")}</button>
                  <span style={{ padding: "8px 12px", fontSize: "14px", color: "var(--text-secondary)" }}>
                    {t("list.pageOf", { page, totalPages })}
                  </span>
                  <button
                    disabled={page >= totalPages}
                    onClick={() => setPage(page + 1)}
                    style={{
                      padding: "8px 16px",
                      borderRadius: "var(--radius)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-surface)",
                      color: page >= totalPages ? "var(--text-disabled)" : "var(--text-primary)",
                      cursor: page >= totalPages ? "default" : "pointer",
                      fontSize: "14px",
                    }}
                  >{t("list.next")}</button>
                </div>
              )}
            </>
          )}
        </section>

        {/* Newsletter CTA */}
        <NewsletterCTA />

        {/* Footer */}
        <footer style={{
          background: "var(--bg-surface)",
          borderTop: "1px solid var(--border)",
          padding: "32px 24px",
          textAlign: "center",
          fontSize: "13px",
          color: "var(--text-muted)",
        }}>
          <div style={{ display: "flex", gap: "24px", justifyContent: "center", marginBottom: "12px" }}>
            <Link to="/" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>{t("footer.home")}</Link>
            <Link to="/blog" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>{t("footer.blog")}</Link>
            <Link to="/terms" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>{t("footer.terms")}</Link>
            <Link to="/privacy" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>{t("footer.privacy")}</Link>
          </div>
          {t("footer.copyright", { year: new Date().getFullYear() })}
        </footer>
      </div>
    </>
  );
}

export function NewsletterCTA() {
  const { t } = useTranslation("blog");
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await fetch("/api/auth/newsletter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || t("newsletter.errorGeneric"));
      }
      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || t("newsletter.errorGeneric"));
    }
  }

  return (
    <section style={{
      maxWidth: "600px",
      margin: "0 auto",
      padding: "48px 24px 64px",
      textAlign: "center",
    }}>
      <div style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        padding: "40px 32px",
      }}>
        <h3 style={{ fontSize: "22px", fontWeight: 700, color: "var(--text-primary)", marginBottom: "8px" }}>
          {t("newsletter.heading")}
        </h3>
        <p style={{ fontSize: "14px", color: "var(--text-secondary)", marginBottom: "20px", lineHeight: 1.5 }}>
          {t("newsletter.body")}
        </p>
        {submitted ? (
          <p style={{ color: "var(--success)", fontWeight: 500 }}>{t("newsletter.subscribed")}</p>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: "flex", gap: "8px", maxWidth: "400px", margin: "0 auto" }}>
            <input
              type="email"
              required
              placeholder={t("newsletter.emailPlaceholder")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
                fontSize: "14px",
                outline: "none",
              }}
            />
            <button type="submit" style={{
              padding: "10px 20px",
              background: "var(--primary)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              fontSize: "14px",
              fontWeight: 500,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}>{t("newsletter.subscribe")}</button>
          </form>
        )}
        {error && <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "8px" }}>{error}</p>}
      </div>
    </section>
  );
}
