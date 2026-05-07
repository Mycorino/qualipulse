import { useState } from "react";

/**
 * SurveyQuestionEditor — the question-being-built editor surface.
 *
 * Type-specific editors are composed inside a shared shell so the editor
 * shape stays consistent across types: prompt input → type-specific config
 * → preview → guardrail flags.
 *
 * For Sprint 3 we ship Likert and Multiple-choice editors with the
 * methodologist's hard guardrails baked in:
 *   - Likert: scale-balance is enforced (positive count must equal negative
 *     count). The editor blocks adding a 4th positive option until a 4th
 *     negative is also added.
 *   - Multiple choice: order-randomization is on by default, with an
 *     anchor-this-option toggle per option (combats primacy bias).
 *
 * The other types (NPS, Single MC, Open text, Ranking, Matrix) will use
 * the same shell + their own configs — sketched as stubs in v1.
 */

type QuestionType = "likert" | "multi_choice" | "nps" | "open_text";

export interface SurveyQuestionEditorProps {
  type: QuestionType;
  initialPrompt?: string;
  /** Called when the editor changes — gives the parent the canonical question shape. */
  onChange?: (q: { type: QuestionType; prompt: string; config: Record<string, unknown> }) => void;
}

export function SurveyQuestionEditor({ type, initialPrompt = "", onChange }: SurveyQuestionEditorProps) {
  const [prompt, setPrompt] = useState(initialPrompt);

  return (
    <div className="survey-q-editor">
      <div className="survey-q-editor__head">
        <span className="survey-q-editor__type-pill">{labelForType(type)}</span>
        <span className="survey-q-editor__id">Q · draft</span>
      </div>
      <label className="survey-q-editor__prompt-label">Question prompt</label>
      <textarea
        className="survey-q-editor__prompt"
        value={prompt}
        onChange={(e) => {
          setPrompt(e.target.value);
          onChange?.({ type, prompt: e.target.value, config: {} });
        }}
        placeholder={placeholderForType(type)}
        rows={2}
      />
      <PromptGuardrails prompt={prompt} />

      <div className="survey-q-editor__divider" />

      {type === "likert" && <LikertConfig />}
      {type === "multi_choice" && <MultiChoiceConfig />}
      {type === "nps" && <NpsConfig />}
      {type === "open_text" && <OpenTextConfig />}
    </div>
  );
}

function labelForType(t: QuestionType): string {
  switch (t) {
    case "likert": return "Likert · 5-point";
    case "multi_choice": return "Multiple choice";
    case "nps": return "Net Promoter Score";
    case "open_text": return "Open text";
  }
}

function placeholderForType(t: QuestionType): string {
  switch (t) {
    case "likert": return "How strongly do you agree with the following statement: …";
    case "multi_choice": return "Which of the following best describes …";
    case "nps": return "How likely are you to recommend us to a friend or colleague?";
    case "open_text": return "What's the one thing we could change to make this better?";
  }
}

/* ────────────────────────────────────────────────────────────────────
   Real-time prompt guardrails — Claude-equivalent, but client-side
   regex for the showcase. Production will call a backend that gives
   suggestion text alongside the flag.
   ──────────────────────────────────────────────────────────────────── */
function PromptGuardrails({ prompt }: { prompt: string }) {
  const flags: { tone: "warn" | "info"; label: string; detail: string }[] = [];
  if (/\b(and|or)\b/i.test(prompt) && prompt.split(" ").length > 6) {
    flags.push({
      tone: "warn",
      label: "Possible double-barreled question",
      detail: "Splitting 'speed and reliability' into two questions usually produces cleaner data.",
    });
  }
  if (/\b(love|hate|amazing|terrible|brilliant|awful)\b/i.test(prompt)) {
    flags.push({
      tone: "warn",
      label: "Leading wording detected",
      detail: "Loaded adjectives bias responses. Try a neutral framing.",
    });
  }
  if (prompt.length > 0 && prompt.length < 8) {
    flags.push({
      tone: "info",
      label: "Prompt looks short",
      detail: "A question under 8 characters often confuses respondents.",
    });
  }
  if (flags.length === 0) return null;
  return (
    <div className="survey-q-editor__guardrails">
      {flags.map((f) => (
        <div
          key={f.label}
          className={`survey-q-editor__guardrail survey-q-editor__guardrail--${f.tone}`}
          role="status"
        >
          <strong>{f.label}.</strong> {f.detail}
        </div>
      ))}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Type-specific configs
   ──────────────────────────────────────────────────────────────────── */

function LikertConfig() {
  // Balanced 5-point scale, enforced. The middle anchor is editable but
  // the four side anchors are paired so users can't unbalance the scale.
  const [anchors, setAnchors] = useState({
    strongDisagree: "Strongly disagree",
    disagree: "Disagree",
    neutral: "Neither agree nor disagree",
    agree: "Agree",
    strongAgree: "Strongly agree",
  });
  return (
    <div className="survey-q-editor__config">
      <div className="survey-q-editor__config-head">
        <span className="survey-q-editor__config-title">Scale anchors</span>
        <span className="survey-q-editor__config-flag">Balance enforced</span>
      </div>
      <div className="survey-q-editor__likert-row">
        <LikertAnchor label="STRONGLY DISAGREE" value={anchors.strongDisagree} onChange={(v) => setAnchors({ ...anchors, strongDisagree: v })} tone="strong-neg" />
        <LikertAnchor label="DISAGREE" value={anchors.disagree} onChange={(v) => setAnchors({ ...anchors, disagree: v })} tone="neg" />
        <LikertAnchor label="NEUTRAL" value={anchors.neutral} onChange={(v) => setAnchors({ ...anchors, neutral: v })} tone="mid" />
        <LikertAnchor label="AGREE" value={anchors.agree} onChange={(v) => setAnchors({ ...anchors, agree: v })} tone="pos" />
        <LikertAnchor label="STRONGLY AGREE" value={anchors.strongAgree} onChange={(v) => setAnchors({ ...anchors, strongAgree: v })} tone="strong-pos" />
      </div>
      <p className="survey-q-editor__config-note">
        Anchors are paired across the scale. You can rephrase each label, but the count of positive
        and negative options always stays equal — unbalanced scales bias responses toward the
        majority side.
      </p>
    </div>
  );
}

function LikertAnchor({ label, value, onChange, tone }: { label: string; value: string; onChange: (v: string) => void; tone: "strong-neg" | "neg" | "mid" | "pos" | "strong-pos" }) {
  return (
    <div className={`survey-q-editor__likert-anchor survey-q-editor__likert-anchor--${tone}`}>
      <span className="survey-q-editor__likert-pill" />
      <span className="survey-q-editor__likert-anchor-label">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="survey-q-editor__likert-input"
      />
    </div>
  );
}

function MultiChoiceConfig() {
  const [options, setOptions] = useState([
    { text: "Pricing clarity", anchored: false },
    { text: "Faster onboarding", anchored: false },
    { text: "Better integrations", anchored: false },
    { text: "More AI features", anchored: false },
    { text: "Other", anchored: true },
  ]);
  return (
    <div className="survey-q-editor__config">
      <div className="survey-q-editor__config-head">
        <span className="survey-q-editor__config-title">Options</span>
        <span className="survey-q-editor__config-flag">Order randomized</span>
      </div>
      <ul className="survey-q-editor__option-list">
        {options.map((opt, i) => (
          <li key={i} className="survey-q-editor__option">
            <span className="survey-q-editor__option-handle" aria-hidden="true">⋮⋮</span>
            <input
              type="text"
              className="survey-q-editor__option-input"
              value={opt.text}
              onChange={(e) => {
                const next = [...options];
                next[i] = { ...next[i], text: e.target.value };
                setOptions(next);
              }}
            />
            <button
              type="button"
              className={`survey-q-editor__option-anchor${opt.anchored ? " survey-q-editor__option-anchor--on" : ""}`}
              onClick={() => {
                const next = [...options];
                next[i] = { ...next[i], anchored: !next[i].anchored };
                setOptions(next);
              }}
              aria-pressed={opt.anchored}
              title={opt.anchored ? "Anchored — won't be randomized" : "Anchor this option"}
            >
              📌 Anchor
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="survey-q-editor__add-option"
        onClick={() => setOptions([...options, { text: "", anchored: false }])}
      >
        + Add option
      </button>
    </div>
  );
}

function NpsConfig() {
  return (
    <div className="survey-q-editor__config">
      <div className="survey-q-editor__config-head">
        <span className="survey-q-editor__config-title">Scale</span>
        <span className="survey-q-editor__config-flag">Standard 0–10</span>
      </div>
      <p className="survey-q-editor__config-note">
        NPS uses the validated 0–10 scale with fixed Detractor (0–6) / Passive (7–8) / Promoter (9–10) buckets.
        Anchor wording is locked: 0 = "Not at all likely", 10 = "Extremely likely".
      </p>
    </div>
  );
}

function OpenTextConfig() {
  const [maxLength, setMaxLength] = useState(500);
  return (
    <div className="survey-q-editor__config">
      <div className="survey-q-editor__config-head">
        <span className="survey-q-editor__config-title">Response settings</span>
      </div>
      <label className="survey-q-editor__inline-label">
        Max length
        <input
          type="number"
          className="survey-q-editor__inline-input tabular"
          value={maxLength}
          onChange={(e) => setMaxLength(Number(e.target.value))}
          min={50}
          max={5000}
          step={50}
        />
        characters
      </label>
      <p className="survey-q-editor__config-note">
        Open text responses are AI-clustered into themes in the dashboard — a max length under 500
        characters keeps clustering quality high.
      </p>
    </div>
  );
}
