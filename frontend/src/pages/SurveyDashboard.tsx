import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { QuestionAnalytics, SurveyDashboard, getDashboard } from "../api/surveys";
import { ChartCard } from "../components/ChartCard";
import { DashboardShell, DashboardStrip } from "../components/DashboardShell";
import { MethodologyBox, SmallNWarning } from "../components/MethodologyBox";

/**
 * SurveyDashboard — `/surveys/:id/dashboard`.
 *
 * Wires the Sprint 1 design-system primitives (DashboardShell,
 * DashboardStrip, ChartCard, MethodologyBox) to the Sprint 6 schema +
 * Sprint 8 analytics endpoint. One ChartCard per question; n<30
 * segments render counts via Wilson-CI-aware ChartCard's `minN` prop.
 *
 * Compare/segments and AI clustering are deliberately out of scope
 * (Sprint 10 + 13). What ships here is the single-survey,
 * single-segment view that proves the methodology contract.
 */
export default function SurveyDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<SurveyDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getDashboard(id)
      .then(setData)
      .catch(() => setError("Could not load dashboard"));
  }, [id]);

  if (error) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">Loading…</p>
      </div>
    );
  }

  return (
    <div style={{ background: "var(--bg-base)", minHeight: "100vh" }}>
      <header
        style={{
          padding: "var(--space-3) var(--space-5)",
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border-default)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-4)",
        }}
      >
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => navigate(`/surveys/${id}/edit`)}
        >
          ← Editor
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: "var(--text-eyebrow)", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
            Dashboard · {data.role.toUpperCase()}
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "var(--text-xl)", letterSpacing: "-0.015em", margin: 0 }}>
            {data.name}
          </h1>
        </div>
      </header>

      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "var(--space-6) var(--space-5)" }}>
        <MethodologyBox
          fields={[
            {
              label: "Sample size",
              value: `n=${data.n_completed} completers${data.n_started > data.n_completed ? ` · ${data.n_started - data.n_completed} partial` : ""}`,
            },
            {
              label: "Fielding window",
              value: data.fielding_started_at
                ? `${formatDate(data.fielding_started_at)}${data.fielding_ended_at ? ` – ${formatDate(data.fielding_ended_at)}` : ""}`
                : "—",
            },
            {
              label: "Completion rate",
              value:
                data.completion_rate_percentage !== null
                  ? `${Math.round(data.completion_rate_percentage)}%`
                  : `Below n=${data.min_n_threshold}`,
            },
            {
              label: "Status",
              value: data.status.toUpperCase(),
            },
          ]}
          note={
            data.n_started < data.min_n_threshold
              ? `Total responses below the n=${data.min_n_threshold} threshold for inference. Percentages are suppressed; counts are shown instead.`
              : "Wilson 95% confidence intervals on every proportion. Segment splits below n=" +
                String(data.min_n_threshold) +
                " are reported as counts only."
          }
        />

        <div style={{ marginTop: "var(--space-6)" }}>
          <DashboardShell sidebar={<QuestionNav questions={data.questions} />}>
            <DashboardStrip
              items={[
                { label: "Respondents", value: String(data.n_started) },
                {
                  label: "Completed",
                  value: String(data.n_completed),
                  delta:
                    data.completion_rate_percentage !== null
                      ? `${Math.round(data.completion_rate_percentage)}% completion`
                      : "n too small to compute",
                  deltaTone:
                    data.completion_rate_percentage !== null && data.completion_rate_percentage >= 80
                      ? "positive"
                      : "neutral",
                },
                { label: "Questions", value: String(data.questions.length) },
              ]}
            />

            {data.questions.length === 0 ? (
              <p className="quanti-showcase__section-meta">No questions yet. Add some in the editor.</p>
            ) : (
              data.questions.map((q) => (
                <QuestionPanel key={q.question_id} q={q} minN={data.min_n_threshold} />
              ))
            )}
          </DashboardShell>
        </div>
      </div>
    </div>
  );
}

function QuestionNav({ questions }: { questions: QuestionAnalytics[] }) {
  return (
    <nav className="shell-nav" aria-label="Questions">
      <div className="shell-nav__group">
        <span className="shell-nav__group-label">Questions</span>
        {questions.map((q, i) => (
          <a key={q.question_id} href={`#q-${q.question_id}`} className="shell-nav__item">
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span style={{ flex: 1, marginLeft: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {q.prompt || "Untitled question"}
            </span>
            <span className="shell-nav__count">{q.n_answered}</span>
          </a>
        ))}
      </div>
    </nav>
  );
}

function QuestionPanel({ q, minN }: { q: QuestionAnalytics; minN: number }) {
  const eyebrow = `${typeLabel(q.type)} · Q${q.sort_order || ""}`.replace(/ \· Q$/, "");
  // ChartCard handles the small-n warning automatically when n_answered < minN.
  return (
    <div id={`q-${q.question_id}`} style={{ scrollMarginTop: "var(--space-6)" }}>
      <ChartCard
        eyebrow={eyebrow}
        takeaway={q.prompt || "Untitled question"}
        n={q.n_answered}
        minN={minN}
      >
        <BreakdownRenderer q={q} minN={minN} />
      </ChartCard>
    </div>
  );
}

function typeLabel(t: string): string {
  switch (t) {
    case "likert":
      return "Likert";
    case "nps":
      return "NPS";
    case "mc_single":
      return "Single choice";
    case "mc_multi":
      return "Multiple choice";
    case "open_text":
      return "Open text";
    case "short_text":
      return "Short text";
    default:
      return t;
  }
}

function BreakdownRenderer({ q, minN }: { q: QuestionAnalytics; minN: number }) {
  if (q.n_answered === 0) {
    return <p className="quanti-showcase__section-meta">No responses yet.</p>;
  }
  if (q.type === "likert" || q.type === "nps") {
    const histogram = (q.breakdown.histogram as Array<{
      bucket: number;
      count: number;
      percentage: number | null;
    }>) ?? [];
    const max = Math.max(1, ...histogram.map((h) => h.count));
    const isBelowMinN = q.n_answered < minN;
    return (
      <div>
        {q.type === "nps" && typeof q.breakdown.nps_score === "number" && (
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "var(--space-3)",
              marginBottom: "var(--space-3)",
            }}
          >
            <span
              className="tabular"
              style={{
                fontFamily: "var(--font-serif)",
                fontSize: "var(--text-2xl)",
                fontWeight: 700,
                color: "var(--brand-700)",
              }}
            >
              {(q.breakdown.nps_score as number) >= 0 ? "+" : ""}
              {q.breakdown.nps_score as number}
            </span>
            <span style={{ fontSize: "var(--text-xs)", letterSpacing: "0.08em", color: "var(--text-tertiary)", textTransform: "uppercase" }}>
              NPS score
            </span>
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
          {histogram.map((h) => (
            <div
              key={h.bucket}
              style={{ display: "grid", gridTemplateColumns: "32px 1fr 64px", gap: "var(--space-3)", alignItems: "center" }}
            >
              <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
                {h.bucket}
              </span>
              <div style={{ height: 10, background: "var(--bg-sunken)", borderRadius: 4, overflow: "hidden" }}>
                <div
                  style={{
                    width: `${(h.count / max) * 100}%`,
                    height: "100%",
                    background: q.type === "nps"
                      ? h.bucket <= 6
                        ? "var(--viz-negative)"
                        : h.bucket <= 8
                          ? "var(--viz-neutral)"
                          : "var(--viz-positive)"
                      : "var(--viz-positive)",
                  }}
                />
              </div>
              <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", textAlign: "right" }}>
                {isBelowMinN
                  ? `${h.count}/${q.n_answered}`
                  : h.percentage !== null
                    ? `${Math.round(h.percentage)}%`
                    : `${h.count}/${q.n_answered}`}
              </span>
            </div>
          ))}
        </div>
        {isBelowMinN && (
          <div style={{ marginTop: "var(--space-3)" }}>
            <SmallNWarning n={q.n_answered} minN={minN} />
          </div>
        )}
        {q.mean !== null && (
          <div className="tabular" style={{ marginTop: "var(--space-3)", fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
            Mean: {q.mean.toFixed(2)}
          </div>
        )}
      </div>
    );
  }
  if (q.type === "mc_single" || q.type === "mc_multi") {
    const choices = (q.breakdown.choices as Array<{
      choice_id: string;
      label: string;
      count: number;
      percentage: number | null;
    }>) ?? [];
    const max = Math.max(1, ...choices.map((c) => c.count));
    const isBelowMinN = q.n_answered < minN;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
        {choices.map((c) => (
          <div
            key={c.choice_id}
            style={{ display: "grid", gridTemplateColumns: "180px 1fr 64px", gap: "var(--space-3)", alignItems: "center" }}
          >
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.label}
            </span>
            <div style={{ height: 10, background: "var(--bg-sunken)", borderRadius: 4, overflow: "hidden" }}>
              <div style={{ width: `${(c.count / max) * 100}%`, height: "100%", background: "var(--viz-positive)" }} />
            </div>
            <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", textAlign: "right" }}>
              {isBelowMinN
                ? `${c.count}/${q.n_answered}`
                : c.percentage !== null
                  ? `${Math.round(c.percentage)}%`
                  : `${c.count}/${q.n_answered}`}
            </span>
          </div>
        ))}
        {isBelowMinN && (
          <div style={{ marginTop: "var(--space-3)" }}>
            <SmallNWarning n={q.n_answered} minN={minN} />
          </div>
        )}
      </div>
    );
  }
  if (q.type === "open_text" || q.type === "short_text") {
    const sample = (q.breakdown.sample as string[]) ?? [];
    const total = (q.breakdown.total_texts as number) ?? sample.length;
    return (
      <div>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {sample.slice(0, 5).map((text, i) => (
            <li
              key={i}
              style={{
                padding: "var(--space-2) var(--space-3)",
                background: "var(--bg-base)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
                fontFamily: "var(--font-serif)",
                fontStyle: "italic",
                fontSize: "var(--text-sm)",
                color: "var(--text-primary)",
                lineHeight: 1.5,
              }}
            >
              "{text}"
            </li>
          ))}
        </ul>
        <p style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", marginTop: "var(--space-2)" }}>
          Showing {Math.min(5, sample.length)} of {total} text responses. AI-clustered themes ship in Sprint 13.
        </p>
      </div>
    );
  }
  return null;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
