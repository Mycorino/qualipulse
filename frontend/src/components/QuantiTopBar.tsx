import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { getMe } from "../api/auth";
import { useAuth } from "../hooks/useAuth";
import { AccountMenu } from "./HeaderControls";

/**
 * QuantiTopBar — the universal app chrome.
 *
 * Sprint 17: now that the Studies list IS the home (`/dashboard` renders
 * it), the old standalone "Dashboard" button is redundant — the
 * QualiPulse wordmark already routes home. This bar is now three
 * elements: wordmark (home) · breadcrumb (climb) · account menu.
 *
 * Self-contained: fetches `me` for the avatar initial and owns sign-out
 * via useAuth, so no page has to thread account props.
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
  const { logout } = useAuth();
  const { t } = useTranslation("shell");
  const [initial, setInitial] = useState("?");

  useEffect(() => {
    getMe()
      .then((me) => {
        const source = (me.name || me.email || "?").trim();
        setInitial(source.charAt(0).toUpperCase() || "?");
      })
      .catch(() => setInitial("?"));
  }, []);

  return (
    <div className="quanti-topbar">
      <button
        type="button"
        className="quanti-topbar__logo"
        onClick={() => navigate("/dashboard")}
        aria-label={t("topBar.homeAriaLabel")}
      >
        QualiPulse
      </button>
      <nav className="quanti-topbar__crumbs" aria-label={t("topBar.breadcrumbAriaLabel")}>
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
      <div className="quanti-topbar__account">
        <AccountMenu initial={initial} onSignOut={logout} />
      </div>
    </div>
  );
}
