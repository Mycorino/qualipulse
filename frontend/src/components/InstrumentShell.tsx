import type { ReactNode } from "react";

import { QuantiTopBar } from "./QuantiTopBar";
import type { Crumb } from "./QuantiTopBar";
import { InstrumentSubNav } from "./InstrumentSubNav";
import type { InstrumentSection } from "./InstrumentSubNav";

export type InstrumentStatusTone = "live" | "draft" | "closed" | "neutral";

interface InstrumentShellProps {
  /** Breadcrumb climbing Studies › <study> › <this instrument>. */
  crumbs: Crumb[];
  /** Small uppercase kicker — e.g. "Interview round" or "Survey". */
  eyebrow: string;
  title: string;
  status?: { label: string; tone?: InstrumentStatusTone };
  /** Header actions (overflow menu, secondary buttons). */
  actions?: ReactNode;
  sections: InstrumentSection[];
  activeSection: string;
  onSectionChange: (key: string) => void;
  subNavLabel?: string;
  children: ReactNode;
}

/**
 * InstrumentShell — the single shared frame for every instrument page.
 *
 * Both a survey and an interview round render through this shell, so they
 * look and behave identically: one QuantiTopBar breadcrumb (the only
 * "where am I"), one header (name · status · actions), one local
 * segmented sub-nav. No instrument page supplies its own breadcrumb or
 * tab bar — that nested chrome is exactly what the navigation critique
 * flagged as confusing.
 *
 * The shell renders the chrome and then `children` directly — it does NOT
 * wrap them in a `<main>`. Each page owns its own body element so it can
 * keep page-specific layout (e.g. the Responses tab's full-bleed grid).
 * Pages that just want the standard centred body can wrap their content
 * in `<main className="instrument-shell__main">`.
 */
export function InstrumentShell({
  crumbs,
  eyebrow,
  title,
  status,
  actions,
  sections,
  activeSection,
  onSectionChange,
  subNavLabel,
  children,
}: InstrumentShellProps) {
  return (
    <div className="instrument-shell">
      <QuantiTopBar crumbs={crumbs} />

      <header className="instrument-header">
        <div className="instrument-header__main">
          <div className="instrument-header__eyebrow">{eyebrow}</div>
          <div className="instrument-header__titlerow">
            <h1 className="instrument-header__title">{title}</h1>
            {status && (
              <span
                className={`instrument-header__status instrument-header__status--${
                  status.tone ?? "neutral"
                }`}
              >
                {status.label}
              </span>
            )}
          </div>
        </div>
        {actions && <div className="instrument-header__actions">{actions}</div>}
      </header>

      <div className="instrument-shell__subnav-row">
        <InstrumentSubNav
          sections={sections}
          active={activeSection}
          onChange={onSectionChange}
          ariaLabel={subNavLabel}
        />
      </div>

      {children}
    </div>
  );
}
