/**
 * DashboardInsights
 * -------------------
 * Two-part AI-driven card on the Dashboard:
 *
 *   1. "What are you focused on right now?" — monthly priority re-prompt.
 *      If the researcher hasn't updated their priority in 30+ days (or never
 *      set one), we show an input field. Otherwise we show a tiny "refresh"
 *      affordance so they can update it without breaking flow.
 *
 *   2. "Studies that fit your company" — recommended templates, scored
 *      against the company's onboarding profile (goals, product stage,
 *      customer type). Each card shows *why* it matched ("Right for
 *      growth-stage teams", "Matches your goal: retention") so the
 *      suggestion feels earned, not random.
 *
 * Both sections are silent if there's nothing to say — the priority prompt
 * only appears when it's due, and the recommendations section degrades to
 * a plain "popular starting points" header when the company has no profile
 * to match on.
 *
 * This component is the entire payoff of the `goals_classification`,
 * `product_stage`, and `customer_type` fields we've been collecting at
 * onboarding: before this, they were written once and never read. Now
 * they drive personalised copy that every researcher sees on every visit.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  getRecommendedStudies,
  type RecommendedStudy,
} from "../api/research";
import { updateCurrentPriority } from "../api/auth";
import type { CompanyResponse } from "../api/auth";

interface Props {
  /** Current company (from /auth/me) so we can show priority + re-prompt cadence. */
  me: CompanyResponse | null;
  /** Called after the priority is saved so the parent can update its state. */
  onPriorityUpdated?: (updated: CompanyResponse) => void;
}

/** A priority that's older than this many days is considered stale. */
const PRIORITY_STALE_DAYS = 30;

export default function DashboardInsights({ me, onPriorityUpdated }: Props) {
  const { t } = useTranslation(["dashboard", "common"]);
  const navigate = useNavigate();

  const [recommendations, setRecommendations] = useState<RecommendedStudy[]>([]);
  const [personalised, setPersonalised] = useState(false);
  const [loadingRecs, setLoadingRecs] = useState(true);

  const [priorityDraft, setPriorityDraft] = useState("");
  const [priorityEditing, setPriorityEditing] = useState(false);
  const [priorityBusy, setPriorityBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadingRecs(true);
    getRecommendedStudies(3)
      .then((r) => {
        if (cancelled) return;
        setRecommendations(r.recommendations || []);
        setPersonalised(!!r.personalised);
      })
      .catch(() => {
        if (cancelled) return;
        setRecommendations([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingRecs(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Sync draft with server value whenever `me` changes.
  useEffect(() => {
    setPriorityDraft((me?.current_priority || "").slice(0, 280));
  }, [me?.current_priority]);

  // "Is the priority stale or never set?" drives whether we show the prompt
  // automatically or keep it collapsed behind an edit affordance.
  const priorityAgeDays: number | null = (() => {
    if (!me?.current_priority_updated_at) return null;
    const ms = Date.now() - new Date(me.current_priority_updated_at).getTime();
    return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
  })();
  const priorityDue =
    !me?.current_priority ||
    priorityAgeDays === null ||
    priorityAgeDays >= PRIORITY_STALE_DAYS;

  async function savePriority() {
    setPriorityBusy(true);
    try {
      const updated = await updateCurrentPriority(priorityDraft.trim() || null);
      onPriorityUpdated?.(updated);
      setPriorityEditing(false);
    } catch {
      // interceptor handles toast
    } finally {
      setPriorityBusy(false);
    }
  }

  function openRecommendedStudy(r: RecommendedStudy) {
    // Reuse the existing wizard — it already accepts ?template=<id> to
    // pre-populate brief, objective, and questions in a single shot.
    navigate(`/projects/new?template=${encodeURIComponent(r.id)}`);
  }

  // Hide the whole card only if we have literally nothing useful to show.
  const showPriorityBlock = !!me && (priorityEditing || priorityDue || !!me.current_priority);
  const hasRecommendations = recommendations.length > 0 || loadingRecs;
  if (!showPriorityBlock && !hasRecommendations) return null;

  return (
    <section
      className="dashboard-insights"
      style={{
        // Use the canonical design-system tokens from index.css. The older
        // inline fallbacks (--surface-raised / --border / --muted) don't
        // exist in the theme so they were silently falling through to the
        // literal hex — and on macOS/iOS with prefers-color-scheme: dark,
        // native form controls rendered against a dark background even
        // though the rest of the page stayed light. Pinning the
        // color-scheme below plus using real tokens keeps the whole card
        // coherent regardless of OS theme.
        background: "var(--bg-surface)",
        color: "var(--text-primary)",
        border: "1px solid var(--border-default)",
        borderRadius: 12,
        padding: 20,
        marginBottom: 20,
        display: "flex",
        flexDirection: "column",
        gap: 20,
        colorScheme: "light",
      }}
    >
      {/* ── Priority prompt ───────────────────────────────────────────── */}
      {showPriorityBlock && (
        <div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>
              {t("insights.priorityTitle", "What are you focused on right now?")}
            </h2>
            {priorityAgeDays !== null && priorityAgeDays < PRIORITY_STALE_DAYS && (
              <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                {t("insights.priorityUpdatedAgo", {
                  defaultValue: "Updated {{count}} day(s) ago",
                  count: priorityAgeDays,
                })}
              </span>
            )}
          </div>

          {priorityEditing || priorityDue ? (
            <div style={{ marginTop: 8 }}>
              <textarea
                value={priorityDraft}
                maxLength={280}
                rows={2}
                onChange={(e) => setPriorityDraft(e.target.value)}
                placeholder={t(
                  "insights.priorityPlaceholder",
                  "e.g. Understand why power users stop upgrading after 6 months"
                )}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: 8,
                  border: "1px solid var(--border-default)",
                  background: "var(--bg-surface)",
                  color: "var(--text-primary)",
                  fontSize: 14,
                  fontFamily: "inherit",
                  resize: "vertical",
                  minHeight: 44,
                  // Prevent Safari/iOS from inverting the control when the
                  // user has OS-level dark mode on — the rest of the card
                  // stays light so the control should too.
                  colorScheme: "light",
                }}
              />
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: 6,
                  gap: 8,
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  {t("insights.priorityHint", "A short sentence so we can suggest research that moves your needle.")}
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  {priorityEditing && (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        setPriorityEditing(false);
                        setPriorityDraft(me?.current_priority || "");
                      }}
                      disabled={priorityBusy}
                    >
                      {t("common:cancel", "Cancel")}
                    </button>
                  )}
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={savePriority}
                    disabled={priorityBusy}
                  >
                    {priorityBusy
                      ? t("common:saving", "Saving…")
                      : t("insights.prioritySave", "Save priority")}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div
              style={{
                marginTop: 6,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <p
                style={{
                  margin: 0,
                  fontSize: 14,
                  color: "var(--text-primary)",
                  flex: 1,
                  minWidth: 200,
                }}
              >
                "{me?.current_priority}"
              </p>
              <button
                className="btn-inline"
                onClick={() => setPriorityEditing(true)}
                style={{ fontSize: 13 }}
              >
                {t("insights.priorityEdit", "Update")}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Recommended studies ──────────────────────────────────────── */}
      {hasRecommendations && (
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              marginBottom: 10,
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <h2 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>
              {personalised
                ? t("insights.recsTitlePersonalised", "Studies that fit your company")
                : t("insights.recsTitleGeneric", "Popular starting points")}
            </h2>
            {personalised && (
              <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                {t("insights.recsSubtitle", "Based on what you told us at signup")}
              </span>
            )}
          </div>

          {loadingRecs ? (
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  style={{
                    flex: "1 1 220px",
                    minHeight: 120,
                    borderRadius: 8,
                    background: "var(--bg-sunken)",
                  }}
                />
              ))}
            </div>
          ) : recommendations.length === 0 ? (
            <p style={{ fontSize: 13, color: "var(--text-tertiary)", margin: 0 }}>
              {t("insights.recsEmpty", "We'll recommend studies here once your profile is set up.")}
            </p>
          ) : (
            <div
              className="dashboard-insights-grid"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: 12,
              }}
            >
              {recommendations.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => openRecommendedStudy(r)}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-start",
                    gap: 8,
                    padding: "14px 14px 12px",
                    borderRadius: 8,
                    border: "1px solid var(--border-default)",
                    background: "var(--bg-surface)",
                    color: "var(--text-primary)",
                    textAlign: "left",
                    cursor: "pointer",
                    minHeight: 44,
                    transition: "border-color .15s, transform .15s",
                    font: "inherit",
                    colorScheme: "light",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "var(--primary)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--border-default)";
                  }}
                >
                  <span style={{ fontSize: 20 }} aria-hidden="true">
                    {r.icon}
                  </span>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{r.name}</span>
                  <span
                    style={{
                      fontSize: 12,
                      color: "var(--text-tertiary)",
                      lineHeight: 1.4,
                    }}
                  >
                    {r.description}
                  </span>
                  {r.reasons.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 4,
                        marginTop: 4,
                      }}
                    >
                      {r.reasons.map((reason) => (
                        <span
                          key={reason}
                          style={{
                            fontSize: 11,
                            padding: "2px 8px",
                            borderRadius: 999,
                            background: "var(--primary-light)",
                            color: "var(--primary)",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {reason}
                        </span>
                      ))}
                    </div>
                  )}
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--text-tertiary)",
                      marginTop: "auto",
                    }}
                  >
                    {r.question_count} questions · {r.duration_minutes} min
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
