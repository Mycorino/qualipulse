import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  QuestionConfigChoice,
  Survey,
  SurveyQuestion,
  getSurvey,
  listQuestions,
} from "../api/surveys";
import { getStudy } from "../api/studies";
import { InstrumentShell } from "../components/InstrumentShell";
import {
  surveySections,
  surveySectionPath,
  surveyStatusPill,
} from "../components/surveyShellNav";

/**
 * SurveyPreview — renders the survey exactly as a respondent would see it.
 *
 * Read-only preview for the researcher. The actual public response page
 * (`/r/:token`) ships in Sprint 8 with submission wiring; this page is the
 * editor's "see what you built" check.
 */
export default function SurveyPreview() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("survey");
  const [survey, setSurvey] = useState<Survey | null>(null);
  const [study, setStudy] = useState<{ id: string; name: string } | null>(null);
  const [questions, setQuestions] = useState<SurveyQuestion[]>([]);

  useEffect(() => {
    if (!id) return;
    Promise.all([getSurvey(id), listQuestions(id)]).then(([s, qs]) => {
      setSurvey(s);
      setQuestions(qs);
      getStudy(s.study_id)
        .then((st) => setStudy({ id: st.id, name: st.name }))
        .catch(() => setStudy(null));
    });
  }, [id]);

  if (!survey) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">{t("preview.loading")}</p>
      </div>
    );
  }

  return (
    <InstrumentShell
      crumbs={[
        { label: t("preview.crumbStudies"), to: "/studies" },
        ...(study ? [{ label: study.name, to: `/studies/${study.id}` }] : []),
        { label: survey.name },
      ]}
      eyebrow={t("preview.eyebrow")}
      title={survey.name}
      status={surveyStatusPill(survey.status, t)}
      sections={surveySections(t)}
      activeSection="preview"
      onSectionChange={(k) => navigate(surveySectionPath(k, survey.id))}
      subNavLabel={t("preview.sectionsNavLabel")}
    >
      <p
        className="quanti-showcase__section-meta"
        style={{ textAlign: "center", padding: "var(--space-3) 0 0" }}
      >
        {t("preview.previewLabel")}
      </p>
      <div
        style={{
          maxWidth: 720,
          margin: "0 auto",
          padding: "var(--space-8) var(--space-5)",
        }}
      >
        <h1
          style={{
            fontFamily: "var(--font-serif)",
            fontSize: "var(--text-headline)",
            letterSpacing: "-0.025em",
            lineHeight: 1.15,
            marginBottom: "var(--space-3)",
          }}
        >
          {survey.name}
        </h1>
        {survey.description && (
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "var(--text-md)",
              lineHeight: 1.6,
              marginBottom: "var(--space-8)",
            }}
          >
            {survey.description}
          </p>
        )}

        {questions.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)", fontStyle: "italic" }}>
            {t("preview.noQuestions")}
          </p>
        ) : (
          <ol
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-8)",
              listStyle: "none",
              margin: 0,
              padding: 0,
            }}
          >
            {questions.map((q, i) => (
              <li key={q.id}>
                <PreviewQuestion question={q} index={i + 1} />
              </li>
            ))}
          </ol>
        )}

        <div
          style={{
            marginTop: "var(--space-12)",
            paddingTop: "var(--space-6)",
            borderTop: "1px solid var(--border-subtle)",
          }}
        >
          <button type="button" className="btn btn-primary" disabled>
            {t("preview.submitPreviewOnly")}
          </button>
        </div>
      </div>
    </InstrumentShell>
  );
}

function PreviewQuestion({
  question,
  index,
}: {
  question: SurveyQuestion;
  index: number;
}) {
  const { t } = useTranslation("survey");
  const cfg = question.config;
  return (
    <div>
      <div
        style={{
          fontSize: "var(--text-eyebrow)",
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--text-tertiary)",
          marginBottom: "var(--space-2)",
        }}
        className="tabular"
      >
        {t("preview.questionOf", { index })}
        {question.is_required && <span style={{ color: "var(--danger)" }}> · {t("preview.required")}</span>}
      </div>
      <div
        style={{
          fontSize: "var(--text-lg)",
          fontWeight: 500,
          lineHeight: 1.4,
          color: "var(--text-primary)",
          marginBottom: "var(--space-4)",
          fontFamily: "var(--font-serif)",
        }}
      >
        {question.prompt || (
          <em style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>{t("preview.untitledQuestion")}</em>
        )}
      </div>
      <PreviewInput type={question.type} config={cfg} />
    </div>
  );
}

function PreviewInput({
  type,
  config,
}: {
  type: SurveyQuestion["type"];
  config: Record<string, unknown>;
}) {
  const { t } = useTranslation("survey");
  if (type === "likert") {
    const scale = (config.scale as number) ?? 5;
    const anchors = (config.anchors as [string, string]) ?? [t("preview.likertDisagree"), t("preview.likertAgree")];
    return (
      <div>
        <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-2)" }}>
          {Array.from({ length: scale }).map((_, i) => (
            <button
              key={i}
              type="button"
              className="compare-chips__chip"
              style={{ flex: 1, justifyContent: "center", padding: "10px 0" }}
              disabled
            >
              {i + 1}
            </button>
          ))}
        </div>
        <div
          className="tabular"
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "var(--text-xs)",
            color: "var(--text-tertiary)",
          }}
        >
          <span>{anchors[0]}</span>
          <span>{anchors[1]}</span>
        </div>
      </div>
    );
  }
  if (type === "nps") {
    return (
      <div>
        <div style={{ display: "flex", gap: "4px" }}>
          {Array.from({ length: 11 }).map((_, i) => (
            <button
              key={i}
              type="button"
              className="compare-chips__chip"
              style={{ flex: 1, justifyContent: "center", padding: "10px 0" }}
              disabled
            >
              {i}
            </button>
          ))}
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "var(--text-xs)",
            color: "var(--text-tertiary)",
            marginTop: "var(--space-2)",
          }}
        >
          <span>{t("preview.npsNotLikely")}</span>
          <span>{t("preview.npsExtremelyLikely")}</span>
        </div>
      </div>
    );
  }
  if (type === "mc_single" || type === "mc_multi") {
    const choices = (config.choices as QuestionConfigChoice[]) ?? [];
    const inputType = type === "mc_single" ? "radio" : "checkbox";
    return (
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        {choices.map((c) => (
          <li
            key={c.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--space-3)",
              padding: "var(--space-3)",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              background: "var(--bg-surface)",
            }}
          >
            <input type={inputType} disabled />
            <span>{c.label}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (type === "open_text") {
    const maxChars = (config.max_chars as number) ?? 500;
    return (
      <textarea
        rows={4}
        disabled
        placeholder={t("preview.upToCharacters", { max: maxChars })}
        style={{
          width: "100%",
          padding: "var(--space-3)",
          border: "1px solid var(--border-default)",
          borderRadius: "var(--radius-md)",
          fontFamily: "inherit",
          fontSize: "var(--text-md)",
          background: "var(--bg-surface)",
        }}
      />
    );
  }
  if (type === "short_text") {
    const maxChars = (config.max_chars as number) ?? 120;
    return (
      <input
        type="text"
        disabled
        placeholder={t("preview.upToCharacters", { max: maxChars })}
        style={{
          width: "100%",
          padding: "10px var(--space-3)",
          border: "1px solid var(--border-default)",
          borderRadius: "var(--radius-md)",
          fontFamily: "inherit",
          fontSize: "var(--text-md)",
          background: "var(--bg-surface)",
        }}
      />
    );
  }
  return null;
}
