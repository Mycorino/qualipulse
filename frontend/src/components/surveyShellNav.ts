import type { InstrumentSection } from "./InstrumentSubNav";
import type { InstrumentStatusTone } from "./InstrumentShell";

/**
 * Shared sub-nav config for the survey instrument pages.
 *
 * A survey's three views — the question builder, the results dashboard,
 * and the respondent preview — are separate routes, but they read as one
 * instrument: the same InstrumentShell with this segmented sub-nav.
 */
export const SURVEY_SECTIONS: InstrumentSection[] = [
  { key: "build", label: "Build" },
  { key: "results", label: "Results" },
  { key: "preview", label: "Preview" },
];

export function surveySectionPath(key: string, surveyId: string): string {
  if (key === "results") return `/surveys/${surveyId}/dashboard`;
  if (key === "preview") return `/surveys/${surveyId}/preview`;
  return `/surveys/${surveyId}/edit`;
}

/** Maps a survey status to an InstrumentShell status pill. */
export function surveyStatusPill(
  status: string,
): { label: string; tone: InstrumentStatusTone } {
  if (status === "live") return { label: "Live", tone: "live" };
  if (status === "closed") return { label: "Closed", tone: "closed" };
  return { label: "Draft", tone: "draft" };
}
