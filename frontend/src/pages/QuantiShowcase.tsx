import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("quantiDemo");
  const [filters, setFilters] = useState<Record<string, string[]>>({
    Role: ["pm"],
  });
  const [activeNav, setActiveNav] = useState("nps");
  const [selectedQuestionType, setSelectedQuestionType] = useState<string>("likert");
  const [editorType, setEditorType] = useState<"likert" | "multi_choice" | "nps" | "open_text">("likert");
  return (
    <div className="quanti-showcase">
      <header className="quanti-showcase__hero">
        <div className="quanti-showcase__eyebrow">{t("showcase.hero.eyebrow")}</div>
        <h1 className="quanti-showcase__title">
          {t("showcase.hero.title")}
        </h1>
        <p className="quanti-showcase__subtitle">
          {t("showcase.hero.subtitle")}
        </p>
      </header>

      {/* ── MethodologyBox ─────────────────────────────────────────── */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">MethodologyBox</h2>
          <p className="quanti-showcase__section-meta">
            {t("showcase.methodology.meta")}
          </p>
        </div>
        <MethodologyBox
          fields={[
            { label: t("showcase.methodology.fields.sampleSize.label"), value: t("showcase.methodology.fields.sampleSize.value") },
            { label: t("showcase.methodology.fields.fieldingWindow.label"), value: t("showcase.methodology.fields.fieldingWindow.value") },
            { label: t("showcase.methodology.fields.method.label"), value: t("showcase.methodology.fields.method.value") },
            { label: t("showcase.methodology.fields.segments.label"), value: t("showcase.methodology.fields.segments.value") },
            { label: t("showcase.methodology.fields.marginOfError.label"), value: t("showcase.methodology.fields.marginOfError.value") },
            { label: t("showcase.methodology.fields.sampling.label"), value: t("showcase.methodology.fields.sampling.value") },
          ]}
          note={t("showcase.methodology.note")}
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
            {t("showcase.chartCard.meta")}
          </p>
        </div>
        <div className="quanti-showcase__grid-2">
          <ChartCard
            eyebrow={t("showcase.chartCard.likert.eyebrow")}
            takeaway={t("showcase.chartCard.likert.takeaway")}
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <DivergingLikertDemo />
          </ChartCard>

          <ChartCard
            eyebrow={t("showcase.chartCard.nps.eyebrow")}
            takeaway={t("showcase.chartCard.nps.takeaway")}
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <NpsDistributionDemo />
          </ChartCard>

          <ChartCard
            eyebrow={t("showcase.chartCard.designers.eyebrow")}
            takeaway={t("showcase.chartCard.designers.takeaway")}
            n={12}
            completionRate={92}
          >
            <CountListDemo
              counts={[
                { label: t("showcase.chartCard.designers.counts.verySatisfied"), value: 6 },
                { label: t("showcase.chartCard.designers.counts.satisfied"), value: 4 },
                { label: t("showcase.chartCard.designers.counts.neutral"), value: 1 },
                { label: t("showcase.chartCard.designers.counts.dissatisfied"), value: 1 },
              ]}
            />
          </ChartCard>

          <ChartCard
            eyebrow={t("showcase.chartCard.multipleChoice.eyebrow")}
            takeaway={t("showcase.chartCard.multipleChoice.takeaway")}
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <HorizontalBarDemo
              bars={[
                { label: t("showcase.chartCard.multipleChoice.bars.pricingClarity"), value: 64 },
                { label: t("showcase.chartCard.multipleChoice.bars.fasterOnboarding"), value: 47 },
                { label: t("showcase.chartCard.multipleChoice.bars.betterIntegrations"), value: 38 },
                { label: t("showcase.chartCard.multipleChoice.bars.moreAi"), value: 29 },
                { label: t("showcase.chartCard.multipleChoice.bars.mobileApp"), value: 18 },
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
            {t("showcase.verbatim.meta")}
          </p>
        </div>
        <div className="quanti-showcase__grid-2">
          <VerbatimCard
            quote={t("showcase.verbatim.q1")}
            segments={["PM", "31–40", "United States"]}
          />
          <VerbatimCard
            quote={t("showcase.verbatim.q2")}
            segments={["Researcher", "26–30", "France"]}
          />
          <VerbatimCard
            quote={t("showcase.verbatim.q3")}
            segments={["Founder", "41–50", "United Kingdom"]}
          />
          <VerbatimCard
            quote={t("showcase.verbatim.q4")}
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
            {t("showcase.statHero.meta")}
          </p>
        </div>
        <StatHero
          eyebrow={t("showcase.statHero.onboarding.eyebrow")}
          stat="73%"
          description={t("showcase.statHero.onboarding.description")}
          meta={t("showcase.statHero.onboarding.meta")}
          quote={{
            text: t("showcase.statHero.onboarding.quote"),
            audioSrc: DEMO_AUDIO,
            segments: ["PM", "31–40", "United States"],
          }}
        />
        <StatHero
          eyebrow={t("showcase.statHero.recommendation.eyebrow")}
          stat="+25"
          description={t("showcase.statHero.recommendation.description")}
          meta={t("showcase.statHero.recommendation.meta")}
          quote={{
            text: t("showcase.statHero.recommendation.quote"),
            audioSrc: DEMO_AUDIO_2,
            segments: ["Researcher", "26–30", "France"],
          }}
        />
      </section>

      {/* Audio waveform (raw, on a quiet card) */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">{t("showcase.audioClip.title")}</h2>
          <p className="quanti-showcase__section-meta">
            {t("showcase.audioClip.metaPart1")} <code>src</code> {t("showcase.audioClip.metaPart2")}
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderRadius: "var(--radius-md)", padding: "var(--space-5)" }}>
          <AudioClip src={DEMO_AUDIO} label={t("showcase.audioClip.demo1")} variant="waveform" />
          <AudioClip src={DEMO_AUDIO_2} label={t("showcase.audioClip.demo2")} variant="waveform" />
          <AudioClip src={DEMO_AUDIO_3} label={t("showcase.audioClip.demo3")} variant="waveform" />
          <div style={{ borderTop: "1px solid var(--border-subtle)", marginTop: "var(--space-2)", paddingTop: "var(--space-3)" }}>
            <AudioClip src={DEMO_AUDIO} label={t("showcase.audioClip.barVariant")} variant="bar" />
          </div>
        </div>
      </section>

      {/* CompareChips */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">CompareChips</h2>
          <p className="quanti-showcase__section-meta">
            {t("showcase.compareChips.meta")} <code>{JSON.stringify(filters)}</code>
          </p>
        </div>
        <CompareChips
          value={filters}
          onChange={setFilters}
          groups={[
            {
              dimension: t("showcase.compareChips.dimensions.role"),
              options: [
                { value: "pm", label: t("showcase.compareChips.roleOptions.pm"), count: 89 },
                { value: "researcher", label: t("showcase.compareChips.roleOptions.researcher"), count: 64 },
                { value: "designer", label: t("showcase.compareChips.roleOptions.designer"), count: 42 },
                { value: "engineer", label: t("showcase.compareChips.roleOptions.engineer"), count: 38 },
                { value: "founder", label: t("showcase.compareChips.roleOptions.founder"), count: 14 },
              ],
            },
            {
              dimension: t("showcase.compareChips.dimensions.region"),
              options: [
                { value: "na", label: t("showcase.compareChips.regionOptions.na"), count: 112 },
                { value: "eu", label: t("showcase.compareChips.regionOptions.eu"), count: 98 },
                { value: "apac", label: t("showcase.compareChips.regionOptions.apac"), count: 31 },
                { value: "rest", label: t("showcase.compareChips.regionOptions.rest"), count: 6 },
              ],
            },
            {
              dimension: t("showcase.compareChips.dimensions.companySize"),
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
            {t("showcase.dashboard.meta")}
          </p>
        </div>
        <DashboardShell
          sidebar={
            <nav className="shell-nav" aria-label={t("showcase.dashboard.navLabel")}>
              <div className="shell-nav__group">
                <span className="shell-nav__group-label">{t("showcase.dashboard.groups.overview")}</span>
                <button
                  type="button"
                  className={`shell-nav__item${activeNav === "summary" ? " shell-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("summary")}
                >
                  {t("showcase.dashboard.items.summary")}
                </button>
                <button
                  type="button"
                  className={`shell-nav__item${activeNav === "segments" ? " shell-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("segments")}
                >
                  {t("showcase.dashboard.items.segments")}
                </button>
              </div>
              <div className="shell-nav__group">
                <span className="shell-nav__group-label">{t("showcase.dashboard.groups.perQuestion")}</span>
                <button
                  type="button"
                  className={`shell-nav__item${activeNav === "nps" ? " shell-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("nps")}
                >
                  {t("showcase.dashboard.items.nps")} <span className="shell-nav__count">247</span>
                </button>
                <button
                  type="button"
                  className={`shell-nav__item${activeNav === "onboarding" ? " shell-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("onboarding")}
                >
                  {t("showcase.dashboard.items.onboarding")} <span className="shell-nav__count">241</span>
                </button>
                <button
                  type="button"
                  className={`shell-nav__item${activeNav === "pricing" ? " shell-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("pricing")}
                >
                  {t("showcase.dashboard.items.pricing")} <span className="shell-nav__count">236</span>
                </button>
                <button
                  type="button"
                  className={`shell-nav__item${activeNav === "features" ? " shell-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("features")}
                >
                  {t("showcase.dashboard.items.features")} <span className="shell-nav__count">232</span>
                </button>
              </div>
              <div className="shell-nav__group">
                <span className="shell-nav__group-label">{t("showcase.dashboard.groups.raw")}</span>
                <button
                  type="button"
                  className={`shell-nav__item${activeNav === "responses" ? " shell-nav__item--active" : ""}`}
                  onClick={() => setActiveNav("responses")}
                >
                  {t("showcase.dashboard.items.responses")} <span className="shell-nav__count">247</span>
                </button>
              </div>
            </nav>
          }
        >
          <DashboardStrip
            items={[
              { label: t("showcase.dashboard.strip.respondents"), value: "247", delta: t("showcase.dashboard.strip.respondentsDelta"), deltaTone: "positive" },
              { label: t("showcase.dashboard.strip.completionRate"), value: "92%", delta: t("showcase.dashboard.strip.completionRateDelta"), deltaTone: "positive" },
              { label: t("showcase.dashboard.strip.fieldingWindow"), value: t("showcase.dashboard.strip.fieldingWindowValue"), delta: t("showcase.dashboard.strip.fieldingWindowDelta"), deltaTone: "neutral" },
            ]}
          />
          <ChartCard
            eyebrow={t("showcase.dashboard.chart.eyebrow")}
            takeaway={t("showcase.dashboard.chart.takeaway")}
            n={247}
            completionRate={92}
            ciHalfWidth={5.4}
          >
            <NpsDistributionDemo />
          </ChartCard>
          <VerbatimCard
            quote={t("showcase.dashboard.verbatim")}
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
            {t("showcase.questionType.meta")}
          </p>
        </div>
        <div className="quanti-showcase__grid-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
          <QuestionTypeCard
            name={t("showcase.questionType.likert.name")}
            description={t("showcase.questionType.likert.description")}
            bestFor={t("showcase.questionType.likert.bestFor")}
            guardrails={[
              { label: t("showcase.questionType.likert.guardrails.balanced"), tone: "info" },
              { label: t("showcase.questionType.likert.guardrails.randomized"), tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><circle cx="2" cy="7" r="1.5" fill="currentColor"/><circle cx="5" cy="7" r="1.5" fill="currentColor"/><circle cx="8" cy="7" r="1.5" fill="currentColor"/><circle cx="11" cy="7" r="1.5" fill="currentColor"/></svg>}
            selected={selectedQuestionType === "likert"}
            onSelect={() => { setSelectedQuestionType("likert"); setEditorType("likert"); }}
          />
          <QuestionTypeCard
            name={t("showcase.questionType.multiChoice.name")}
            description={t("showcase.questionType.multiChoice.description")}
            bestFor={t("showcase.questionType.multiChoice.bestFor")}
            guardrails={[
              { label: t("showcase.questionType.multiChoice.guardrails.randomized"), tone: "info" },
              { label: t("showcase.questionType.multiChoice.guardrails.anchor"), tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><rect x="2" y="2" width="3" height="3" rx="0.5" fill="currentColor"/><rect x="2" y="6" width="3" height="3" rx="0.5" fill="currentColor" opacity="0.4"/><rect x="2" y="10" width="3" height="3" rx="0.5" fill="currentColor"/></svg>}
            selected={selectedQuestionType === "multi_choice"}
            onSelect={() => { setSelectedQuestionType("multi_choice"); setEditorType("multi_choice"); }}
          />
          <QuestionTypeCard
            name={t("showcase.questionType.nps.name")}
            description={t("showcase.questionType.nps.description")}
            bestFor={t("showcase.questionType.nps.bestFor")}
            guardrails={[
              { label: t("showcase.questionType.nps.guardrails.standard"), tone: "info" },
              { label: t("showcase.questionType.nps.guardrails.locked"), tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 11 L7 4 L12 9 L12 11 Z" fill="currentColor"/></svg>}
            selected={selectedQuestionType === "nps"}
            onSelect={() => { setSelectedQuestionType("nps"); setEditorType("nps"); }}
          />
          <QuestionTypeCard
            name={t("showcase.questionType.openText.name")}
            description={t("showcase.questionType.openText.description")}
            bestFor={t("showcase.questionType.openText.bestFor")}
            guardrails={[
              { label: t("showcase.questionType.openText.guardrails.clustered"), tone: "info" },
              { label: t("showcase.questionType.openText.guardrails.maxChars"), tone: "neutral" },
            ]}
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><line x1="2" y1="4" x2="12" y2="4" stroke="currentColor" strokeWidth="1.4"/><line x1="2" y1="7" x2="12" y2="7" stroke="currentColor" strokeWidth="1.4"/><line x1="2" y1="10" x2="9" y2="10" stroke="currentColor" strokeWidth="1.4"/></svg>}
            selected={selectedQuestionType === "open_text"}
            onSelect={() => { setSelectedQuestionType("open_text"); setEditorType("open_text"); }}
          />
          <QuestionTypeCard
            name={t("showcase.questionType.maxDiff.name")}
            description={t("showcase.questionType.maxDiff.description")}
            bestFor={t("showcase.questionType.maxDiff.bestFor")}
            disabled
            icon={<svg width="14" height="14" viewBox="0 0 14 14"><path d="M2 4 L7 4 L7 6 L4 6 L4 8 L7 8 L7 10 L2 10 Z M9 4 L12 4 L12 10 L9 10 Z" fill="currentColor"/></svg>}
          />
          <QuestionTypeCard
            name={t("showcase.questionType.conjoint.name")}
            description={t("showcase.questionType.conjoint.description")}
            bestFor={t("showcase.questionType.conjoint.bestFor")}
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
            {t("showcase.surveyEditor.meta")}
          </p>
        </div>
        <SurveyQuestionEditor
          key={editorType}
          type={editorType}
          initialPrompt={
            editorType === "likert"
              ? t("showcase.surveyEditor.prompts.likert")
              : editorType === "multi_choice"
              ? t("showcase.surveyEditor.prompts.multiChoice")
              : editorType === "nps"
              ? t("showcase.surveyEditor.prompts.nps")
              : t("showcase.surveyEditor.prompts.openText")
          }
        />
      </section>

      {/* ScreenerBridge */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">ScreenerBridge</h2>
          <p className="quanti-showcase__section-meta">
            {t("showcase.screenerBridge.meta")}
          </p>
        </div>
        <ScreenerBridge
          matchCount={89}
          filterDescription={t("showcase.screenerBridge.detractors")}
          availableCredits={250}
          onInvite={() => alert("Demo: would queue 89 interview invites")}
          onSaveSegment={() => alert("Demo: would save segment to study")}
        />
        <ScreenerBridge
          matchCount={142}
          filterDescription={t("showcase.screenerBridge.promoters")}
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
            {t("showcase.findingCard.meta")}
          </p>
        </div>
        <FindingCard
          index={t("showcase.findingCard.f03.index")}
          actionTitle={t("showcase.findingCard.f03.actionTitle")}
          context={t("showcase.findingCard.f03.context")}
          evidence={
            <ChartCard
              eyebrow={t("showcase.findingCard.f03.evidenceEyebrow")}
              takeaway={t("showcase.findingCard.f03.evidenceTakeaway")}
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
                quote={t("showcase.findingCard.f03.verbatim1")}
                audioSrc={DEMO_AUDIO}
                segments={["PM", "31–40", "United States"]}
              />
              <VerbatimCard
                quote={t("showcase.findingCard.f03.verbatim2")}
                audioSrc={DEMO_AUDIO_2}
                segments={["Designer", "26–30", "Canada"]}
                compact
              />
            </>
          }
          implication={t("showcase.findingCard.f03.implication")}
          sampleNote={t("showcase.findingCard.f03.sampleNote")}
          confidence="strong"
        />
        <FindingCard
          index={t("showcase.findingCard.f04.index")}
          actionTitle={t("showcase.findingCard.f04.actionTitle")}
          evidence={
            <ChartCard
              eyebrow={t("showcase.findingCard.f04.evidenceEyebrow")}
              takeaway={t("showcase.findingCard.f04.evidenceTakeaway")}
              n={89}
              completionRate={94}
              ciHalfWidth={6.2}
            >
              <HorizontalBarDemo
                bars={[
                  { label: t("showcase.findingCard.f04.bars.aiReport"), value: 71 },
                  { label: t("showcase.findingCard.f04.bars.adaptiveInterviews"), value: 38 },
                  { label: t("showcase.findingCard.f04.bars.sharingExports"), value: 26 },
                  { label: t("showcase.findingCard.f04.bars.recruitingPanel"), value: 17 },
                ]}
              />
            </ChartCard>
          }
          verbatims={
            <VerbatimCard
              quote={t("showcase.findingCard.f04.verbatim")}
              audioSrc={DEMO_AUDIO_3}
              segments={["Researcher", "31–40", "United Kingdom"]}
            />
          }
          implication={t("showcase.findingCard.f04.implication")}
          sampleNote={t("showcase.findingCard.f04.sampleNote")}
          confidence="supported"
          layout="evidence-left"
        />
        <FindingCard
          index={t("showcase.findingCard.f05.index")}
          actionTitle={t("showcase.findingCard.f05.actionTitle")}
          evidence={
            <ChartCard
              eyebrow={t("showcase.findingCard.f05.evidenceEyebrow")}
              takeaway={t("showcase.findingCard.f05.evidenceTakeaway")}
              n={12}
              completionRate={92}
            >
              <CountListDemo
                counts={[
                  { label: t("showcase.findingCard.f05.counts.conceptTesting"), value: 7 },
                  { label: t("showcase.findingCard.f05.counts.brandPerception"), value: 3 },
                  { label: t("showcase.findingCard.f05.counts.pricingResearch"), value: 1 },
                  { label: t("showcase.findingCard.f05.counts.onboardingResearch"), value: 1 },
                ]}
              />
            </ChartCard>
          }
          verbatims={
            <VerbatimCard
              quote={t("showcase.findingCard.f05.verbatim")}
              segments={["Designer", "26–30", "Australia"]}
              compact
            />
          }
          implication={t("showcase.findingCard.f05.implication")}
          sampleNote={t("showcase.findingCard.f05.sampleNote")}
          confidence="directional"
        />
      </section>

      {/* Segment2x2 */}
      <section className="quanti-showcase__section">
        <div>
          <h2 className="quanti-showcase__section-title">Segment2x2</h2>
          <p className="quanti-showcase__section-meta">
            {t("showcase.segment2x2.meta")}
          </p>
        </div>
        <Segment2x2
          xAxisLabel={t("showcase.segment2x2.xAxisLabel")}
          yAxisLabel={t("showcase.segment2x2.yAxisLabel")}
          quadrants={[
            {
              label: t("showcase.segment2x2.q1.label"),
              quote: t("showcase.segment2x2.q1.quote"),
              segment: "PM · 31–40",
              n: 89,
            },
            {
              label: t("showcase.segment2x2.q2.label"),
              quote: t("showcase.segment2x2.q2.quote"),
              segment: "Founder · 41–50",
              n: 142,
            },
            {
              label: t("showcase.segment2x2.q3.label"),
              quote: t("showcase.segment2x2.q3.quote"),
              segment: "Designer · 26–30",
              n: 38,
            },
            {
              label: t("showcase.segment2x2.q4.label"),
              quote: t("showcase.segment2x2.q4.quote"),
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
            {t("showcase.crossTab.meta")}
          </p>
        </div>
        <CrossTabTable
          columns={[
            t("showcase.crossTab.columns.pms"),
            t("showcase.crossTab.columns.researchers"),
            t("showcase.crossTab.columns.designers"),
            t("showcase.crossTab.columns.engineers"),
            t("showcase.crossTab.columns.founders"),
          ]}
          columnNs={[89, 64, 12, 38, 14]}
          rows={[
            {
              label: t("showcase.crossTab.rows.onboardingFriction"),
              values: [62, 48, 67, 31, 71],
              counts: [55, 31, 8, 12, 10],
            },
            {
              label: t("showcase.crossTab.rows.pricingClarity"),
              values: [54, 39, 58, 24, 64],
              counts: [48, 25, 7, 9, 9],
            },
            {
              label: t("showcase.crossTab.rows.exportQuality"),
              values: [38, 71, 33, 18, 28],
              counts: [34, 45, 4, 7, 4],
            },
            {
              label: t("showcase.crossTab.rows.aiAccuracy"),
              values: [42, 56, 42, 21, 35],
              counts: [37, 36, 5, 8, 5],
            },
            {
              label: t("showcase.crossTab.rows.mobileParity"),
              values: [18, 12, 17, 14, 21],
              counts: [16, 8, 2, 5, 3],
            },
          ]}
          minN={30}
          note={t("showcase.crossTab.note")}
        />
      </section>

      <footer style={{ marginTop: "var(--space-12)", paddingTop: "var(--space-6)", borderTop: "1px solid var(--border-subtle)", color: "var(--text-tertiary)", fontSize: "var(--text-xs)" }}>
        {t("showcase.footer")}
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
  const { t } = useTranslation("quantiDemo");
  // Strong-disagree, disagree, neutral, agree, strong-agree
  const segments = [
    { label: t("showcase.charts.likert.stronglyDisagree"), pct: 12, color: "var(--viz-div-strong-neg)", side: "neg" as const },
    { label: t("showcase.charts.likert.disagree"), pct: 18, color: "var(--viz-div-neg)", side: "neg" as const },
    { label: t("showcase.charts.likert.neutral"), pct: 22, color: "var(--viz-div-mid)", side: "mid" as const },
    { label: t("showcase.charts.likert.agree"), pct: 28, color: "var(--viz-div-pos)", side: "pos" as const },
    { label: t("showcase.charts.likert.stronglyAgree"), pct: 20, color: "var(--viz-div-strong-pos)", side: "pos" as const },
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
        <div style={{ flex: `0 0 ${neutralPct}%`, background: segments.find((s) => s.side === "mid")?.color, height: "100%" }} title={`${t("showcase.charts.likert.neutral")}: ${neutralPct}%`} />
        {/* Positive side */}
        <div style={{ flex: `0 0 ${posTotal}%`, display: "flex", height: "100%" }}>
          {segments.filter((s) => s.side === "pos").map((s) => (
            <div key={s.label} style={{ width: `${(s.pct / posTotal) * 100}%`, background: s.color }} title={`${s.label}: ${s.pct}%`} />
          ))}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
        <span>{t("showcase.charts.likert.disagreeFooter", { pct: negTotal })}</span>
        <span style={{ color: "var(--text-secondary)" }}>{t("showcase.charts.likert.neutralFooter", { pct: neutralPct })}</span>
        <span>{t("showcase.charts.likert.agreeFooter", { pct: posTotal })}</span>
      </div>
    </div>
  );
}

function NpsDistributionDemo() {
  const { t } = useTranslation("quantiDemo");
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
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{t("showcase.charts.nps.scoreLabel")}</span>
      </div>
      <div style={{ display: "flex", height: 24, borderRadius: 4, overflow: "hidden" }}>
        <div style={{ width: `${detractors}%`, background: "var(--viz-negative)" }} title={`${t("showcase.charts.nps.detractors")}: ${detractors}%`} />
        <div style={{ width: `${passives}%`, background: "var(--viz-neutral)" }} title={`${t("showcase.charts.nps.passives")}: ${passives}%`} />
        <div style={{ width: `${promoters}%`, background: "var(--viz-positive)" }} title={`${t("showcase.charts.nps.promoters")}: ${promoters}%`} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
        <span>{t("showcase.charts.nps.detractors")} {detractors}%</span>
        <span>{t("showcase.charts.nps.passives")} {passives}%</span>
        <span>{t("showcase.charts.nps.promoters")} {promoters}%</span>
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
  const { t } = useTranslation("quantiDemo");
  const total = counts.reduce((a, b) => a + b.value, 0);
  // For small-n, show counts not percentages.
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
      {counts.map((c) => (
        <div key={c.label} style={{ display: "flex", justifyContent: "space-between", padding: "var(--space-2) 0", borderBottom: "1px dashed var(--border-subtle)" }}>
          <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>{c.label}</span>
          <span className="tabular" style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-semibold)", color: "var(--text-primary)" }}>
            {t("showcase.charts.countList.ofTotal", { value: c.value, total })}
          </span>
        </div>
      ))}
    </div>
  );
}
