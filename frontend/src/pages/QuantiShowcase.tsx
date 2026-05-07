import { useState } from "react";
import { ChartCard } from "../components/ChartCard";
import { VerbatimCard } from "../components/VerbatimCard";
import { MethodologyBox, SmallNWarning } from "../components/MethodologyBox";
import { StatHero } from "../components/StatHero";
import { CompareChips } from "../components/CompareChips";
import { DashboardShell, DashboardStrip } from "../components/DashboardShell";
import { AudioClip } from "../components/AudioClip";
import { QuestionTypeCard } from "../components/QuestionTypeCard";
import { SurveyQuestionEditor } from "../components/SurveyQuestionEditor";
import { ScreenerBridge } from "../components/ScreenerBridge";
import { FindingCard } from "../components/FindingCard";
import { Segment2x2 } from "../components/Segment2x2";
import { CrossTabTable } from "../components/CrossTabTable";

/**
 * QuantiShowcase — preview surface for Sprint 1 components.
 *
 * Not linked from production navigation. Reachable at /design-system/quanti
 * for design review and iteration. Demonstrates each component in a
 * representative context so the editorial voice can be evaluated end-to-end.
 */
// Tiny silent-WAV data URIs so the AudioClip element loads successfully in
// the showcase. The waveform shape hashes off the URI string itself, so the
// three clips look distinct even though the audio payload is identical
// silence. Real verbatims will use real R2 URLs.
const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";
const DEMO_AUDIO = `${SILENT_WAV}#demo-1`;
const DEMO_AUDIO_2 = `${SILENT_WAV}#demo-2`;
const DEMO_AUDIO_3 = `${SILENT_WAV}#demo-3`;

export default function QuantiShowcase() {
  const [filters, setFilters] = useState<Record<string, string[]>>({
    Role: ["pm"],
  });
  const [activeNav, setActiveNav] = useState("nps");
  const [selectedQuestionType, setSelectedQuestionType] = useState<string>("likert");
  const [editorType, setEditorType] = useState<"likert" | "multi_choice" | "nps" | "open_text">("likert");
  return (
    <div className="quanti-showcase">
      <header className="quanti-showcase__hero">
        <div className="quanti-showcase__eyebrow">Design system · Sprint 1</div>
        <h1 className="quanti-showcase__title">
          The editorial voice for mixed-methods research
        </h1>
        <p className="quanti-showcase__subtitle">
          Three primitives for the quanti surface — a ChartCard that enforces a takeaway-above-chart
          discipline, a VerbatimCard that pairs verbatim quotes with optional audio, and a
          MethodologyBox that anchors every report in credible sample notation.
        </p>
      </header>

      {/* ── MethodologyBox ─────────────────────────────────────────── */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">MethodologyBox</h2>
          <p className="quanti-showcase__section-meta">
            Required at the top of every shared report. Expanded variant in the appendix.
          </p>
        </div>
        <MethodologyBox
          fields={[
            { label: "Sample size", value: "n=247 completers" },
            { label: "Fielding window", value: "Apr 14 – May 02, 2026" },
            { label: "Method", value: "Mixed (survey + 18 interviews)" },
            { label: "Segments", value: "Role · Company size · Region" },
            { label: "Margin of error", value: "±5.4pp at 95% confidence" },
            { label: "Sampling", value: "Stratified panel quota" },
          ]}
          note="Weighted to match B2B SaaS PM/researcher composition by company size and region. Unweighted counts shown alongside weighted percentages throughout. Segment splits below n=30 are reported as counts only."
        />
        <div>
          <SmallNWarning n={12} />
        </div>
      </section>

      {/* ── ChartCard ──────────────────────────────────────────────── */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">ChartCard</h2>
          <p className="quanti-showcase__section-meta">
            Eyebrow → serif takeaway → chart slot → footer with sample notation. Below n=30 a
            directional-only warning surfaces automatically.
          </p>
        </div>
        <div className="quanti-showcase__grid-2">
          <ChartCard
            eyebrow="Likert · Q3"
            takeaway="Detractors cite onboarding friction 3× more than promoters."
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <DivergingLikertDemo />
          </ChartCard>

          <ChartCard
            eyebrow="NPS · Q7"
            takeaway="A clear majority of users would recommend us, but a vocal detractor segment is forming."
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <NpsDistributionDemo />
          </ChartCard>

          <ChartCard
            eyebrow="Segment · Designers"
            takeaway="Designers' satisfaction skews high — but the sample is too small to claim significance."
            n={12}
            completionRate={92}
          >
            <CountListDemo
              counts={[
                { label: "Very satisfied", value: 6 },
                { label: "Satisfied", value: 4 },
                { label: "Neutral", value: 1 },
                { label: "Dissatisfied", value: 1 },
              ]}
            />
          </ChartCard>

          <ChartCard
            eyebrow="Multiple choice · Q5"
            takeaway="Pricing clarity tops the request list — twice as often as feature gaps."
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <HorizontalBarDemo
              bars={[
                { label: "Pricing clarity", value: 64 },
                { label: "Faster onboarding", value: 47 },
                { label: "Better integrations", value: 38 },
                { label: "More AI features", value: 29 },
                { label: "Mobile app", value: 18 },
              ]}
            />
          </ChartCard>
        </div>
      </section>

      {/* ── VerbatimCard ───────────────────────────────────────────── */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">VerbatimCard</h2>
          <p className="quanti-showcase__section-meta">
            Pull-quote with optional audio playback. Defaults to segment-only attribution
            (privacy-first) — names appear only when participants have consented to identification.
          </p>
        </div>
        <div className="quanti-showcase__grid-2">
          <VerbatimCard
            quote="I almost cancelled last week. The pricing page never explained what 'team' actually meant — I was paying for seats I didn't need."
            segments={["PM", "31–40", "United States"]}
          />
          <VerbatimCard
            quote="The interview format felt unusually natural. I forgot it was an AI after the second question."
            segments={["Researcher", "26–30", "France"]}
          />
          <VerbatimCard
            quote="What I want is fewer tools, not more features. Every new dashboard is another tab I'll never open."
            segments={["Founder", "41–50", "United Kingdom"]}
          />
          <VerbatimCard
            quote="Honestly? I just need it to be fast. Everything else is negotiable."
            segments={["Engineer", "26–30", "Germany"]}
            compact
          />
        </div>
      </section>

      {/* ── Sprint 2 ─────────────────────────────────────────────────── */}

      {/* StatHero */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">StatHero</h2>
          <p className="quanti-showcase__section-meta">
            The page-unit pattern for "stat + voice" pairings — 60/40 stat-left, verbatim-right.
            One stat per hero. The waveform inside the verbatim is the signature interaction.
          </p>
        </div>
        <StatHero
          eyebrow="Onboarding · Q2"
          stat="73%"
          description="of new users abandon onboarding before reaching the third step."
          meta="n=247 · 95% CI ±5.4pp · Apr 14 – May 02, 2026"
          quote={{
            text: "I almost cancelled last week. The pricing page never explained what 'team' actually meant — I was paying for seats I didn't need.",
            audioSrc: DEMO_AUDIO,
            segments: ["PM", "31–40", "United States"],
          }}
        />
        <StatHero
          eyebrow="Recommendation · Q7"
          stat="+25"
          description="Net Promoter Score across all completed responses — promoters outweigh detractors but a vocal segment is forming."
          meta="n=247 · 47% promoters · 22% detractors"
          quote={{
            text: "Honestly, I'd recommend it tomorrow if the analysis took half as long. Right now it's a 7 — could be a 9.",
            audioSrc: DEMO_AUDIO_2,
            segments: ["Researcher", "26–30", "France"],
          }}
        />
      </section>

      {/* Audio waveform (raw, on a quiet card) */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">AudioClip — waveform variant</h2>
          <p className="quanti-showcase__section-meta">
            Procedural waveform tinted with the viz palette. Filled bars track playback; the
            shape is deterministic per <code>src</code> so each clip looks distinct without
            real audio decoding. Real Web Audio decoding is a follow-up.
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderRadius: "var(--radius-md)", padding: "var(--space-5)" }}>
          <AudioClip src={DEMO_AUDIO} label="Waveform demo 1" variant="waveform" />
          <AudioClip src={DEMO_AUDIO_2} label="Waveform demo 2" variant="waveform" />
          <AudioClip src={DEMO_AUDIO_3} label="Waveform demo 3" variant="waveform" />
          <div style={{ borderTop: "1px solid var(--border-subtle)", marginTop: "var(--space-2)", paddingTop: "var(--space-3)" }}>
            <AudioClip src={DEMO_AUDIO} label="Bar variant for comparison" variant="bar" />
          </div>
        </div>
      </section>

      {/* CompareChips */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">CompareChips</h2>
          <p className="quanti-showcase__section-meta">
            Multi-select segment filter, grouped by dimension. Active state is brand-filled;
            "All" resets a dimension. Selected: <code>{JSON.stringify(filters)}</code>
          </p>
        </div>
        <CompareChips
          value={filters}
          onChange={setFilters}
          groups={[
            {
              dimension: "Role",
              options: [
                { value: "pm", label: "Product Manager", count: 89 },
                { value: "researcher", label: "Researcher", count: 64 },
                { value: "designer", label: "Designer", count: 42 },
                { value: "engineer", label: "Engineer", count: 38 },
                { value: "founder", label: "Founder", count: 14 },
              ],
            },
            {
              dimension: "Region",
              options: [
                { value: "na", label: "North America", count: 112 },
                { value: "eu", label: "Europe", count: 98 },
                { value: "apac", label: "APAC", count: 31 },
                { value: "rest", label: "Rest of world", count: 6 },
              ],
            },
            {
              dimension: "Company size",
              options: [
                { value: "smb", label: "1–50", count: 73 },
                { value: "mid", label: "51–500", count: 121 },
                { value: "ent", label: "500+", count: 53 },
              ],
            },
          ]}
        />
      </section>

      {/* DashboardShell + DashboardStrip */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">DashboardShell &amp; DashboardStrip</h2>
          <p className="quanti-showcase__section-meta">
            Sticky sidebar nav + scrolling canvas. Strip anchors the top with three editorial
            metrics in serif. This is the layout every quanti dashboard surface inherits.
          </p>
        </div>
        <DashboardShell
          sidebar={
            <nav className="dashboard-nav" aria-label="Study sections">
              <div className="dashboard-nav__group">
                <span className="dashboard-nav__group-label">Overview</span>
                <button
                  type="button"
                  className={`dashboard-nav__item${activeNav === "summary" ? " dashboard-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("summary")}
                >
                  Summary
                </button>
                <button
                  type="button"
                  className={`dashboard-nav__item${activeNav === "segments" ? " dashboard-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("segments")}
                >
                  Segments
                </button>
              </div>
              <div className="dashboard-nav__group">
                <span className="dashboard-nav__group-label">Per question</span>
                <button
                  type="button"
                  className={`dashboard-nav__item${activeNav === "nps" ? " dashboard-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("nps")}
                >
                  Q1 — Net promoter <span className="dashboard-nav__count">247</span>
                </button>
                <button
                  type="button"
                  className={`dashboard-nav__item${activeNav === "onboarding" ? " dashboard-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("onboarding")}
                >
                  Q2 — Onboarding friction <span className="dashboard-nav__count">241</span>
                </button>
                <button
                  type="button"
                  className={`dashboard-nav__item${activeNav === "pricing" ? " dashboard-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("pricing")}
                >
                  Q3 — Pricing clarity <span className="dashboard-nav__count">236</span>
                </button>
                <button
                  type="button"
                  className={`dashboard-nav__item${activeNav === "features" ? " dashboard-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("features")}
                >
                  Q4 — Feature priorities <span className="dashboard-nav__count">232</span>
                </button>
              </div>
              <div className="dashboard-nav__group">
                <span className="dashboard-nav__group-label">Raw</span>
                <button
                  type="button"
                  className={`dashboard-nav__item${activeNav === "responses" ? " dashboard-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("responses")}
                >
                  All responses <span className="dashboard-nav__count">247</span>
                </button>
              </div>
            </nav>
          }
        >
          <DashboardStrip
            items={[
              { label: "Respondents", value: "247", delta: "+34 this week", deltaTone: "positive" },
              { label: "Completion rate", value: "92%", delta: "+3pp vs last study", deltaTone: "positive" },
              { label: "Fielding window", value: "18 days", delta: "Apr 14 – May 02, 2026", deltaTone: "neutral" },
            ]}
          />
          <ChartCard
            eyebrow="NPS · Q1"
            takeaway="Promoters outweigh detractors, but the detractor segment is forming early in the trial."
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <NpsDistributionDemo />
          </ChartCard>
          <VerbatimCard
            quote="The product is great. The pricing page is what nearly killed the sale."
            audioSrc={DEMO_AUDIO_3}
            segments={["PM", "31–40", "Germany"]}
          />
        </DashboardShell>
      </section>

      {/* ── Sprint 3 ─────────────────────────────────────────────────── */}

      {/* QuestionTypeCard */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">QuestionTypeCard</h2>
          <p className="quanti-showcase__section-meta">
            Selectable tile for picking a question type. Each carries methodological-guardrail
            badges so users see at picker time that we'll randomize order, balance scales, and
            insert attention checks. v2 types render with a "Coming soon" pill.
          </p>
        </div>
        <div className="quanti-showcase__grid-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <QuestionTypeCard
            name="Likert · 5-point"
            description="Measure agreement on a balanced scale."
            bestFor="Best for: opinions, agreement statements"
            guardrails={[
              { label: "Auto-balanced", tone: "info" },
              { label: "Order randomized", tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><circle cx="2" cy="7" r="1.5" fill="currentColor"/><circle cx="5" cy="7" r="1.5" fill="currentColor"/><circle cx="8" cy="7" r="1.5" fill="currentColor"/><circle cx="11" cy="7" r="1.5" fill="currentColor"/></svg>}
            selected={selectedQuestionType === "likert"}
            onSelect={() => { setSelectedQuestionType("likert"); setEditorType("likert"); }}
          />
          <QuestionTypeCard
            name="Multiple choice"
            description="Pick one or more from a list of options."
            bestFor="Best for: feature requests, behaviors"
            guardrails={[
              { label: "Order randomized", tone: "info" },
              { label: "Anchor support", tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><rect x="2" y="2" width="3" height="3" rx="0.5" fill="currentColor"/><rect x="2" y="6" width="3" height="3" rx="0.5" fill="currentColor" opacity="0.4"/><rect x="2" y="10" width="3" height="3" rx="0.5" fill="currentColor"/></svg>}
            selected={selectedQuestionType === "multi_choice"}
            onSelect={() => { setSelectedQuestionType("multi_choice"); setEditorType("multi_choice"); }}
          />
          <QuestionTypeCard
            name="Net Promoter Score"
            description="Validated 0–10 recommendation scale."
            bestFor="Best for: tracking advocacy over time"
            guardrails={[
              { label: "Standard 0–10", tone: "info" },
              { label: "Anchors locked", tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 11 L7 4 L12 9 L12 11 Z" fill="currentColor"/></svg>}
            selected={selectedQuestionType === "nps"}
            onSelect={() => { setSelectedQuestionType("nps"); setEditorType("nps"); }}
          />
          <QuestionTypeCard
            name="Open text"
            description="Free-form responses, AI-clustered into themes."
            bestFor="Best for: 'one thing we could change'"
            guardrails={[
              { label: "AI-clustered", tone: "info" },
              { label: "Max 500 chars", tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><line x1="2" y1="4" x2="12" y2="4" stroke="currentColor" strokeWidth="1.4"/><line x1="2" y1="7" x2="12" y2="7" stroke="currentColor" strokeWidth="1.4"/><line x1="2" y1="10" x2="9" y2="10" stroke="currentColor" strokeWidth="1.4"/></svg>}
            selected={selectedQuestionType === "open_text"}
            onSelect={() => { setSelectedQuestionType("open_text"); setEditorType("open_text"); }}
          />
          <QuestionTypeCard
            name="MaxDiff"
            description="Force-rank trade-offs between attributes."
            bestFor="Best for: feature prioritization at scale"
            disabled
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 4 L7 4 L7 6 L4 6 L4 8 L7 8 L7 10 L2 10 Z M9 4 L12 4 L12 10 L9 10 Z" fill="currentColor"/></svg>}
          />
          <QuestionTypeCard
            name="Conjoint analysis"
            description="Decompose preferences into attribute utilities."
            bestFor="Best for: pricing & packaging research"
            disabled
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><circle cx="4" cy="4" r="2.5" fill="currentColor" opacity="0.5"/><circle cx="10" cy="4" r="2.5" fill="currentColor" opacity="0.5"/><circle cx="7" cy="9" r="2.5" fill="currentColor"/></svg>}
          />
        </div>
      </section>

      {/* SurveyQuestionEditor */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">SurveyQuestionEditor</h2>
          <p className="quanti-showcase__section-meta">
            The question-being-built editor surface. Type-specific configs live inside a shared
            shell. Real-time prompt guardrails flag double-barreled questions and leading wording
            as the user types — try writing "How satisfied are you with the speed and reliability?"
            or "Do you love our product?" to see them fire.
          </p>
        </div>
        <SurveyQuestionEditor
          key={editorType}
          type={editorType}
          initialPrompt={
            editorType === "likert"
              ? "How satisfied are you with the speed and reliability of the analysis pipeline?"
              : editorType === "multi_choice"
              ? "Which of the following would most improve your workflow?"
              : editorType === "nps"
              ? "How likely are you to recommend us to a friend or colleague?"
              : "What's the one thing we could change to make this better for you?"
          }
        />
      </section>

      {/* ScreenerBridge */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">ScreenerBridge</h2>
          <p className="quanti-showcase__section-meta">
            The wedge — survey-to-interview conversion. Filtered survey respondents get invited to
            a 10-minute AI voice interview in one click. Credit cost is shown upfront; credits are
            only charged when an interview actually completes.
          </p>
        </div>
        <ScreenerBridge
          matchCount={89}
          filterDescription={'"Detractors who use mobile daily" — Role: PM, Region: NA, NPS ≤ 6'}
          availableCredits={250}
          onInvite={() => alert("Demo: would queue 89 interview invites")}
          onSaveSegment={() => alert("Demo: would save segment to study")}
        />
        <ScreenerBridge
          matchCount={142}
          filterDescription={'"Promoters at 500+ employee companies" — NPS ≥ 9, Company size ≥ 500'}
          availableCredits={75}
          onInvite={() => alert("Demo: would queue first 75 invites + waitlist")}
          onSaveSegment={() => alert("Demo: would save segment to study")}
        />
      </section>

      {/* ── Sprint 4 ─────────────────────────────────────────────────── */}

      {/* FindingCard */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">FindingCard</h2>
          <p className="quanti-showcase__section-meta">
            The MBB action-title page unit for the mixed-methods report. Action-title in serif
            (thesis-style, never "Theme: X"), evidence row, "So what" implication line, confidence
            pill, and sample note. Three layout variants by composition.
          </p>
        </div>
        <FindingCard
          index="Finding 03 of 07"
          actionTitle="Trust gaps cost us 30% of new users — driven by checkout, not pricing."
          context="Detractors who churned in their first month consistently flagged the checkout flow as opaque — even when their stated objection was price. The pricing page tested clean; the checkout did not."
          evidence={
            <ChartCard
              eyebrow="Likert · Q3 — Checkout clarity"
              takeaway="Detractors rate checkout 3× more confusing than promoters, and 2× more confusing than pricing."
              n={247}
              completionRate={92}
              ciHalfWidth={5.4}
            >
              <DivergingLikertDemo />
            </ChartCard>
          }
          verbatims={
            <>
              <VerbatimCard
                quote="The pricing page made sense. The checkout asked for things I didn't expect — that's where I bailed."
                audioSrc={DEMO_AUDIO}
                segments={["PM", "31–40", "United States"]}
              />
              <VerbatimCard
                quote="I genuinely thought I was being charged twice. The line items don't match what's on the pricing page."
                audioSrc={DEMO_AUDIO_2}
                segments={["Designer", "26–30", "Canada"]}
                compact
              />
            </>
          }
          implication="Reorder the checkout to mirror the pricing page line-by-line. The pricing copy is the trust-builder; the checkout currently undoes that work in 30 seconds."
          sampleNote="n=247 survey · 18 follow-up interviews · 4 segments"
          confidence="strong"
        />
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
              <HorizontalBarDemo
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
              audioSrc={DEMO_AUDIO_3}
              segments={["Researcher", "31–40", "United Kingdom"]}
            />
          }
          implication="Lead the marketing site with the report, not the interview. The interview is plumbing; the report is what gets paid for."
          sampleNote="n=89 promoters · 6 renewal interviews"
          confidence="supported"
          layout="evidence-left"
        />
        <FindingCard
          index="Finding 05 of 07"
          actionTitle="Designers may be a separate ICP entirely — but the sample is too thin to commit."
          evidence={
            <ChartCard
              eyebrow="Segment · Designers"
              takeaway="Designers' top use case looks distinct from PMs and Researchers — but at n=12 we can't confirm."
              n={12}
              completionRate={92}
            >
              <CountListDemo
                counts={[
                  { label: "Concept testing", value: 7 },
                  { label: "Brand perception", value: 3 },
                  { label: "Pricing research", value: 1 },
                  { label: "Onboarding research", value: 1 },
                ]}
              />
            </ChartCard>
          }
          verbatims={
            <VerbatimCard
              quote="I bought this for concept tests, not for customer research. I'd love a faster way to spin up a 5-person concept reaction."
              segments={["Designer", "26–30", "Australia"]}
              compact
            />
          }
          implication="Run a targeted 30-respondent survey of designers before building anything. The signal is interesting but a 12-person sample isn't a roadmap input."
          sampleNote="n=12 designer respondents · 1 follow-up interview"
          confidence="directional"
        />
      </section>

      {/* Segment2x2 */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">Segment2x2</h2>
          <p className="quanti-showcase__section-meta">
            The MECE-forcing page unit. Cell tints scale with volume share so the eye lands on the
            heaviest quadrant first. One quote per cell, never two — discipline on the page.
          </p>
        </div>
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
      </section>

      {/* CrossTabTable */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">CrossTabTable</h2>
          <p className="quanti-showcase__section-meta">
            Theme × segment table with sequential-tint conditional formatting. Cells below n=30
            display counts (not percentages) with a hatched background — small-n honesty baked in.
          </p>
        </div>
        <CrossTabTable
          columns={["PMs", "Researchers", "Designers", "Engineers", "Founders"]}
          columnNs={[89, 64, 12, 38, 14]}
          rows={[
            {
              label: "Onboarding friction",
              values: [62, 48, 67, 31, 71],
              counts: [55, 31, 8, 12, 10],
            },
            {
              label: "Pricing clarity",
              values: [54, 39, 58, 24, 64],
              counts: [48, 25, 7, 9, 9],
            },
            {
              label: "Export quality",
              values: [38, 71, 33, 18, 28],
              counts: [34, 45, 4, 7, 4],
            },
            {
              label: "AI accuracy",
              values: [42, 56, 42, 21, 35],
              counts: [37, 36, 5, 8, 5],
            },
            {
              label: "Mobile parity",
              values: [18, 12, 17, 14, 21],
              counts: [16, 8, 2, 5, 3],
            },
          ]}
          minN={30}
          note="Designer column shows counts because n=12 falls below the inference threshold (n≥30). Themes are AI-clustered from open-text responses; cells show the % of that segment that mentioned the theme."
        />
      </section>

      <footer style={{ marginTop: "var(--space-12)", paddingTop: "var(--space-6)", borderTop: "1px solid var(--border-subtle)", color: "var(--text-tertiary)", fontSize: "var(--text-xs)" }}>
        Sprint 1 + 2 + 3 + 4 — design-system extension for the quanti work track. 13 new
        components: ChartCard, VerbatimCard, MethodologyBox, StatHero, CompareChips, DashboardShell,
        DashboardStrip, QuestionTypeCard, SurveyQuestionEditor, ScreenerBridge, FindingCard,
        Segment2x2, CrossTabTable, plus a waveform variant on the existing AudioClip primitive.
        Sprint 5 next: report scrollytelling layout + print stylesheet + PrioritizationMatrix.
      </footer>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Lightweight demo charts — pure CSS/SVG, no chart library yet.
   These are illustrative for the showcase only; production charts will
   use Recharts and live inside a dedicated chart-library wrapper.
   ──────────────────────────────────────────────────────────────────── */

function DivergingLikertDemo() {
  // Strong-disagree, disagree, neutral, agree, strong-agree
  const segments = [
    { label: "Strongly disagree", pct: 12, color: "var(--viz-div-strong-neg)", side: "neg" as const },
    { label: "Disagree", pct: 18, color: "var(--viz-div-neg)", side: "neg" as const },
    { label: "Neutral", pct: 22, color: "var(--viz-div-mid)", side: "mid" as const },
    { label: "Agree", pct: 28, color: "var(--viz-div-pos)", side: "pos" as const },
    { label: "Strongly agree", pct: 20, color: "var(--viz-div-strong-pos)", side: "pos" as const },
  ];
  const negTotal = segments.filter((s) => s.side === "neg").reduce((a, b) => a + b.pct, 0);
  const posTotal = segments.filter((s) => s.side === "pos").reduce((a, b) => a + b.pct, 0);
  const neutralPct = segments.find((s) => s.side === "mid")?.pct ?? 0;
  // Each side scales to half the bar; neutral straddles the middle.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", paddingTop: "var(--space-2)" }}>
      <div style={{ display: "flex", alignItems: "center", height: 28, position: "relative", borderRadius: 4, overflow: "hidden", background: "var(--bg-sunken)" }}>
        {/* Negative side, right-aligned to center */}
        <div style={{ flex: `0 0 ${negTotal}%`, display: "flex", justifyContent: "flex-end", height: "100%" }}>
          {segments.filter((s) => s.side === "neg").map((s) => (
            <div key={s.label} style={{ width: `${(s.pct / negTotal) * 100}%`, background: s.color }} title={`${s.label}: ${s.pct}%`} />
          ))}
        </div>
        {/* Neutral straddles the middle */}
        <div style={{ flex: `0 0 ${neutralPct}%`, background: segments.find((s) => s.side === "mid")?.color, height: "100%" }} title={`Neutral: ${neutralPct}%`} />
        {/* Positive side */}
        <div style={{ flex: `0 0 ${posTotal}%`, display: "flex", height: "100%" }}>
          {segments.filter((s) => s.side === "pos").map((s) => (
            <div key={s.label} style={{ width: `${(s.pct / posTotal) * 100}%`, background: s.color }} title={`${s.label}: ${s.pct}%`} />
          ))}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
        <span>{negTotal}% disagree</span>
        <span style={{ color: "var(--text-secondary)" }}>{neutralPct}% neutral</span>
        <span>{posTotal}% agree</span>
      </div>
    </div>
  );
}

function NpsDistributionDemo() {
  const detractors = 22;
  const passives = 31;
  const promoters = 47;
  const nps = promoters - detractors;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", paddingTop: "var(--space-2)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-3)" }}>
        <span className="tabular" style={{ fontFamily: "var(--font-serif)", fontSize: "var(--text-2xl)", fontWeight: "var(--weight-bold)", color: "var(--brand-700)" }}>
          +{nps}
        </span>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>NPS score</span>
      </div>
      <div style={{ display: "flex", height: 24, borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${detractors}%`, background: "var(--viz-negative)" }} title={`Detractors: ${detractors}%`} />
        <div style={{ width: `${passives}%`, background: "var(--viz-neutral)" }} title={`Passives: ${passives}%`} />
        <div style={{ width: `${promoters}%`, background: "var(--viz-positive)" }} title={`Promoters: ${promoters}%`} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
        <span>Detractors {detractors}%</span>
        <span>Passives {passives}%</span>
        <span>Promoters {promoters}%</span>
      </div>
    </div>
  );
}

function HorizontalBarDemo({ bars }: { bars: { label: string; value: number }[] }) {
  const max = Math.max(...bars.map((b) => b.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
      {bars.map((b) => (
        <div key={b.label} style={{ display: "grid", gridTemplateColumns: "140px 1fr 40px", alignItems: "center", gap: "var(--space-3)" }}>
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

function CountListDemo({ counts }: { counts: { label: string; value: number }[] }) {
  // For small-n, show counts not percentages.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
      {counts.map((c) => (
        <div key={c.label} style={{ display: "flex", justifyContent: "space-between", padding: "var(--space-2) 0", borderBottom: "1px dashed var(--border-subtle)" }}>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>{c.label}</span>
          <span className="tabular" style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)" }}>
            {c.value} of {counts.reduce((a, b) => a + b.value, 0)}
          </span>
        </div>
      ))}
    </div>
  );
}
