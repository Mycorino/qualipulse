import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

/**
 * QuestionTypeCard — selectable tile for picking a survey question type.
 *
 * The methodologist's "rails not blank canvas" recommendation: each type
 * carries 1–2 guardrail badges so users see at picker time that we'll
 * randomize order, balance scales, or insert attention checks. Types we
 * deliberately defer to v2 (MaxDiff, conjoint) render with a "Coming soon"
 * pill and `disabled=true`.
 *
 * The icon slot is a simple ReactNode so callers can pass an SVG glyph.
 * Picked icons stay flat-line (no fills) so they sit calmly against the
 * tile's selected-state brand background.
 */
export interface QuestionTypeGuardrail {
  /** Short label shown in a small pill, e.g. "Auto-balanced" or "Order randomized". */
  label: string;
  /** Tone of the pill — defaults to neutral; "info" = brand-tinted. */
  tone?: "info" | "neutral";
}

interface QuestionTypeCardProps {
  /** Display name, e.g. "Likert (5-point)". */
  name: string;
  /** One-line description of when to use this type. */
  description: string;
  /** "Best for: opinions, agreement scales" — two-line max. */
  bestFor?: string;
  /** Methodological badges that will be enforced when this type is picked. */
  guardrails?: QuestionTypeGuardrail[];
  /** Inline icon glyph. Should be ~20px square. */
  icon?: ReactNode;
  /** Selected state — picker shows a brand-tinted border + checkmark. */
  selected?: boolean;
  /** v2 types render disabled with a "Coming soon" pill. */
  disabled?: boolean;
  /** Custom badge text used when disabled. Defaults to "Coming soon". */
  comingSoonLabel?: string;
  onSelect?: () => void;
}

export function QuestionTypeCard({
  name,
  description,
  bestFor,
  guardrails,
  icon,
  selected,
  disabled,
  comingSoonLabel,
  onSelect,
}: QuestionTypeCardProps) {
  const { t } = useTranslation("survey");
  const resolvedComingSoonLabel = comingSoonLabel ?? t("questionTypeCard.comingSoon");
  return (
    <button
      type="button"
      className={`question-type-card${selected ? " question-type-card--selected" : ""}${disabled ? " question-type-card--disabled" : ""}`}
      onClick={() => !disabled && onSelect?.()}
      aria-pressed={selected}
      disabled={disabled}
    >
      <div className="question-type-card__head">
        {icon && <span className="question-type-card__icon" aria-hidden="true">{icon}</span>}
        <span className="question-type-card__name">{name}</span>
        {selected && (
          <span className="question-type-card__check" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 7.5 L6 10.5 L11 4.5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </span>
        )}
        {disabled && <span className="question-type-card__pill">{resolvedComingSoonLabel}</span>}
      </div>
      <p className="question-type-card__description">{description}</p>
      {bestFor && <p className="question-type-card__best-for">{bestFor}</p>}
      {guardrails && guardrails.length > 0 && (
        <div className="question-type-card__guardrails">
          {guardrails.map((g) => (
            <span
              key={g.label}
              className={`question-type-card__guardrail question-type-card__guardrail--${g.tone ?? "neutral"}`}
            >
              <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
                <path d="M5 1 L1 3 L1 5.5 C1 7.5 5 9 5 9 C5 9 9 7.5 9 5.5 L9 3 Z" fill="currentColor" opacity="0.18"/>
                <path d="M5 1 L1 3 L1 5.5 C1 7.5 5 9 5 9 C5 9 9 7.5 9 5.5 L9 3 Z" stroke="currentColor" strokeWidth="0.8" fill="none"/>
              </svg>
              {g.label}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}
