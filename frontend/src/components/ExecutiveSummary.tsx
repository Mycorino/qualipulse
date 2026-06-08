import { useTranslation } from "react-i18next";

/**
 * ExecutiveSummary — the standalone-argument scaffold.
 *
 * The ex-MBB perspective: the exec summary is where consultants earn their
 * fee, not the appendix. A senior reader should be able to read only this
 * and act. AI can draft the governing thoughts; the human researcher edits
 * the wording and order. Here we render the structure so the editor surface
 * (out of scope for the design system) has a target shape.
 *
 * Three governing thoughts is the recommended count: enough to cover a
 * thesis and two drivers, few enough to be remembered. We accept up to
 * five in the API but warn (in the editor, not here) when researchers add
 * a sixth.
 */

export interface GoverningThought {
  /** Action-title form, e.g. "Trust gaps cost us 30% of new users." */
  thesis: string;
  /** One-paragraph elaboration. Serif body. */
  elaboration: string;
  /** Optional reference back to a finding number. */
  findingRef?: string;
}

interface ExecutiveSummaryProps {
  /** Headline above the governing thoughts. Serif, display-size. */
  headline: string;
  /** Optional sub-headline / one-line context. */
  subheadline?: string;
  thoughts: GoverningThought[];
  /** Author block at the bottom — researcher name, role, study date. */
  author?: { name: string; role?: string; date: string };
}

export function ExecutiveSummary({
  headline,
  subheadline,
  thoughts,
  author,
}: ExecutiveSummaryProps) {
  const { t: tr } = useTranslation("study");
  return (
    <section className="exec-summary" aria-labelledby="exec-summary-headline">
      <div className="exec-summary__head">
        <div className="exec-summary__eyebrow">{tr("executiveSummary.eyebrow")}</div>
        <h2 id="exec-summary-headline" className="exec-summary__headline">
          {headline}
        </h2>
        {subheadline && <p className="exec-summary__subheadline">{subheadline}</p>}
      </div>
      <ol className="exec-summary__thoughts">
        {thoughts.map((t, i) => (
          <li key={i} className="exec-summary__thought">
            <div className="exec-summary__thought-num tabular">{String(i + 1).padStart(2, "0")}</div>
            <div className="exec-summary__thought-body">
              <h3 className="exec-summary__thought-thesis">{t.thesis}</h3>
              <p className="exec-summary__thought-elab">{t.elaboration}</p>
              {t.findingRef && (
                <a className="exec-summary__thought-ref" href={`#${t.findingRef.toLowerCase().replace(/\s+/g, "-")}`}>
                  {tr("executiveSummary.seeRef", { ref: t.findingRef })}
                </a>
              )}
            </div>
          </li>
        ))}
      </ol>
      {author && (
        <footer className="exec-summary__author">
          <span className="exec-summary__author-name">{author.name}</span>
          {author.role && <span className="exec-summary__author-role">{author.role}</span>}
          <span className="exec-summary__author-date tabular">{author.date}</span>
        </footer>
      )}
    </section>
  );
}
