import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES } from "../i18n";
import {
  generateScreeningTranslation,
  patchScreeningTranslation,
  ScreeningQuestionResponse,
} from "../api/projects";
import { useToast } from "./Toast";

/**
 * Researcher-facing editor for a screening question's per-language localizations.
 * Auto-generated translations are pre-filled; the researcher can review/correct
 * the wording per language. Options are aligned by index to the canonical
 * options (the disqualification gate's stable identity is never touched here).
 */

const NATIVE: Record<string, string> = {
  en: "English", fr: "Français", de: "Deutsch", es: "Español", it: "Italiano", pt: "Português",
};

interface Props {
  projectId: string;
  screening: ScreeningQuestionResponse;
  sourceLang: string;
  onSaved: () => void;
}

export default function ScreeningTranslationsEditor({ projectId, screening, sourceLang, onSaved }: Props) {
  const { toast } = useToast();
  const { t } = useTranslation("project");
  const [open, setOpen] = useState(false);
  const langs = useMemo(
    () => SUPPORTED_LANGUAGES.filter((l) => l !== sourceLang.slice(0, 2)),
    [sourceLang]
  );
  const [lang, setLang] = useState<string>(langs[0] ?? "fr");
  const tr = screening.translations?.[lang];
  const [question, setQuestion] = useState(tr?.question ?? screening.question);
  const [options, setOptions] = useState<string[]>(
    screening.options.map((o, i) => tr?.options?.[i] ?? o)
  );
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);

  function applyTranslation(l: string, source: ScreeningQuestionResponse) {
    const t = source.translations?.[l];
    setQuestion(t?.question ?? source.question);
    setOptions(source.options.map((o, i) => t?.options?.[i] ?? o));
  }

  // Auto-fill a language's fields via Claude the first time it's selected and
  // no translation is cached yet. Cheap and lazy — a language nobody opens is
  // never translated. On failure the canonical text stays editable.
  async function autofill(next: string) {
    if (generating) return;
    setGenerating(true);
    try {
      const fresh = await generateScreeningTranslation(projectId, screening.id, next);
      applyTranslation(next, fresh);
      onSaved(); // persist ✓ state + cache sibling questions translated in the same call
    } catch {
      applyTranslation(next, screening); // fall back to canonical, let the user type
    } finally {
      setGenerating(false);
    }
  }

  function switchLang(next: string) {
    setLang(next);
    if (screening.translations?.[next]) {
      applyTranslation(next, screening);
    } else {
      void autofill(next);
    }
  }

  function toggleOpen() {
    setOpen((v) => {
      const opening = !v;
      if (opening && !screening.translations?.[lang]) void autofill(lang);
      return opening;
    });
  }

  async function save() {
    setSaving(true);
    try {
      await patchScreeningTranslation(projectId, screening.id, { lang, question, options });
      toast(t("screeningTranslations.saved"), "success");
      onSaved();
    } catch {
      toast(t("screeningTranslations.saveFailed"), "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="screening-tr">
      <button className="screening-tr__toggle" onClick={toggleOpen}>
        {open ? "▾" : "▸"} 🌐 {t("screeningTranslations.toggle")}
      </button>
      {open && (
        <div className="screening-tr__body">
          <div className="screening-tr__langs">
            {langs.map((l) => (
              <button
                key={l}
                className={`screening-tr__lang${l === lang ? " active" : ""}`}
                onClick={() => switchLang(l)}
                disabled={generating}
              >
                {NATIVE[l] ?? l}
                {screening.translations?.[l] ? " ✓" : ""}
              </button>
            ))}
          </div>
          {generating && (
            <p className="screening-tr__generating">✨ {t("screeningTranslations.generating")}</p>
          )}
          <label className="field-label">{t("screeningTranslations.questionLabel")}</label>
          <input
            className="field-input"
            value={question}
            disabled={generating}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <label className="field-label" style={{ marginTop: 8 }}>{t("screeningTranslations.optionsLabel")}</label>
          {screening.options.map((canonical, i) => (
            <div key={i} className="screening-tr__opt">
              <span className="screening-tr__canonical">{canonical}</span>
              <input
                className="field-input"
                value={options[i] ?? ""}
                disabled={generating}
                onChange={(e) => setOptions((prev) => prev.map((o, oi) => (oi === i ? e.target.value : o)))}
              />
            </div>
          ))}
          <button
            className="btn btn-primary btn-sm"
            style={{ marginTop: 10 }}
            disabled={saving || generating}
            onClick={save}
          >
            {saving ? "Saving…" : `Save ${NATIVE[lang] ?? lang}`}
          </button>
        </div>
      )}
    </div>
  );
}
