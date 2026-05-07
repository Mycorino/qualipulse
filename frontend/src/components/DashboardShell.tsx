import type { ReactNode } from "react";

/**
 * DashboardShell — the layout primitive for any quanti dashboard surface.
 *
 * Sticky `--dashboard-sidebar-w` left rail + bg-sunken canvas right. The
 * sidebar is for study navigation (overview / per-question / segments /
 * raw responses) and is the slot for the `compare-chips` filter row when
 * present.
 *
 * On <960px the sidebar collapses to a horizontal top bar, matching the
 * existing Dashboard hamburger pattern. The canvas always scrolls
 * independently of the sidebar.
 */
interface DashboardShellProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export function DashboardShell({ sidebar, children }: DashboardShellProps) {
  return (
    <div className="dashboard-shell">
      <aside className="dashboard-shell__sidebar">{sidebar}</aside>
      <main className="dashboard-shell__canvas">{children}</main>
    </div>
  );
}

/**
 * DashboardStrip — the 3-up summary row that anchors every dashboard page.
 *
 * Editorial discipline: 3 numbers max — N respondents, completion rate,
 * fielding window. Reusing this primitive across surveys, panel views, and
 * project-level rollups keeps the metric vocabulary consistent. Each tile
 * uses the serif for the value and tabular-nums so number columns line up.
 */
export interface DashboardStripItem {
  label: string;
  value: string;
  /** Optional one-line note under the value, e.g. "↑ 12pp vs last week". */
  delta?: string;
  /** Sentiment of the delta — colours the small note. */
  deltaTone?: "positive" | "negative" | "neutral";
}

export function DashboardStrip({ items }: { items: DashboardStripItem[] }) {
  return (
    <div className="dashboard-strip" role="group" aria-label="Dashboard summary">
      {items.map((item) => (
        <div key={item.label} className="dashboard-strip__item">
          <div className="dashboard-strip__label">{item.label}</div>
          <div className="dashboard-strip__value tabular">{item.value}</div>
          {item.delta && (
            <div
              className={`dashboard-strip__delta dashboard-strip__delta--${item.deltaTone ?? "neutral"}`}
            >
              {item.delta}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
