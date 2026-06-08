import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  AnswerSubmission,
  PublicQuestion,
  PublicSurvey,
  QuestionConfigChoice,
  getPublicSurvey,
  submitPublicResponse,
} from "../api/surveys";

/**
 * PublicResponse — `/r/:token` respondent-facing form.
 *
 * Mobile-first, no auth. Renders the live survey, collects answers,
 * submits via the public endpoint. Identity (email) is collected only if
 * the link isn't anonymous. Constant-time "Survey not available" for any
 * unhappy state — matches the backend contract.
 *
 * Validation runs client-side for fast feedback; server-side validation
 * is the authority (Sprint 6 wired the per-type checks).
 */

interface AnswerMap {
  [questionId: string]: AnswerSubmission;
}

export default function PublicResponse() {
  const { t } = useTranslation("shell");
  const { token } = useParams<{ token: string }>();
  const [survey, setSurvey] = useState<PublicSurvey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [startedAt] = useState(() => Date.now());

  useEffect(() => {
    if (!token) return;
    getPublicSurvey(token)
      .then(setSurvey)
      .catch(() => setError(t("publicResponse.notAvailable")));
  }, [token]);

  const missingRequired = useMemo(() => {
    if (!survey) return [];
    return survey.questions
      .filter((q) => q.is_required && !hasAnswerFor(q, answers[q.id]))
      .map((q) => q.id);
  }, [survey, answers]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !survey) return;
    if (missingRequired.length > 0) return;
    setSubmitting(true);
    try {
      const flatAnswers: AnswerSubmission[] = Object.values(answers).filter((a) =>
        // Only send answers that actually have a value, to avoid empty rows.
        a.value_numeric !== undefined ||
        (a.value_text && a.value_text.trim().length > 0) ||
        (a.value_choice_ids && a.value_choice_ids.length > 0),
      );
      await submitPublicResponse(token, {
        answers: flatAnswers,
        email: survey.is_anonymous ? undefined : email || undefined,
        is_complete: true,
        submission_metadata: {
          completion_seconds: Math.round((Date.now() - startedAt) / 1000),
          ua: navigator.userAgent,
        },
      });
      setSubmitted(true);
    } catch {
      setError(t("publicResponse.submitError"));
    } finally {
      setSubmitting(false);
    }
  };

  if (error) {
    return (
      <div className="public-response">
        <div className="public-response__container public-response__error">
          <h1>{error}</h1>
          <p>{t("publicResponse.errorContactHint")}</p>
        </div>
      </div>
    );
  }

  if (!survey) {
    return (
      <div className="public-response">
        <div className="public-response__container">
          <p style={{ color: "var(--text-tertiary)" }}>{t("publicResponse.loading")}</p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="public-response">
        <div className="public-response__container public-response__thanks">
          <h1>{t("publicResponse.thanksTitle")}</h1>
          <p>
            {t("publicResponse.thanksBody")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="public-response">
      <form onSubmit={onSubmit} className="public-response__container">
        <header className="public-response__head">
          <h1 className="public-response__title">{survey.name}</h1>
          {survey.description && (
            <p className="public-response__description">{survey.description}</p>
          )}
          {survey.is_anonymous && (
            <p className="public-response__anon-note">
              {t("publicResponse.anonymousNote")}
            </p>
          )}
        </header>

        <ol className="public-response__qlist">
          {survey.questions.map((q, i) => (
            <li key={q.id} className="public-response__qitem">
              <QuestionInput
                question={q}
                index={i + 1}
                value={answers[q.id]}
                showError={missingRequired.includes(q.id)}
                onChange={(v) =>
                  setAnswers((prev) => ({ ...prev, [q.id]: { question_id: q.id, ...v } }))
                }
              />
            </li>
          ))}
        </ol>

        {!survey.is_anonymous && (
          <div className="public-response__email-block">
            <label className="public-response__email-label" htmlFor="resp-email">
              {t("publicResponse.emailLabel")}
            </label>
            <input
              id="resp-email"
              type="email"
              className="public-response__email-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("publicResponse.emailPlaceholder")}
              autoComplete="email"
            />
            <p className="public-response__email-help">
              {t("publicResponse.emailHelp")}
            </p>
          </div>
        )}

        {missingRequired.length > 0 && (
          <div className="public-response__validation">
            {t("publicResponse.validation", { count: missingRequired.length })}
          </div>
        )}

        <div className="public-response__submit-row">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || missingRequired.length > 0}
          >
            {submitting ? t("publicResponse.submitting") : t("publicResponse.submit")}
          </button>
        </div>
      </form>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Per-type input components
   ──────────────────────────────────────────────────────────────────── */

function hasAnswerFor(q: PublicQuestion, a: AnswerSubmission | undefined): boolean {
  if (!a) return false;
  if (q.type === "likert" || q.type === "nps") {
    return typeof a.value_numeric === "number";
  }
  if (q.type === "mc_single" || q.type === "mc_multi") {
    return !!a.value_choice_ids && a.value_choice_ids.length > 0;
  }
  return !!a.value_text && a.value_text.trim().length > 0;
}

interface QuestionInputProps {
  question: PublicQuestion;
  index: number;
  value: AnswerSubmission | undefined;
  showError: boolean;
  onChange: (next: Omit<AnswerSubmission, "question_id">) => void;
}

function QuestionInput({ question, index, value, showError, onChange }: QuestionInputProps) {
  const { t } = useTranslation("shell");
  return (
    <div>
      <div className={`public-response__qhead${showError ? " public-response__qhead--error" : ""}`}>
        <span className="public-response__qnum tabular">
          {String(index).padStart(2, "0")}
          {question.is_required ? ` · ${t("publicResponse.required")}` : ""}
        </span>
        <h2 className="public-response__qprompt">{question.prompt}</h2>
      </div>
      <Renderer question={question} value={value} onChange={onChange} />
    </div>
  );
}

function Renderer({
  question,
  value,
  onChange,
}: {
  question: PublicQuestion;
  value: AnswerSubmission | undefined;
  onChange: (next: Omit<AnswerSubmission, "question_id">) => void;
}) {
  const { t } = useTranslation("shell");
  const cfg = question.config;
  if (question.type === "likert") {
    const scale = (cfg.scale as number) ?? 5;
    const anchors =
      (cfg.anchors as [string, string]) ??
      [t("publicResponse.likertLow"), t("publicResponse.likertHigh")];
    return (
      <div>
        <div className="public-response__scale">
          {Array.from({ length: scale }).map((_, i) => {
            const v = i + 1;
            const selected = value?.value_numeric === v;
            return (
              <button
                key={v}
                type="button"
                className={`public-response__scale-btn${selected ? " public-response__scale-btn--selected" : ""}`}
                onClick={() => onChange({ value_numeric: v })}
                aria-pressed={selected}
              >
                {v}
              </button>
            );
          })}
        </div>
        <div className="public-response__scale-labels tabular">
          <span>{anchors[0]}</span>
          <span>{anchors[1]}</span>
        </div>
      </div>
    );
  }
  if (question.type === "nps") {
    return (
      <div>
        <div className="public-response__nps">
          {Array.from({ length: 11 }).map((_, i) => {
            const selected = value?.value_numeric === i;
            return (
              <button
                key={i}
                type="button"
                className={`public-response__nps-btn${selected ? " public-response__nps-btn--selected" : ""}`}
                onClick={() => onChange({ value_numeric: i })}
                aria-pressed={selected}
              >
                {i}
              </button>
            );
          })}
        </div>
        <div className="public-response__scale-labels tabular">
          <span>{t("publicResponse.npsLow")}</span>
          <span>{t("publicResponse.npsHigh")}</span>
        </div>
      </div>
    );
  }
  if (question.type === "mc_single" || question.type === "mc_multi") {
    const choices = (cfg.choices as QuestionConfigChoice[]) ?? [];
    const selected = new Set(value?.value_choice_ids ?? []);
    const isMulti = question.type === "mc_multi";
    return (
      <ul className="public-response__choices">
        {choices.map((c) => {
          const isOn = selected.has(c.id);
          return (
            <li key={c.id}>
              <button
                type="button"
                className={`public-response__choice${isOn ? " public-response__choice--selected" : ""}`}
                onClick={() => {
                  if (isMulti) {
                    const next = new Set(selected);
                    if (next.has(c.id)) next.delete(c.id);
                    else next.add(c.id);
                    onChange({ value_choice_ids: Array.from(next) });
                  } else {
                    onChange({ value_choice_ids: [c.id] });
                  }
                }}
                aria-pressed={isOn}
              >
                <span className={`public-response__choice-marker${isOn ? " public-response__choice-marker--on" : ""}`} />
                <span>{c.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    );
  }
  if (question.type === "open_text") {
    const maxChars = (cfg.max_chars as number) ?? 500;
    return (
      <textarea
        className="public-response__textarea"
        rows={4}
        maxLength={maxChars}
        value={value?.value_text ?? ""}
        onChange={(e) => onChange({ value_text: e.target.value })}
        placeholder={t("publicResponse.openTextPlaceholder", { maxChars })}
      />
    );
  }
  if (question.type === "short_text") {
    const maxChars = (cfg.max_chars as number) ?? 120;
    return (
      <input
        type="text"
        className="public-response__text-input"
        maxLength={maxChars}
        value={value?.value_text ?? ""}
        onChange={(e) => onChange({ value_text: e.target.value })}
        placeholder=" "
      />
    );
  }
  return null;
}
