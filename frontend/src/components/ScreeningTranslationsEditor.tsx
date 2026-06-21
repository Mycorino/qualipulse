import { useMemo, useState } from "react";
import { SUPPORTED_LANGUAGES } from "../i18n";
import { patchScreeningTranslation, ScreeningQuestionResponse } from "../api/projects";
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

  function switchLang(next: string) {
    setLang(next);
    const t = screening.translations?.[next];
    setQuestion(t?.question ?? screening.question);
    setOptions(screening.options.map((o, i) => t?.options?.[i] ?? o));
  }

  async function save() {
    setSaving(true);
    try {
      await patchScreeningTranslation(projectId, screening.id, { lang, question, options });
      toast("Translation saved", "success");
      onSaved();
    } catch {
      toast("Failed to save translation", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="screening-tr">
      <button className="screening-tr__toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "▾" : "▸"} 🌐 Translations
      </button>
      {open && (
        <div className="screening-tr__body">
          <div className="screening-tr__langs">
            {langs.map((l) => (
              <button
                key={l}
                className={`screening-tr__lang${l === lang ? " active" : ""}`}
                onClick={() => switchLang(l)}
              >
                {NATIVE[l] ?? l}
                {screening.translations?.[l] ? " ✓" : ""}
              </button>
            ))}
          </div>
          <label className="field-label">Question</label>
          <input className="field-input" value={question} onChange={(e) => setQuestion(e.target.value)} />
          <label className="field-label" style={{ marginTop: 8 }}>Options</label>
          {screening.options.map((canonical, i) => (
            <div key={i} className="screening-tr__opt">
              <span className="screening-tr__canonical">{canonical}</span>
              <input
                className="field-input"
                value={options[i] ?? ""}
                onChange={(e) => setOptions((prev) => prev.map((o, oi) => (oi === i ? e.target.value : o)))}
              />
            </div>
          ))}
          <button className="btn btn-primary btn-sm" style={{ marginTop: 10 }} disabled={saving} onClick={save}>
            {saving ? "Saving…" : `Save ${NATIVE[lang] ?? lang}`}
          </button>
        </div>
      )}
    </div>
  );
}
