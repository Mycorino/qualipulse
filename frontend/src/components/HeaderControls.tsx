import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "./LanguageSwitcher";
import type { ProjectListItem } from "../api/projects";

/**
 * ProjectSwitcher
 * Renders a clickable button labelled with the current project name.
 * Click → dropdown listing the user's non-archived projects (incl. demo).
 * Selecting a project navigates to it.
 */
export function ProjectSwitcher({
  currentId,
  currentName,
  projects,
  participantCount,
  isActive,
}: {
  currentId: string | undefined;
  currentName: string;
  projects: ProjectListItem[];
  participantCount: number;
  isActive: boolean;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation("project");
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", onDocClick);
      document.addEventListener("keydown", onKey);
    }
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const visible = projects.filter((p) => !p.archived_at);
  const subtitle = `${t("switcher.participants", { count: participantCount, defaultValue: "{{count}} participants" })} · ${
    isActive
      ? t("switcher.active", { defaultValue: "Active" })
      : t("switcher.inactive", { defaultValue: "Inactive" })
  }`;

  return (
    <div className="project-switcher" ref={wrapRef}>
      <button
        className="project-switcher__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="project-switcher__name">{currentName}</span>
        <span className="project-switcher__sub">{subtitle}</span>
        <span className="project-switcher__chevron" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="project-switcher__menu" role="listbox">
          {visible.length === 0 ? (
            <div className="project-switcher__empty">
              {t("switcher.empty", { defaultValue: "No other projects." })}
            </div>
          ) : (
            visible.map((p) => {
              const isCurrent = p.id === currentId;
              return (
                <button
                  key={p.id}
                  role="option"
                  aria-selected={isCurrent}
                  className={`project-switcher__item${isCurrent ? " is-current" : ""}`}
                  onClick={() => {
                    setOpen(false);
                    if (!isCurrent) navigate(`/projects/${p.id}`);
                  }}
                >
                  <span className="project-switcher__item-name">
                    {p.is_demo ? "★ " : ""}
                    {p.name}
                  </span>
                  <span className="project-switcher__item-meta">
                    {t("switcher.completed", {
                      count: p.completed_count,
                      defaultValue: "{{count}} responses",
                    })}
                  </span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

/**
 * AccountMenu — avatar dropdown, shown at all viewport widths.
 * Renders a circular avatar with the company's first initial. On click,
 * shows a menu with Account Settings, language toggle, Sign Out.
 * It's the only account affordance on the QuantiTopBar hub (which has no
 * hamburger nav), so it must stay reachable on mobile too.
 */
export function AccountMenu({
  initial,
  onSignOut,
}: {
  initial: string;
  onSignOut: () => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", onDocClick);
      document.addEventListener("keydown", onKey);
    }
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="account-menu" ref={wrapRef}>
      <button
        className="account-menu__avatar"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t("account")}
        onClick={() => setOpen((v) => !v)}
      >
        {initial}
      </button>
      {open && (
        <div className="account-menu__dropdown" role="menu">
          <button
            role="menuitem"
            className="account-menu__item"
            onClick={() => {
              setOpen(false);
              navigate("/account");
            }}
          >
            {t("account")}
          </button>
          <div className="account-menu__row" role="none">
            <span className="account-menu__row-label">{t("language", { defaultValue: "Language" })}</span>
            <LanguageSwitcher variant="light" />
          </div>
          <div className="account-menu__divider" role="separator" />
          <button
            role="menuitem"
            className="account-menu__item"
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}
          >
            {t("signOut")}
          </button>
        </div>
      )}
    </div>
  );
}
