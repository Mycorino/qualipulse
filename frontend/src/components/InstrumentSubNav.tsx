import type { ReactNode } from "react";

export interface InstrumentSection {
  key: string;
  label: string;
  /** Optional trailing badge, e.g. a response count. */
  badge?: ReactNode;
}

interface InstrumentSubNavProps {
  sections: InstrumentSection[];
  active: string;
  onChange: (key: string) => void;
  ariaLabel?: string;
}

/**
 * InstrumentSubNav — the LOCAL navigation inside one instrument
 * (a survey or an interview round).
 *
 * Deliberately a segmented control, not an underline tab bar: the Study
 * workspace already owns the underline tab bar, so an instrument's own
 * sections must read as visually subordinate. One glance should tell a
 * user which navigation is primary and which is local — that's the whole
 * point of the navigation-unification work.
 */
export function InstrumentSubNav({
  sections,
  active,
  onChange,
  ariaLabel = "Sections",
}: InstrumentSubNavProps) {
  return (
    <div className="instrument-subnav" role="tablist" aria-label={ariaLabel}>
      {sections.map((s) => {
        const isActive = s.key === active;
        return (
          <button
            key={s.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={`instrument-subnav__item${
              isActive ? " instrument-subnav__item--active" : ""
            }`}
            onClick={() => onChange(s.key)}
          >
            <span>{s.label}</span>
            {s.badge != null && (
              <span className="instrument-subnav__badge">{s.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
