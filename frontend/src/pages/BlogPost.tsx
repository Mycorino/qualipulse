import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { getPublishedPost, type BlogPost } from "../api/blog";
import { NewsletterCTA } from "./Blog";

export default function BlogPostPage() {
  const { slug } = useParams<{ slug: string }>();
  const [post, setPost] = useState<BlogPost | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    getPublishedPost(slug)
      .then((res) => setPost(res.data))
      .catch((err) => {
        if (err.response?.status === 404) setNotFound(true);
      })
      .finally(() => setLoading(false));
  }, [slug]);

  function formatDate(iso: string | null) {
    if (!iso) return "";
    return new Date(iso).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: "var(--text-muted)" }}>Loading...</p>
      </div>
    );
  }

  if (notFound || !post) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg-base)", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: "16px" }}>
        <h1 style={{ fontSize: "24px", color: "var(--text-primary)" }}>Post not found</h1>
        <Link to="/blog" style={{ color: "var(--primary)", textDecoration: "none" }}>Back to blog</Link>
      </div>
    );
  }

  const metaTitle = post.meta_title || post.title;
  const metaDescription = post.meta_description || post.excerpt || "";
  const ogImage = post.og_image_url || post.cover_image_url || "";

  return (
    <>
      <Helmet>
        <title>{metaTitle} — QualiPulse Blog</title>
        <meta name="description" content={metaDescription} />
        <meta property="og:title" content={metaTitle} />
        <meta property="og:description" content={metaDescription} />
        <meta property="og:type" content="article" />
        {ogImage && <meta property="og:image" content={ogImage} />}
        <meta property="article:published_time" content={post.published_at || ""} />
        <meta property="article:author" content={post.author_name} />
        {post.tags.map((tag) => (
          <meta key={tag} property="article:tag" content={tag} />
        ))}
        <script type="application/ld+json">
          {JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Article",
            headline: post.title,
            description: metaDescription,
            image: ogImage || undefined,
            datePublished: post.published_at,
            author: {
              "@type": "Person",
              name: post.author_name,
            },
            publisher: {
              "@type": "Organization",
              name: "QualiPulse",
            },
          })}
        </script>
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
            <Link to="/blog" style={{ color: "var(--text-secondary)", textDecoration: "none", fontWeight: 500, fontSize: "14px" }}>Blog</Link>
            <Link to="/login" style={{ color: "var(--text-secondary)", textDecoration: "none", fontSize: "14px" }}>Log in</Link>
            <Link to="/signup" style={{
              background: "var(--primary)",
              color: "#fff",
              padding: "8px 16px",
              borderRadius: "var(--radius)",
              textDecoration: "none",
              fontSize: "14px",
              fontWeight: 500,
            }}>Get Started</Link>
          </nav>
        </header>

        {/* Cover image */}
        {post.cover_image_url && (
          <div style={{
            maxWidth: "900px",
            margin: "32px auto 0",
            padding: "0 24px",
          }}>
            <img
              src={post.cover_image_url}
              alt={post.title}
              style={{
                width: "100%",
                maxHeight: "400px",
                objectFit: "cover",
                borderRadius: "var(--radius-lg)",
              }}
            />
          </div>
        )}

        {/* Article */}
        <article style={{
          maxWidth: "720px",
          margin: "0 auto",
          padding: "40px 24px 32px",
        }}>
          {/* Tags */}
          {post.tags.length > 0 && (
            <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
              {post.tags.map((tag) => (
                <Link
                  key={tag}
                  to={`/blog?tag=${encodeURIComponent(tag)}`}
                  style={{
                    fontSize: "11px",
                    fontWeight: 600,
                    color: "var(--primary)",
                    background: "var(--brand-50)",
                    padding: "3px 10px",
                    borderRadius: "var(--radius-xs)",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    textDecoration: "none",
                  }}
                >{tag}</Link>
              ))}
            </div>
          )}

          <h1 style={{
            fontSize: "36px",
            fontWeight: 700,
            color: "var(--text-primary)",
            lineHeight: 1.2,
            marginBottom: "12px",
          }}>{post.title}</h1>

          {post.subtitle && (
            <p style={{ fontSize: "20px", color: "var(--text-secondary)", lineHeight: 1.4, marginBottom: "16px" }}>
              {post.subtitle}
            </p>
          )}

          <div style={{
            fontSize: "14px",
            color: "var(--text-muted)",
            marginBottom: "32px",
            paddingBottom: "24px",
            borderBottom: "1px solid var(--border-subtle)",
          }}>
            {post.author_name} &middot; {formatDate(post.published_at)}
          </div>

          {/* Content */}
          <div
            className="blog-content"
            dangerouslySetInnerHTML={{ __html: post.content }}
            style={{
              fontSize: "16px",
              lineHeight: 1.75,
              color: "var(--text-primary)",
            }}
          />
        </article>

        {/* Back to blog */}
        <div style={{ maxWidth: "720px", margin: "0 auto", padding: "0 24px 32px" }}>
          <Link to="/blog" style={{
            color: "var(--primary)",
            textDecoration: "none",
            fontSize: "14px",
            fontWeight: 500,
          }}>&larr; Back to all posts</Link>
        </div>

        {/* Newsletter */}
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
            <Link to="/" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>Home</Link>
            <Link to="/blog" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>Blog</Link>
            <Link to="/terms" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>Terms</Link>
            <Link to="/privacy" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>Privacy</Link>
          </div>
          &copy; {new Date().getFullYear()} QualiPulse. All rights reserved.
        </footer>
      </div>
    </>
  );
}
