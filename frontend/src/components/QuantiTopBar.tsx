import { useNavigate } from "react-router-dom";

/**
 * QuantiTopBar — the global app chrome for every quanti surface.
 *
 * The Study / Survey pages were built fast with their own minimal
 * headers and skipped the app-level navigation entirely — leaving no
 * way back to the main dashboard. This component restores that:
 *
 *   [QualiPulse]  ›  Studies  ›  <current page>            [Dashboard]
 *
 * - The QualiPulse wordmark always routes to /dashboard.
 * - A breadcrumb trail shows where the researcher is + lets them climb
 *   back up one level at a time.
 * - A "Dashboard" button on the right is the explicit escape hatch.
 *
 * Pages render their own page-specific header (title, tabs, actions)
 * BELOW this bar — QuantiTopBar is only the global strip.
 */

export interface Crumb {
  label: string;
  /** Omit `to` for the current page (rendered non-clickable). */
  to?: string;
}

interface QuantiTopBarProps {
  crumbs: Crumb[];
}

export function QuantiTopBar({ crumbs }: QuantiTopBarProps) {
  const navigate = useNavigate();
  return (
    <div className="quanti-topbar">
      <button
        type="button"
        className="quanti-topbar__logo"
        onClick={() => navigate("/dashboard")}
        aria-label="Back to dashboard"
      >
        QualiPulse
      </button>
      <nav className="quanti-topbar__crumbs" aria-label="Breadcrumb">
        {crumbs.map((crumb, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <span key={`${crumb.label}-${i}`} className="quanti-topbar__crumb-wrap">
              <span className="quanti-topbar__crumb-sep" aria-hidden="true">
                ›
              </span>
              {crumb.to && !isLast ? (
                <button
                  type="button"
                  className="quanti-topbar__crumb quanti-topbar__crumb--link"
                  onClick={() => navigate(crumb.to!)}
                >
                  {crumb.label}
                </button>
              ) : (
                <span
                  className="quanti-topbar__crumb"
                  aria-current={isLast ? "page" : undefined}
                >
                  {crumb.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>
      <button
        type="button"
        className="btn btn-secondary btn-sm quanti-topbar__dashboard"
        onClick={() => navigate("/dashboard")}
      >
        Dashboard
      </button>
    </div>
  );
}
