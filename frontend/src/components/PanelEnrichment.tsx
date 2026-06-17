import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getMyPanel, savePanelAnswers, grantSensitiveConsent,
  PanelAttribute, PanelAnswerValue, PanelCompleteness,
} from "../api/panel";

/**
 * Progressive panel-enrichment UI for consented panelists. Unlike the
 * mandatory pre-interview questionnaire (one question at a time), this is a
 * grouped, scroll-and-tap board: answer as many or as few as you like, in any
 * order. The more you add, the higher the completeness — framed as "more
 * studies for you". Sensitive categories stay hidden until an explicit consent.
 *
 * Driven entirely by the server catalogue (`GET /panel/me`); answers save as
 * you tap (`POST /panel/answers`). Works with either a participant_session
 * (right after the interview) or a durable panel_session (the emailed portal).
 */

interface Props {
  token: string;
  embedded?: boolean; // post-interview inline vs full portal page
}

export default function PanelEnrichment({ token, embedded }: Props) {
  const { t, i18n } = useTranslation("panel");
  const lang = (i18n.language || "en").slice(0, 2);

  const [attributes, setAttributes] = useState<PanelAttribute[]>([]);
  const [answers, setAnswers] = useState<Record<string, PanelAnswerValue>>({});
  const [completeness, setCompleteness] = useState<PanelCompleteness | null>(null);
  const [sensitiveConsent, setSensitiveConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const sensitiveRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let active = true;
    getMyPanel(token, lang)
      .then((me) => {
        if (!active) return;
        setAttributes(me.attributes);
        setAnswers(me.answers);
        setCompleteness(me.completeness);
        setSensitiveConsent(me.sensitive_consent);
      })
      .catch(() => active && setError(t("loadError")))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token, lang, t]);

  async function persist(attribute_id: string, value: PanelAnswerValue) {
    try {
      const res = await savePanelAnswers(token, [{ attribute_id, value }]);
      setCompleteness(res.completeness);
    } catch {
      setError(t("saveError"));
    }
  }

  function setSingle(attr: PanelAttribute, value: string) {
    setAnswers((a) => ({ ...a, [attr.id]: value }));
    persist(attr.id, value);
  }
  function setBool(attr: PanelAttribute, value: boolean) {
    setAnswers((a) => ({ ...a, [attr.id]: value }));
    persist(attr.id, value);
  }
  function toggleMulti(attr: PanelAttribute, value: string) {
    setAnswers((a) => {
      const cur = Array.isArray(a[attr.id]) ? (a[attr.id] as string[]) : [];
      const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
      if (next.length > 0) persist(attr.id, next);
      return { ...a, [attr.id]: next };
    });
  }

  async function acceptSensitive() {
    try {
      const res = await grantSensitiveConsent(token, lang);
      setSensitiveConsent(res.sensitive_consent);
      setAttributes(res.attributes);
      setTimeout(() => sensitiveRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    } catch {
      setError(t("saveError"));
    }
  }

  // Group attributes by category, preserving the server's priority order.
  const groups = useMemo(() => {
    const map = new Map<string, PanelAttribute[]>();
    for (const a of attributes) {
      if (!map.has(a.category)) map.set(a.category, []);
      map.get(a.category)!.push(a);
    }
    return Array.from(map.entries());
  }, [attributes]);

  if (loading) return <p className="muted-text" style={{ textAlign: "center", padding: 24 }}>{t("loading")}</p>;

  const pct = completeness?.percent ?? 0;
  const answered = completeness?.answered_count ?? 0;

  function renderAttr(attr: PanelAttribute) {
    const val = answers[attr.id];
    return (
      <div className="panel-attr" key={attr.id}>
        <p className="panel-attr__label">{attr.label}</p>
        <div className="panel-attr__options">
          {attr.type === "bool" ? (
            <>
              <button className={`panel-chip${val === true ? " selected" : ""}`} onClick={() => setBool(attr, true)}>{t("yes")}</button>
              <button className={`panel-chip${val === false ? " selected" : ""}`} onClick={() => setBool(attr, false)}>{t("no")}</button>
            </>
          ) : attr.type === "multi" ? (
            attr.options.map((o) => {
              const sel = Array.isArray(val) && val.includes(o.value);
              return <button key={o.value} className={`panel-chip${sel ? " selected" : ""}`} onClick={() => toggleMulti(attr, o.value)}>{o.label}</button>;
            })
          ) : (
            attr.options.map((o) => (
              <button key={o.value} className={`panel-chip${val === o.value ? " selected" : ""}`} onClick={() => setSingle(attr, o.value)}>{o.label}</button>
            ))
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={embedded ? "panel-enrich panel-enrich--embedded" : "panel-enrich"}>
      <div className="panel-enrich__header">
        <h2 className="panel-enrich__title">{t("title")}</h2>
        <p className="panel-enrich__subtitle">{t("subtitle")}</p>
        <div className="panel-progress-bar"><div className="panel-progress-fill" style={{ width: `${pct}%` }} /></div>
        <p className="panel-enrich__progress">{t("progress", { count: answered, percent: pct })}</p>
      </div>

      {error && <div className="error-banner" role="alert">{error}</div>}

      {groups.map(([category, attrs]) => (
        <section className="panel-group" key={category}>
          <h3 className="panel-group__title">{t(`categories.${category}`, category)}</h3>
          {attrs.map(renderAttr)}
        </section>
      ))}

      {!sensitiveConsent && (
        <div className="panel-sensitive-card" ref={sensitiveRef}>
          <strong>{t("sensitiveTitle")}</strong>
          <p>{t("sensitiveBody")}</p>
          <button className="btn btn-primary" style={{ width: "100%", minHeight: 44 }} onClick={acceptSensitive}>
            {t("sensitiveAccept")}
          </button>
        </div>
      )}

      <p className="panel-enrich__foot">{t("stopAnytime")}</p>
    </div>
  );
}
