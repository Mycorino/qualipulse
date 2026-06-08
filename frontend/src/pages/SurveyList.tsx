import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  Survey,
  SurveyTemplate,
  createFromTemplate,
  createSurvey,
  listSurveys,
  listTemplates,
} from "../api/surveys";
import { SurveyQuotaBanner } from "../components/SurveyQuotaBanner";
import { useToast } from "../components/Toast";
import { QuantiTopBar } from "../components/QuantiTopBar";

/**
 * SurveyList — minimal listing + create flow for the quanti track.
 *
 * Linked from the dashboard. New surveys auto-create an implicit Study
 * (per Decision 8 in the roadmap) so researchers never see "create a Study
 * first." The list is workspace-scoped via the existing auth dependency.
 */
export default function SurveyList() {
  const [surveys, setSurveys] = useState<Survey[] | null>(null);
  const [templates, setTemplates] = useState<SurveyTemplate[]>([]);
  const [creating, setCreating] = useState(false);
  const [seeding, setSeeding] = useState<string | null>(null);
  const [name, setName] = useState("");
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t } = useTranslation("survey");

  useEffect(() => {
    listSurveys()
      .then(setSurveys)
      .catch(() => toast(t("list.loadSurveysFailed"), "error"));
    listTemplates()
      .then(setTemplates)
      .catch(() => undefined);
  }, [toast]);

  const onUseTemplate = async (templateId: string) => {
    try {
      setSeeding(templateId);
      const survey = await createFromTemplate(templateId);
      navigate(`/surveys/${survey.id}/edit`);
    } catch {
      toast(t("list.createFromTemplateFailed"), "error");
    } finally {
      setSeeding(null);
    }
  };

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setCreating(true);
      const survey = await createSurvey({ name: name.trim() });
      navigate(`/surveys/${survey.id}/edit`);
    } catch {
      toast(t("list.createSurveyFailed"), "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)" }}>
    <QuantiTopBar crumbs={[{ label: t("list.crumbStudies"), to: "/studies" }, { label: t("list.crumbSurveys") }]} />
    <div className="quanti-showcase" style={{ padding: "var(--space-10) var(--report-canvas-pad-x)" }}>
      <SurveyQuotaBanner />
      <header
        className="quanti-showcase__hero"
        style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: "var(--space-4)", flexWrap: "wrap" }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="quanti-showcase__eyebrow">{t("list.eyebrow")}</div>
          <h1 className="quanti-showcase__title">{t("list.title")}</h1>
          <p className="quanti-showcase__subtitle">
            {t("list.subtitlePrefix")}<strong>{t("list.subtitleStudy")}</strong>{t("list.subtitleSuffix")}
          </p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => navigate("/studies")}>
          {t("list.viewAllStudies")}
        </button>
      </header>

      {templates.length > 0 && (
        <section className="quanti-showcase__section">
          <h2 className="quanti-showcase__section-title">{t("list.templatesTitle")}</h2>
          <p className="quanti-showcase__section-meta">
            {t("list.templatesMeta")}
          </p>
          <div className="quanti-showcase__grid-2">
            {templates.map((tpl) => (
              <button
                key={tpl.id}
                type="button"
                className="chart-card"
                style={{ textAlign: "left", cursor: "pointer", border: "1px solid var(--border-default)" }}
                onClick={() => onUseTemplate(tpl.id)}
                disabled={seeding !== null}
              >
                <div className="chart-card__eyebrow">{tpl.role.toUpperCase()}</div>
                <div className="chart-card__takeaway">{tpl.name}</div>
                <div className="chart-card__footer tabular">
                  <span>{t("list.questionCount", { count: tpl.question_count })}</span>
                  <span className="chart-card__footer-divider">·</span>
                  <span>{tpl.summary}</span>
                </div>
                <div style={{ marginTop: "var(--space-3)", color: "var(--brand-600)", fontSize: "var(--text-sm)", fontWeight: 500 }}>
                  {seeding === tpl.id ? t("list.creating") : t("list.useTemplate")}
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="quanti-showcase__section">
        <h2 className="quanti-showcase__section-title">{t("list.fromScratchTitle")}</h2>
        <form onSubmit={onCreate} style={{ display: "flex", gap: "var(--space-3)", maxWidth: 560 }}>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("list.namePlaceholder")}
            style={{
              flex: 1,
              padding: "10px 14px",
              fontSize: "var(--text-md)",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              background: "var(--bg-surface)",
            }}
          />
          <button type="submit" className="btn btn-primary" disabled={creating || !name.trim()}>
            {creating ? t("list.creating") : t("list.createSurvey")}
          </button>
        </form>
      </section>

      <section className="quanti-showcase__section">
        <h2 className="quanti-showcase__section-title">{t("list.allSurveysTitle")}</h2>
        {surveys === null ? (
          <p className="quanti-showcase__section-meta">{t("common.loading")}</p>
        ) : surveys.length === 0 ? (
          <p className="quanti-showcase__section-meta">{t("list.noSurveys")}</p>
        ) : (
          <div className="quanti-showcase__grid-2">
            {surveys.map((s) => (
              <a
                key={s.id}
                href={`/surveys/${s.id}/edit`}
                className="chart-card"
                style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
              >
                <div className="chart-card__eyebrow">
                  {s.role.toUpperCase()} · {s.status.toUpperCase()}
                </div>
                <div className="chart-card__takeaway">{s.name}</div>
                <div className="chart-card__footer tabular">
                  <span>{t("list.questionCount", { count: s.question_count })}</span>
                  <span className="chart-card__footer-divider">·</span>
                  <span>{t("list.completedCount", { count: s.completed_count })}</span>
                  <span className="chart-card__footer-divider">·</span>
                  <span>{t("list.totalCount", { count: s.response_count })}</span>
                </div>
              </a>
            ))}
          </div>
        )}
      </section>
    </div>
    </div>
  );
}
