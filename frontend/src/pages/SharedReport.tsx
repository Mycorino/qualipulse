import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AnalysisReport, AttributedQuote } from "../api/projects";
import { Skeleton } from "../components/Skeleton";

interface SharedReportData {
  project_name: string | null;
  participant_count: number;
  generated_at: string | null;
  report: AnalysisReport | null;
}

export default function SharedReport() {
  const { token } = useParams<{ token: string }>();
  const { t } = useTranslation("analysis");
  const [data, setData] = useState<SharedReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetch(`/api/reports/${token}`)
      .then((r) => {
        if (!r.ok) throw new Error(t("sharedReport.notFound"));
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, t]);

  if (loading) {
    return (
      <div className="shared-report-page">
        <header className="shared-report-header">
          <div className="shared-report-header-inner">
            <div className="shared-report-brand">QualiPulse</div>
          </div>
        </header>
        <main className="shared-report-main">
          <div className="shared-report-title-block">
            <Skeleton height="32px" width="60%" />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <Skeleton height="22px" width="100px" />
              <Skeleton height="22px" width="120px" />
            </div>
          </div>
          <section className="shared-report-section">
            <Skeleton height="14px" width="100%" />
            <Skeleton height="14px" width="90%" />
            <Skeleton height="14px" width="70%" />
          </section>
          <section className="shared-report-section">
            <Skeleton height="22px" width="140px" />
            {[1, 2, 3].map((i) => (
              <div key={i} className="analysis-theme-card" style={{ marginTop: 16 }}>
                <Skeleton height="18px" width="50%" />
                <Skeleton height="14px" width="85%" />
                <Skeleton height="14px" width="60%" />
              </div>
            ))}
          </section>
        </main>
      </div>
    );
  }

  if (error || !data?.report) {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "100vh", gap: 12, color: "var(--text-secondary)" }}>
        <div style={{ fontSize: 40 }}>🔒</div>
        <p style={{ fontWeight: 600, fontSize: 18 }}>{t("sharedReport.reportUnavailable")}</p>
        <p style={{ fontSize: 14 }}>{error ?? t("sharedReport.linkRevoked")}</p>
      </div>
    );
  }

  const { report } = data;

  function renderQuote(q: AttributedQuote | string, idx: number) {
    if (typeof q === "string") {
      return <blockquote key={idx} className="analysis-quote">"{q}"</blockquote>;
    }
    return (
      <blockquote key={idx} className="analysis-quote">
        <div>"{q.text}"</div>
        {(q.participant_display_name || q.participant_identifier) && (
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4, fontWeight: 500 }}>
            — {q.participant_display_name || q.participant_identifier}
          </div>
        )}
      </blockquote>
    );
  }

  return (
    <div className="shared-report-page">
      {/* Header */}
      <header className="shared-report-header">
        <div className="shared-report-header-inner">
          <div className="shared-report-brand">QualiPulse</div>
          <div className="shared-report-meta">
            <span>{t("sharedReport.participant", { count: data.participant_count })}</span>
            {data.generated_at && (
              <span>{t("sharedReport.generatedOn", { date: new Date(data.generated_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) })}</span>
            )}
          </div>
        </div>
      </header>

      <main className="shared-report-main">
        {/* Title */}
        <div className="shared-report-title-block">
          <h1 className="shared-report-title">{data.project_name ?? t("sharedReport.researchReport")}</h1>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
            <span className="badge">{t("sharedReport.interviews", { count: report.participant_count })}</span>
            {report.confidence && (
              <span
                className="badge"
                title={t("sharedReport.confidenceTooltip")}
                aria-label={`${t("sharedReport.confidence", { level: report.confidence })} — ${t("sharedReport.confidenceTooltip")}`}
                style={{ cursor: "help" }}
              >
                {t("sharedReport.confidence", { level: report.confidence })}
              </span>
            )}
          </div>
        </div>

        {/* Summary */}
        <section className="shared-report-section">
          <div className="analysis-summary-box">
            <p style={{ fontSize: 15, lineHeight: 1.65 }}>{report.summary}</p>
          </div>
        </section>

        {/* Key Themes */}
        {report.themes?.length > 0 && (() => {
          const themeColors = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6", "#f97316", "#06b6d4", "#a855f7"];
          return (
            <section className="shared-report-section">
              <h2 className="shared-report-section-title">{t("sharedReport.keyThemes")} ({report.themes.length})</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                {report.themes.map((theme, i) => (
                  <div key={i} className="analysis-theme-card" style={{ borderLeft: `4px solid ${themeColors[i % themeColors.length]}` }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                      <span style={{ fontWeight: 700, fontSize: 15 }}>{theme.title}</span>
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        {theme.frequency && (
                          <span className="badge" style={{ fontSize: 11 }}>{theme.frequency}</span>
                        )}
                        {theme.quotes?.length > 0 && (
                          <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{theme.quotes.length} quote{theme.quotes.length !== 1 ? "s" : ""}</span>
                        )}
                      </div>
                    </div>
                    <p style={{ color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: theme.quotes?.length ? 12 : 0 }}>
                      {theme.summary}
                    </p>
                    {theme.quotes?.slice(0, 3).map((q, qi) => renderQuote(q, qi))}
                  </div>
                ))}
              </div>
            </section>
          );
        })()}

        {/* Jobs to Be Done */}
        {report.jobs_to_be_done?.length > 0 && (
          <section className="shared-report-section">
            <h2 className="shared-report-section-title">{t("sharedReport.jobsToBeDone")} ({report.jobs_to_be_done.length})</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {report.jobs_to_be_done.map((j, i) => (
                <div key={i} style={{ padding: "14px 16px", borderRadius: 8, background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderLeft: "4px solid #f59e0b" }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{j.job}</div>
                  <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>{j.insight}</div>
                  {j.frequency && <span className="badge" style={{ marginTop: 6, display: "inline-block", fontSize: 11 }}>{j.frequency}</span>}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Tensions */}
        {report.tensions?.length > 0 && (
          <section className="shared-report-section">
            <h2 className="shared-report-section-title">{t("sharedReport.tensionsAndContradictions")} ({report.tensions.length})</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {report.tensions.map((tn, i) => (
                <div key={i} style={{ padding: "12px 16px", borderRadius: 8, borderLeft: "4px solid #ef4444", background: "var(--bg-surface)" }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{tn.tension}</div>
                  <div style={{ color: "var(--text-secondary)", fontSize: 14 }}>{tn.detail}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Recommendations */}
        {report.recommendations?.length > 0 && (
          <section className="shared-report-section">
            <h2 className="shared-report-section-title">{t("sharedReport.recommendations")}</h2>
            <ol style={{ paddingLeft: 20, display: "flex", flexDirection: "column", gap: 8 }}>
              {report.recommendations.map((r, i) => (
                <li key={i} style={{ color: "var(--text-secondary)", lineHeight: 1.6 }}>{r}</li>
              ))}
            </ol>
          </section>
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", padding: "32px 0 64px", color: "var(--text-tertiary)", fontSize: 13 }}>
          {t("sharedReport.generatedBy")} <strong>QualiPulse</strong> · {t("sharedReport.tagline")}
        </div>
      </main>
    </div>
  );
}
