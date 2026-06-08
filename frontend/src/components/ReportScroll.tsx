import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

/**
 * ReportScroll — the scrollytelling layout for shared mixed-methods reports.
 *
 * The plan from the agent reviews: build one source-of-truth surface that
 * works as both a live web page (interactive-lite, hover quotes, play
 * audio) and a print export. Compose with FindingCard, Segment2x2, etc.
 *
 * Layout:
 *   - Cover hero (full-bleed serif title + study meta)
 *   - Sticky right-rail TOC tracking scroll position
 *   - Sections snap-aligned at section boundaries (CSS scroll-snap proximity)
 *   - Each section can opt into `pageBreak` so the print stylesheet emits
 *     an explicit page break before it (hidden in screen view)
 *
 * The TOC is computed from the `sections` prop, not by parsing children,
 * so callers stay in control of order and labels.
 */

export interface ReportSection {
  /** Slug used as the anchor id and TOC link. */
  id: string;
  /** Short label shown in the TOC, e.g. "Executive summary" or "Finding 03". */
  label: string;
  /** The section body — typically a FindingCard, Segment2x2, etc. */
  content: ReactNode;
  /** Optional grouping label, eg. "Findings" — clusters TOC entries. */
  group?: string;
  /** When true, the print stylesheet emits a page break before this section. */
  pageBreak?: boolean;
}

interface ReportScrollProps {
  /** Cover content — full-bleed hero. Typically a serif title + study meta. */
  cover: ReactNode;
  sections: ReportSection[];
}

export function ReportScroll({ cover, sections }: ReportScrollProps) {
  const { t } = useTranslation("study");
  const [activeId, setActiveId] = useState<string | null>(sections[0]?.id ?? null);

  // IntersectionObserver-driven TOC highlight. We pick the first section
  // whose top is above the viewport mid-line so it tracks the spirit of
  // "what is the user reading now" rather than what just appeared.
  useEffect(() => {
    const els = sections
      .map((s) => document.getElementById(s.id))
      .filter((el): el is HTMLElement => !!el);
    if (els.length === 0) return;
    const onScroll = () => {
      const mid = window.innerHeight * 0.4;
      let candidate: string | null = null;
      for (const el of els) {
        const rect = el.getBoundingClientRect();
        if (rect.top <= mid) candidate = el.id;
      }
      if (candidate && candidate !== activeId) setActiveId(candidate);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [sections, activeId]);

  // Group sections for the TOC.
  const tocGroups = sections.reduce<Record<string, ReportSection[]>>((acc, s) => {
    const key = s.group ?? "_";
    (acc[key] ??= []).push(s);
    return acc;
  }, {});

  return (
    <div className="report-scroll">
      <header className="report-scroll__cover">{cover}</header>
      <div className="report-scroll__layout">
        <aside className="report-scroll__toc" aria-label={t("reportScroll.tocLabel")}>
          {Object.entries(tocGroups).map(([group, items]) => (
            <div key={group} className="report-scroll__toc-group">
              {group !== "_" && (
                <div className="report-scroll__toc-group-label">{group}</div>
              )}
              <ul className="report-scroll__toc-list">
                {items.map((s) => (
                  <li key={s.id}>
                    <a
                      href={`#${s.id}`}
                      className={`report-scroll__toc-link${activeId === s.id ? " report-scroll__toc-link--active" : ""}`}
                    >
                      {s.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </aside>
        <main className="report-scroll__main">
          {sections.map((s) => (
            <section
              key={s.id}
              id={s.id}
              className={`report-scroll__section${s.pageBreak ? " report-scroll__section--page-break" : ""}`}
            >
              {s.content}
            </section>
          ))}
        </main>
      </div>
    </div>
  );
}
