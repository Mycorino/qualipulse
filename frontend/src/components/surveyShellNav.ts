import type { TFunction } from "i18next";

import type { InstrumentSection } from "./InstrumentSubNav";
import type { InstrumentStatusTone } from "./InstrumentShell";

/**
 * Shared sub-nav config for the survey instrument pages.
 *
 * A survey's three views — the question builder, the results dashboard,
 * and the respondent preview — are separate routes, but they read as one
 * instrument: the same InstrumentShell with this segmented sub-nav.
 *
 * Labels come from the `shell` namespace so they localize with the rest
 * of the chrome (any page's `t` can reach them via the `shell:` prefix).
 */
export function surveySections(t: TFunction): InstrumentSection[] {
  return [
    { key: "build", label: t("shell:instrument.sectionBuild") },
    { key: "results", label: t("shell:instrument.sectionResults") },
    { key: "preview", label: t("shell:instrument.sectionPreview") },
  ];
}

export function surveySectionPath(key: string, surveyId: string): string {
  if (key === "results") return `/surveys/${surveyId}/dashboard`;
  if (key === "preview") return `/surveys/${surveyId}/preview`;
  return `/surveys/${surveyId}/edit`;
}

/** Maps a survey status to an InstrumentShell status pill. */
export function surveyStatusPill(
  status: string,
  t: TFunction,
): { label: string; tone: InstrumentStatusTone } {
  if (status === "live")
    return { label: t("shell:instrument.statusLive"), tone: "live" };
  if (status === "closed")
    return { label: t("shell:instrument.statusClosed"), tone: "closed" };
  return { label: t("shell:instrument.statusDraft"), tone: "draft" };
}
