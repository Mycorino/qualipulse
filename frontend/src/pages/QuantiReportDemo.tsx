import { ChartCard } from "../components/ChartCard";
import { VerbatimCard } from "../components/VerbatimCard";
import { MethodologyBox } from "../components/MethodologyBox";
import { StatHero } from "../components/StatHero";
import { FindingCard } from "../components/FindingCard";
import { Segment2x2 } from "../components/Segment2x2";
import { CrossTabTable } from "../components/CrossTabTable";
import { PrioritizationMatrix } from "../components/PrioritizationMatrix";
import { ExecutiveSummary } from "../components/ExecutiveSummary";
import { ReportScroll } from "../components/ReportScroll";

/**
 * QuantiReportDemo — the full mixed-methods report rendered end-to-end.
 *
 * Sticches every Sprint 1-5 component into a single realistic study
 * (a hypothetical pricing-and-onboarding study). Reachable at
 * /design-system/quanti/report. Demonstrates the scrollytelling layout,
 * sticky TOC, and print stylesheet — exporting via the browser's print
 * dialog produces a clean A4 PDF.
 */

const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";
const A1 = `${SILENT_WAV}#a-1`;
const A2 = `${SILENT_WAV}#a-2`;
const A3 = `${SILENT_WAV}#a-3`;
const A4 = `${SILENT_WAV}#a-4`;

export default function QuantiReportDemo() {
  return (
    <ReportScroll
      cover={
        <div style={{ maxWidth: "980px", margin: "0 auto" }}>
          <div style={{ fontSize: "var(--text-eyebrow)", fontWeight: "var(--weight-semibold)", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--surface-emphasis-text-soft)", marginBottom: "var(--space-3)" }}>
            Mixed-methods report · Q2 2026
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "3.6rem", fontWeight: 700, letterSpacing: "-0.025em", lineHeight: 1.05, marginBottom: "var(--space-5)", maxWidth: "20ch" }}>
            Why new users churn — pricing, trust, and the checkout cliff.
          </h1>
          <p style={{ fontSize: "var(--text-lg)", color: "var(--surface-emphasis-text-soft)", lineHeight: 1.5, maxWidth: "60ch", marginBottom: "var(--space-8)" }}>
            A study of 247 first-month users combining a structured survey with 18 follow-up
            interviews — to size the churn drivers we suspected and surface the ones we didn't.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-6)", color: "var(--surface-emphasis-text-soft)", fontSize: "var(--text-sm)" }}>
            <div><span style={{ display: "block", fontSize: "var(--text-eyebrow)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--surface-emphasis-text-muted)", marginBottom: "4px" }}>Sample</span><span className="tabular">n=247 + 18 interviews</span></div>
            <div><span style={{ display: "block", fontSize: "var(--text-eyebrow)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--surface-emphasis-text-muted)", marginBottom: "4px" }}>Field window</span><span className="tabular">Apr 14 – May 02, 2026</span></div>
            <div><span style={{ display: "block", fontSize: "var(--text-eyebrow)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--surface-emphasis-text-muted)", marginBottom: "4px" }}>Author</span>Camille Dubois, Sr. Researcher</div>
          </div>
        </div>
      }
      sections={[
        {
          id: "methodology",
          label: "Methodology",
          group: "Context",
          content: (
            <MethodologyBox
              fields={[
                { label: "Sample size", value: "n=247 completers" },
                { label: "Fielding window", value: "Apr 14 – May 02, 2026" },
                { label: "Method", value: "Mixed (survey + 18 interviews)" },
                { label: "Segments", value: "Role · Company size · Region" },
                { label: "Margin of error", value: "±5.4pp at 95% confidence" },
                { label: "Sampling", value: "Stratified panel quota" },
              ]}
              note="Weighted to match B2B SaaS PM / researcher composition by company size and region. Unweighted counts shown alongside weighted percentages throughout. Segment splits below n=30 are reported as counts only."
            />
          ),
        },
        {
          id: "executive-summary",
          label: "Executive summary",
          group: "Context",
          pageBreak: true,
          content: (
            <ExecutiveSummary
              headline="Three things — checkout fixes the trust gap, the AI report drives renewal, designers may be a separate ICP."
              subheadline="If we ship one change before EOQ, it's the checkout. The other two are signals to act on, not commitments."
              thoughts={[
                {
                  thesis: "Trust gaps cost 30% of new users — and the cause is the checkout, not the pricing page.",
                  elaboration:
                    "Detractors who churned consistently flagged the checkout as opaque, even when their stated objection was price. The pricing page tested clean across all segments; the checkout did not. Reordering the line items to mirror pricing recovers an estimated 18-22% of first-month churn.",
                  findingRef: "Finding 03",
                },
                {
                  thesis: "Promoters renew because of the AI synthesis report — not because of the interview tool.",
                  elaboration:
                    "When asked what they'd cancel last, promoters named the report 2× more often than the interview surface. Lead the marketing site with the report; the interviews are plumbing that gets paid for via the analysis.",
                  findingRef: "Finding 04",
                },
                {
                  thesis: "Designers may be a separate ICP — but the sample is too thin to commit.",
                  elaboration:
                    "Designers (n=12) reported a different primary use case (concept testing, not customer research). The signal is interesting but not yet bankable; we recommend a 30-respondent designer-only survey before any product work.",
                  findingRef: "Finding 05",
                },
              ]}
              author={{ name: "Camille Dubois", role: "Sr. Researcher", date: "May 06, 2026" }}
            />
          ),
        },
        {
          id: "headline-stat",
          label: "Headline metric",
          group: "Findings",
          content: (
            <StatHero
              eyebrow="Onboarding · Q2"
              stat="73%"
              description="of new users abandon the onboarding flow before reaching the third step."
              meta="n=247 · 95% CI ±5.4pp"
              quote={{
                text: "I almost cancelled last week. The pricing page never explained what 'team' actually meant — I was paying for seats I didn't need.",
                audioSrc: A1,
                segments: ["PM", "31–40", "United States"],
              }}
            />
          ),
        },
        {
          id: "finding-03",
          label: "Finding 03 — Checkout cliff",
          group: "Findings",
          pageBreak: true,
          content: (
            <FindingCard
              index="Finding 03 of 07"
              actionTitle="Trust gaps cost us 30% of new users — driven by checkout, not pricing."
              context="Detractors who churned in their first month consistently flagged the checkout as opaque — even when their stated objection was price. The pricing page tested clean; the checkout did not."
              evidence={
                <ChartCard
                  eyebrow="Likert · Q3 — Checkout clarity"
                  takeaway="Detractors rate checkout 3× more confusing than promoters."
                  n={247}
                  completionRate={92}
                  ciHalfWidth={5.4}
                >
                  <DivergingLikert />
                </ChartCard>
              }
              verbatims={
                <>
                  <VerbatimCard
                    quote="The pricing page made sense. The checkout asked for things I didn't expect — that's where I bailed."
                    audioSrc={A2}
                    segments={["PM", "31–40", "United States"]}
                  />
                  <VerbatimCard
                    quote="I genuinely thought I was being charged twice. The line items don't match what's on the pricing page."
                    audioSrc={A3}
                    segments={["Designer", "26–30", "Canada"]}
                    compact
                  />
                </>
              }
              implication="Reorder the checkout to mirror the pricing page line-by-line. The pricing copy is the trust-builder; the checkout currently undoes that work in 30 seconds."
              sampleNote="n=247 survey · 18 follow-up interviews · 4 segments"
              confidence="strong"
            />
          ),
        },
        {
          id: "finding-04",
          label: "Finding 04 — AI as the renewal driver",
          group: "Findings",
          pageBreak: true,
          content: (
            <FindingCard
              index="Finding 04 of 07"
              actionTitle="Promoters cite the AI synthesis as their reason to renew — not the interview tool."
              evidence={
                <ChartCard
                  eyebrow="Multiple choice · Q5"
                  takeaway="The AI report is the most-cited renewal reason, twice as often as the interview tool itself."
                  n={89}
                  completionRate={94}
                  ciHalfWidth={6.2}
                >
                  <HBars
                    bars={[
                      { label: "AI synthesis report", value: 71 },
                      { label: "Adaptive interviews", value: 38 },
                      { label: "Sharing & exports", value: 26 },
                      { label: "Recruiting panel", value: 17 },
                    ]}
                  />
                </ChartCard>
              }
              verbatims={
                <VerbatimCard
                  quote="If you took away the analysis I'd cancel. The interviews are nice but I can do those anywhere."
                  audioSrc={A4}
                  segments={["Researcher", "31–40", "United Kingdom"]}
                />
              }
              implication="Lead the marketing site with the report, not the interview. The interview is plumbing; the report is what gets paid for."
              sampleNote="n=89 promoters · 6 renewal interviews"
              confidence="supported"
              layout="evidence-left"
            />
          ),
        },
        {
          id: "segment-matrix",
          label: "Segment landscape",
          group: "Segmentation",
          pageBreak: true,
          content: (
            <Segment2x2
              xAxisLabel="Solution sophistication →"
              yAxisLabel="Need intensity →"
              quadrants={[
                {
                  label: "High need · Low solution",
                  quote: "I gave up trying to make our existing tool do this. I just need it to work.",
                  segment: "PM · 31–40",
                  n: 89,
                },
                {
                  label: "High need · High solution",
                  quote: "We switched to a workaround last year. We'd switch back if you fixed the export.",
                  segment: "Founder · 41–50",
                  n: 142,
                },
                {
                  label: "Low need · Low solution",
                  quote: "Honestly, this isn't a daily problem for me. Maybe quarterly.",
                  segment: "Designer · 26–30",
                  n: 38,
                },
                {
                  label: "Low need · High solution",
                  quote: "Nice to have but our team uses Notion docs and that covers 80% of it.",
                  segment: "Engineer · 31–40",
                  n: 18,
                },
              ]}
            />
          ),
        },
        {
          id: "cross-tab",
          label: "Themes by segment",
          group: "Segmentation",
          content: (
            <CrossTabTable
              columns={["PMs", "Researchers", "Designers", "Engineers", "Founders"]}
              columnNs={[89, 64, 12, 38, 14]}
              rows={[
                { label: "Onboarding friction", values: [62, 48, 67, 31, 71], counts: [55, 31, 8, 12, 10] },
                { label: "Pricing clarity", values: [54, 39, 58, 24, 64], counts: [48, 25, 7, 9, 9] },
                { label: "Export quality", values: [38, 71, 33, 18, 28], counts: [34, 45, 4, 7, 4] },
                { label: "AI accuracy", values: [42, 56, 42, 21, 35], counts: [37, 36, 5, 8, 5] },
                { label: "Mobile parity", values: [18, 12, 17, 14, 21], counts: [16, 8, 2, 5, 3] },
              ]}
              note="Designer and Founder columns show counts because n<30 falls below the inference threshold. Themes are AI-clustered from open-text responses."
            />
          ),
        },
        {
          id: "prioritization",
          label: "What to do next",
          group: "Action",
          pageBreak: true,
          content: (
            <PrioritizationMatrix
              recommendations={[
                { id: "1", title: "Mirror checkout line items to pricing page", impact: 88, feasibility: 78, effort: "quick", findingRef: "Finding 03" },
                { id: "2", title: "Lead the homepage with the AI report demo", impact: 72, feasibility: 82, effort: "medium", findingRef: "Finding 04" },
                { id: "3", title: "Add inline 'team plan' explainer in signup", impact: 64, feasibility: 90, effort: "quick", findingRef: "Finding 03" },
                { id: "4", title: "Designer-targeted survey wave (n=30)", impact: 52, feasibility: 70, effort: "medium", findingRef: "Finding 05" },
                { id: "5", title: "Rebuild export pipeline for Researchers", impact: 78, feasibility: 32, effort: "large", findingRef: "Finding 04" },
                { id: "6", title: "Mobile parity for transcript review", impact: 42, feasibility: 28, effort: "large", findingRef: "Finding 06" },
                { id: "7", title: "Renewal-trigger AI report email digest", impact: 58, feasibility: 64, effort: "medium", findingRef: "Finding 04" },
              ]}
            />
          ),
        },
      ]}
    />
  );
}

/* ──────────────────────────────────────────────────────────────────
   Demo charts. Same as in QuantiShowcase but local so the report
   page is self-contained.
   ────────────────────────────────────────────────────────────────── */

function DivergingLikert() {
  const segs = [
    { pct: 12, color: "var(--viz-div-strong-neg)", side: "neg" as const },
    { pct: 18, color: "var(--viz-div-neg)", side: "neg" as const },
    { pct: 22, color: "var(--viz-div-mid)", side: "mid" as const },
    { pct: 28, color: "var(--viz-div-pos)", side: "pos" as const },
    { pct: 20, color: "var(--viz-div-strong-pos)", side: "pos" as const },
  ];
  const neg = segs.filter((s) => s.side === "neg").reduce((a, b) => a + b.pct, 0);
  const pos = segs.filter((s) => s.side === "pos").reduce((a, b) => a + b.pct, 0);
  const mid = segs.find((s) => s.side === "mid")!.pct;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", paddingTop: "var(--space-2)" }}>
      <div style={{ display: "flex", height: 28, borderRadius: 4, overflow: "hidden", background: "var(--bg-sunken)" }}>
        <div style={{ flex: `0 0 ${neg}%`, display: "flex", justifyContent: "flex-end" }}>
          {segs.filter((s) => s.side === "neg").map((s, i) => <div key={i} style={{ width: `${(s.pct / neg) * 100}%`, background: s.color }} />)}
        </div>
        <div style={{ flex: `0 0 ${mid}%`, background: segs.find((s) => s.side === "mid")!.color }} />
        <div style={{ flex: `0 0 ${pos}%`, display: "flex" }}>
          {segs.filter((s) => s.side === "pos").map((s, i) => <div key={i} style={{ width: `${(s.pct / pos) * 100}%`, background: s.color }} />)}
        </div>
      </div>
      <div className="tabular" style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
        <span>{neg}% disagree</span>
        <span>{mid}% neutral</span>
        <span>{pos}% agree</span>
      </div>
    </div>
  );
}

function HBars({ bars }: { bars: { label: string; value: number }[] }) {
  const max = Math.max(...bars.map((b) => b.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
      {bars.map((b) => (
        <div key={b.label} style={{ display: "grid", gridTemplateColumns: "160px 1fr 40px", alignItems: "center", gap: "var(--space-3)" }}>
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>{b.label}</span>
          <div style={{ height: 12, background: "var(--bg-sunken)", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ width: `${(b.value / max) * 100}%`, height: "100%", background: "var(--viz-positive)" }} />
          </div>
          <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", textAlign: "right" }}>{b.value}%</span>
        </div>
      ))}
    </div>
  );
}
