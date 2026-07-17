import { CSSProperties, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  StudySummary,
  fetchStudyReportHtml,
  getLatestAnalysis,
  listStudies,
} from "../api/studies";
import { SynthesisSummary, listSyntheses } from "../api/synthesis";
import { openHtmlDocument } from "../utils/openHtmlDocument";
import { DecisionMemoSection } from "../components/DecisionMemoSection";
import { HubShell } from "../components/HubShell";
import { useToast } from "../components/Toast";

/**
 * Reports — `/reports`, the library of every generated report document.
 *
 * This is not a launcher into studies: each row opens the finished report
 * itself (the print-ready HTML the study/analysis produced), the same way
 * decision memos open. Two report families live at the workspace level:
 *
 *   • Study reports  — the mixed-methods "Decision report" each Study
 *                      produces once its analysis is ready.
 *   • Decision memos — cross-study syntheses (DecisionMemoSection).
 *
 * The page wears the report's own ink. Both families are the mixed/decision
 * family, which the exported documents render in bordeaux on warm paper
 * (services/report_export.py → _PALETTES["mixed"] + _BASE_DOC_CSS). Mirroring
 * those tokens here makes each row read as the document it opens.
 */

// Mirror of report_export.py _PALETTES["mixed"] + _BASE_DOC_CSS. Keep in sync.
export const REPORT_INK = {
  accent: "#7c2434", // bordeaux — the board-document ink
  tint: "#f8eef0",
  deep: "#4d1420",
  paper: "#fcfcfa",
  ink: "#17201b",
  ink2: "#4c5852",
  ink3: "#7a847e",
  rule: "#dfe5e0",
} as const;

/** A report row styled as the document it opens: warm paper, a bordeaux
 *  spine down the left edge, the report rule for its border. */
export const reportRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "var(--space-4)",
  flexWrap: "wrap",
  textAlign: "left",
  background: REPORT_INK.paper,
  border: `1px solid ${REPORT_INK.rule}`,
  borderLeft: `3px solid ${REPORT_INK.accent}`,
  borderRadius: "var(--radius-md)",
  padding: "var(--space-3) var(--space-4)",
  color: REPORT_INK.ink,
};

function ReportBadge({ label }: { label: string }) {
  return (
    <span
      style={{
        fontSize: "var(--text-eyebrow)",
        fontWeight: 600,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: REPORT_INK.accent,
        background: REPORT_INK.tint,
        borderRadius: 999,
        padding: "3px 10px",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

/** Section eyebrow in the report's bordeaux ink (overrides the app-blue
 *  eyebrow so the whole page reads as one document family). */
function ReportEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: "var(--text-eyebrow)",
        fontWeight: 600,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: REPORT_INK.accent,
      }}
    >
      {children}
    </div>
  );
}

export default function Reports() {
  const { t } = useTranslation("dashboard");
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [memos, setMemos] = useState<SynthesisSummary[] | null>(null);
  // Which study report is currently being fetched (prevents double-open).
  const [openingId, setOpeningId] = useState<string | null>(null);
  // ?newMemo=1 (from the workspace NBA / studies sidecar) opens the create
  // modal in DecisionMemoSection via its openSignal prop.
  const [memoOpenSignal, setMemoOpenSignal] = useState(0);

  useEffect(() => {
    listStudies()
      .then(setStudies)
      .catch(() => toast(t("studyList.loadError"), "error"));
  }, [toast, t]);

  const refreshMemos = () => {
    listSyntheses()
      .then(setMemos)
      .catch(() => toast(t("decisionMemos.loadError"), "error"));
  };
  useEffect(refreshMemos, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (searchParams.get("newMemo") === "1") {
      setMemoOpenSignal((n) => n + 1);
      setSearchParams(
        (sp) => {
          const next = new URLSearchParams(sp);
          next.delete("newMemo");
          return next;
        },
        { replace: true },
      );
    }
  }, [searchParams, setSearchParams]);

  const activeStudies = useMemo(
    () => (studies ?? []).filter((s) => !s.archived_at),
    [studies],
  );

  // A report only shows here once it actually exists — this is a library of
  // generated documents, not a to-do list of studies to open.
  const studyReports = useMemo(
    () => activeStudies.filter((s) => s.has_report),
    [activeStudies],
  );

  const readyMemoCount = useMemo(
    () => (memos ?? []).filter((m) => m.status === "ready").length,
    [memos],
  );
  const reportsCount = studyReports.length + readyMemoCount;

  // Open the study's finished report document directly in a new tab —
  // openHtmlDocument claims the tab synchronously (mobile-safe), then the
  // callback resolves the latest analysis and fetches its report.html.
  const openStudyReport = async (s: StudySummary) => {
    setOpeningId(s.id);
    try {
      await openHtmlDocument(async () => {
        const analysis = await getLatestAnalysis(s.id);
        if (!analysis || analysis.status !== "ready") {
          throw new Error("report_not_ready");
        }
        return fetchStudyReportHtml(s.id, analysis.id);
      }, `study-report-${s.id.slice(0, 8)}.html`);
    } catch {
      toast(t("reports.studyReports.openError"), "error");
    } finally {
      setOpeningId(null);
    }
  };

  const evidenceLabel = (s: StudySummary) => {
    const parts: string[] = [];
    if (s.completed_interview_count > 0) {
      parts.push(t("hub.evidence.interviews", { count: s.completed_interview_count }));
    }
    if (s.completed_response_count > 0) {
      parts.push(t("hub.evidence.responses", { count: s.completed_response_count }));
    }
    return parts.join(" · ") || "—";
  };

  const hasAnyReport = studyReports.length > 0 || (memos ?? []).length > 0;

  return (
    <HubShell active="reports" studies={studies} memoCount={reportsCount} studyCount={studies?.length}>
      <div className="hub-canvas">
        <header className="hub-head">
          <div className="hub-head__text">
            <ReportEyebrow>{t("reports.eyebrow")}</ReportEyebrow>
            <h1 className="hub-head__title">{t("reports.title")}</h1>
            <p className="hub-head__sub">{t("reports.sub")}</p>
          </div>
        </header>

        {studies === null ? (
          <div className="hub-table-wrap" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="hub-skel-row">
                <span className="hub-skel" style={{ width: 70, height: 18, borderRadius: 999 }} />
                <span className="hub-skel" style={{ width: "42%", height: 12 }} />
                <span className="hub-skel" style={{ width: 80, height: 10 }} />
              </div>
            ))}
          </div>
        ) : !hasAnyReport ? (
          <div
            style={{
              background: REPORT_INK.paper,
              border: `1px dashed ${REPORT_INK.rule}`,
              borderRadius: "var(--radius-md)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            <p style={{ color: REPORT_INK.ink2, maxWidth: 520, margin: "0 auto", lineHeight: 1.5 }}>
              {t("reports.emptyAll")}
            </p>
          </div>
        ) : (
          <>
            {/* ── Study reports ─────────────────────────────────────── */}
            {studyReports.length > 0 && (
              <section className="quanti-showcase__section">
                <div style={{ marginBottom: "var(--space-4)" }}>
                  <ReportEyebrow>{t("reports.studyReports.eyebrow")}</ReportEyebrow>
                  <h2 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0, color: REPORT_INK.ink }}>
                    {t("reports.studyReports.title")}
                  </h2>
                  <p style={{ color: REPORT_INK.ink3, fontSize: "var(--text-sm)", margin: "4px 0 0" }}>
                    {t("reports.studyReports.sub")}
                  </p>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                  {studyReports.map((s) => {
                    const opening = openingId === s.id;
                    return (
                      <button
                        key={s.id}
                        type="button"
                        disabled={opening}
                        onClick={() => openStudyReport(s)}
                        style={{ ...reportRowStyle, cursor: opening ? "progress" : "pointer" }}
                      >
                        <ReportBadge label={t("reports.studyReports.badge")} />
                        <div style={{ flex: 1, minWidth: 220 }}>
                          <div style={{ fontWeight: 600 }}>
                            {s.name}
                            {s.is_demo && <span className="hub-demo-badge">{t("hub.demoBadge")}</span>}
                          </div>
                          <div style={{ fontSize: "var(--text-xs)", color: REPORT_INK.ink3 }}>
                            {evidenceLabel(s)}
                          </div>
                        </div>
                        <span
                          style={{
                            fontSize: "var(--text-sm)",
                            fontWeight: 600,
                            color: REPORT_INK.accent,
                            whiteSpace: "nowrap",
                          }}
                        >
                          <span aria-hidden="true">📄 </span>
                          {opening ? t("reports.studyReports.opening") : t("reports.studyReports.open")}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            )}

            {/* ── Decision memos ────────────────────────────────────── */}
            {/* DecisionMemoSection self-guards: renders create + list at ≥2
                studies, returns null below that. It wears the same report
                ink (bordeaux spine, warm paper) via the `ink` prop. */}
            <DecisionMemoSection
              studies={activeStudies}
              memos={memos}
              onRefresh={refreshMemos}
              openSignal={memoOpenSignal}
              ink={{ ...REPORT_INK, rowStyle: reportRowStyle }}
            />
          </>
        )}
      </div>
    </HubShell>
  );
}
