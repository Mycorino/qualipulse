import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("quantiDemo");
  return (
    <ReportScroll
      cover={
        <div style={{ maxWidth: "980px", margin: "0 auto" }}>
          <div style={{ fontSize: "var(--text-eyebrow)", fontWeight: "var(--weight-semibold)", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--surface-emphasis-text-soft)", marginBottom: "var(--space-3)" }}>
            {t("reportDemo.cover.eyebrow")}
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "3.6rem", fontWeight: 700, letterSpacing: "-0.025em", lineHeight: 1.05, marginBottom: "var(--space-5)", maxWidth: "20ch" }}>
            {t("reportDemo.cover.title")}
          </h1>
          <p style={{ fontSize: "var(--text-lg)", color: "var(--surface-emphasis-text-soft)", lineHeight: 1.5, maxWidth: "60ch", marginBottom: "var(--space-8)" }}>
            {t("reportDemo.cover.lede")}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-6)", color: "var(--surface-emphasis-text-soft)", fontSize: "var(--text-sm)" }}>
            <div><span style={{ display: "block", fontSize: "var(--text-eyebrow)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--surface-emphasis-text-muted)", marginBottom: "4px" }}>{t("reportDemo.cover.sampleLabel")}</span><span className="tabular">{t("reportDemo.cover.sampleValue")}</span></div>
            <div><span style={{ display: "block", fontSize: "var(--text-eyebrow)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--surface-emphasis-text-muted)", marginBottom: "4px" }}>{t("reportDemo.cover.fieldWindowLabel")}</span><span className="tabular">{t("reportDemo.cover.fieldWindowValue")}</span></div>
            <div><span style={{ display: "block", fontSize: "var(--text-eyebrow)", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--surface-emphasis-text-muted)", marginBottom: "4px" }}>{t("reportDemo.cover.authorLabel")}</span>{t("reportDemo.cover.authorValue")}</div>
          </div>
        </div>
      }
      sections={[
        {
          id: "methodology",
          label: t("reportDemo.sections.methodology"),
          group: t("reportDemo.groups.context"),
          content: (
            <MethodologyBox
              fields={[
                { label: t("reportDemo.methodology.fields.sampleSize.label"), value: t("reportDemo.methodology.fields.sampleSize.value") },
                { label: t("reportDemo.methodology.fields.fieldingWindow.label"), value: t("reportDemo.methodology.fields.fieldingWindow.value") },
                { label: t("reportDemo.methodology.fields.method.label"), value: t("reportDemo.methodology.fields.method.value") },
                { label: t("reportDemo.methodology.fields.segments.label"), value: t("reportDemo.methodology.fields.segments.value") },
                { label: t("reportDemo.methodology.fields.marginOfError.label"), value: t("reportDemo.methodology.fields.marginOfError.value") },
                { label: t("reportDemo.methodology.fields.sampling.label"), value: t("reportDemo.methodology.fields.sampling.value") },
              ]}
              note={t("reportDemo.methodology.note")}
            />
          ),
        },
        {
          id: "executive-summary",
          label: t("reportDemo.sections.executiveSummary"),
          group: t("reportDemo.groups.context"),
          pageBreak: true,
          content: (
            <ExecutiveSummary
              headline={t("reportDemo.executiveSummary.headline")}
              subheadline={t("reportDemo.executiveSummary.subheadline")}
              thoughts={[
                {
                  thesis: t("reportDemo.executiveSummary.thought1.thesis"),
                  elaboration: t("reportDemo.executiveSummary.thought1.elaboration"),
                  findingRef: t("reportDemo.executiveSummary.thought1.findingRef"),
                },
                {
                  thesis: t("reportDemo.executiveSummary.thought2.thesis"),
                  elaboration: t("reportDemo.executiveSummary.thought2.elaboration"),
                  findingRef: t("reportDemo.executiveSummary.thought2.findingRef"),
                },
                {
                  thesis: t("reportDemo.executiveSummary.thought3.thesis"),
                  elaboration: t("reportDemo.executiveSummary.thought3.elaboration"),
                  findingRef: t("reportDemo.executiveSummary.thought3.findingRef"),
                },
              ]}
              author={{ name: t("reportDemo.executiveSummary.author.name"), role: t("reportDemo.executiveSummary.author.role"), date: t("reportDemo.executiveSummary.author.date") }}
            />
          ),
        },
        {
          id: "headline-stat",
          label: t("reportDemo.sections.headlineMetric"),
          group: t("reportDemo.groups.findings"),
          content: (
            <StatHero
              eyebrow={t("reportDemo.headlineStat.eyebrow")}
              stat="73%"
              description={t("reportDemo.headlineStat.description")}
              meta={t("reportDemo.headlineStat.meta")}
              quote={{
                text: t("reportDemo.headlineStat.quote"),
                audioSrc: A1,
                segments: ["PM", "31–40", "United States"],
              }}
            />
          ),
        },
        {
          id: "finding-03",
          label: t("reportDemo.sections.finding03"),
          group: t("reportDemo.groups.findings"),
          pageBreak: true,
          content: (
            <FindingCard
              index={t("reportDemo.finding03.index")}
              actionTitle={t("reportDemo.finding03.actionTitle")}
              context={t("reportDemo.finding03.context")}
              evidence={
                <ChartCard
                  eyebrow={t("reportDemo.finding03.evidenceEyebrow")}
                  takeaway={t("reportDemo.finding03.evidenceTakeaway")}
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
                    quote={t("reportDemo.finding03.verbatim1")}
                    audioSrc={A2}
                    segments={["PM", "31–40", "United States"]}
                  />
                  <VerbatimCard
                    quote={t("reportDemo.finding03.verbatim2")}
                    audioSrc={A3}
                    segments={["Designer", "26–30", "Canada"]}
                    compact
                  />
                </>
              }
              implication={t("reportDemo.finding03.implication")}
              sampleNote={t("reportDemo.finding03.sampleNote")}
              confidence="strong"
            />
          ),
        },
        {
          id: "finding-04",
          label: t("reportDemo.sections.finding04"),
          group: t("reportDemo.groups.findings"),
          pageBreak: true,
          content: (
            <FindingCard
              index={t("reportDemo.finding04.index")}
              actionTitle={t("reportDemo.finding04.actionTitle")}
              evidence={
                <ChartCard
                  eyebrow={t("reportDemo.finding04.evidenceEyebrow")}
                  takeaway={t("reportDemo.finding04.evidenceTakeaway")}
                  n={89}
                  completionRate={94}
                  ciHalfWidth={6.2}
                >
                  <HBars
                    bars={[
                      { label: t("reportDemo.finding04.bars.aiReport"), value: 71 },
                      { label: t("reportDemo.finding04.bars.adaptiveInterviews"), value: 38 },
                      { label: t("reportDemo.finding04.bars.sharingExports"), value: 26 },
                      { label: t("reportDemo.finding04.bars.recruitingPanel"), value: 17 },
                    ]}
                  />
                </ChartCard>
              }
              verbatims={
                <VerbatimCard
                  quote={t("reportDemo.finding04.verbatim")}
                  audioSrc={A4}
                  segments={["Researcher", "31–40", "United Kingdom"]}
                />
              }
              implication={t("reportDemo.finding04.implication")}
              sampleNote={t("reportDemo.finding04.sampleNote")}
              confidence="supported"
              layout="evidence-left"
            />
          ),
        },
        {
          id: "segment-matrix",
          label: t("reportDemo.sections.segmentLandscape"),
          group: t("reportDemo.groups.segmentation"),
          pageBreak: true,
          content: (
            <Segment2x2
              xAxisLabel={t("reportDemo.segmentMatrix.xAxisLabel")}
              yAxisLabel={t("reportDemo.segmentMatrix.yAxisLabel")}
              quadrants={[
                {
                  label: t("reportDemo.segmentMatrix.q1.label"),
                  quote: t("reportDemo.segmentMatrix.q1.quote"),
                  segment: "PM · 31–40",
                  n: 89,
                },
                {
                  label: t("reportDemo.segmentMatrix.q2.label"),
                  quote: t("reportDemo.segmentMatrix.q2.quote"),
                  segment: "Founder · 41–50",
                  n: 142,
                },
                {
                  label: t("reportDemo.segmentMatrix.q3.label"),
                  quote: t("reportDemo.segmentMatrix.q3.quote"),
                  segment: "Designer · 26–30",
                  n: 38,
                },
                {
                  label: t("reportDemo.segmentMatrix.q4.label"),
                  quote: t("reportDemo.segmentMatrix.q4.quote"),
                  segment: "Engineer · 31–40",
                  n: 18,
                },
              ]}
            />
          ),
        },
        {
          id: "cross-tab",
          label: t("reportDemo.sections.themesBySegment"),
          group: t("reportDemo.groups.segmentation"),
          content: (
            <CrossTabTable
              columns={[
                t("reportDemo.crossTab.columns.pms"),
                t("reportDemo.crossTab.columns.researchers"),
                t("reportDemo.crossTab.columns.designers"),
                t("reportDemo.crossTab.columns.engineers"),
                t("reportDemo.crossTab.columns.founders"),
              ]}
              columnNs={[89, 64, 12, 38, 14]}
              rows={[
                { label: t("reportDemo.crossTab.rows.onboardingFriction"), values: [62, 48, 67, 31, 71], counts: [55, 31, 8, 12, 10] },
                { label: t("reportDemo.crossTab.rows.pricingClarity"), values: [54, 39, 58, 24, 64], counts: [48, 25, 7, 9, 9] },
                { label: t("reportDemo.crossTab.rows.exportQuality"), values: [38, 71, 33, 18, 28], counts: [34, 45, 4, 7, 4] },
                { label: t("reportDemo.crossTab.rows.aiAccuracy"), values: [42, 56, 42, 21, 35], counts: [37, 36, 5, 8, 5] },
                { label: t("reportDemo.crossTab.rows.mobileParity"), values: [18, 12, 17, 14, 21], counts: [16, 8, 2, 5, 3] },
              ]}
              note={t("reportDemo.crossTab.note")}
            />
          ),
        },
        {
          id: "prioritization",
          label: t("reportDemo.sections.whatToDoNext"),
          group: t("reportDemo.groups.action"),
          pageBreak: true,
          content: (
            <PrioritizationMatrix
              recommendations={[
                { id: "1", title: t("reportDemo.prioritization.rec1"), impact: 88, feasibility: 78, effort: "quick", findingRef: t("reportDemo.prioritization.ref03") },
                { id: "2", title: t("reportDemo.prioritization.rec2"), impact: 72, feasibility: 82, effort: "medium", findingRef: t("reportDemo.prioritization.ref04") },
                { id: "3", title: t("reportDemo.prioritization.rec3"), impact: 64, feasibility: 90, effort: "quick", findingRef: t("reportDemo.prioritization.ref03") },
                { id: "4", title: t("reportDemo.prioritization.rec4"), impact: 52, feasibility: 70, effort: "medium", findingRef: t("reportDemo.prioritization.ref05") },
                { id: "5", title: t("reportDemo.prioritization.rec5"), impact: 78, feasibility: 32, effort: "large", findingRef: t("reportDemo.prioritization.ref04") },
                { id: "6", title: t("reportDemo.prioritization.rec6"), impact: 42, feasibility: 28, effort: "large", findingRef: t("reportDemo.prioritization.ref06") },
                { id: "7", title: t("reportDemo.prioritization.rec7"), impact: 58, feasibility: 64, effort: "medium", findingRef: t("reportDemo.prioritization.ref04") },
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
  const { t } = useTranslation("quantiDemo");
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
        <span>{t("reportDemo.charts.likert.disagreeFooter", { pct: neg })}</span>
        <span>{t("reportDemo.charts.likert.neutralFooter", { pct: mid })}</span>
        <span>{t("reportDemo.charts.likert.agreeFooter", { pct: pos })}</span>
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
