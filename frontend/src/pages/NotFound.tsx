import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useHead } from "../hooks/useHead";

/**
 * Catch-all 404 page. Mounted at <Route path="*"> in App.tsx so that unknown
 * URLs render something intentional instead of a blank SPA shell (which
 * Googlebot was previously interpreting as a soft 404 — that's what surfaced
 * in Search Console).
 *
 * Notes:
 * - We can't return an HTTP 404 from a static SPA — nginx still serves
 *   index.html with a 200. The next-best thing is a clear UI plus
 *   `<meta name="robots" content="noindex,follow">` so the page doesn't
 *   enter the index and any links it contains are still discoverable.
 * - `prerender-status-code` is honoured by Prerender.io / Rendertron-style
 *   pre-renderers if we ever add one. Harmless if no prerenderer is in use.
 */
export default function NotFound() {
  const { t } = useTranslation();

  useHead({
    title: `${t("notFound.title")} · QualiPulse`,
    metas: [
      { name: "robots", content: "noindex,follow" },
      { name: "prerender-status-code", content: "404" },
    ],
  });

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-base)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}
    >
      <div
        style={{
          maxWidth: 480,
          textAlign: "center",
          padding: "48px 24px",
        }}
      >
        <Link
          to="/"
          style={{
            textDecoration: "none",
            color: "var(--text-primary)",
            fontWeight: 700,
            fontSize: 18,
          }}
        >
          QualiPulse
        </Link>

        <div
          aria-hidden="true"
          style={{
            fontSize: 72,
            fontWeight: 800,
            color: "var(--primary, #6366f1)",
            margin: "32px 0 12px",
            lineHeight: 1,
          }}
        >
          404
        </div>

        <h1
          style={{
            fontSize: 22,
            fontWeight: 700,
            color: "var(--text-primary)",
            marginBottom: 10,
          }}
        >
          {t("notFound.title")}
        </h1>

        <p
          style={{
            fontSize: 15,
            color: "var(--text-secondary)",
            marginBottom: 28,
            lineHeight: 1.55,
          }}
        >
          {t("notFound.body")}
        </p>

        <div
          style={{
            display: "flex",
            gap: 12,
            justifyContent: "center",
            flexWrap: "wrap",
          }}
        >
          <Link to="/" className="btn btn-primary">
            {t("notFound.ctaHome")}
          </Link>
          <Link to="/blog" className="btn btn-ghost">
            {t("notFound.ctaBlog")}
          </Link>
        </div>
      </div>
    </div>
  );
}
