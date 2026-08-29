import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  createTextStimulus,
  deleteStimulus,
  uploadStimulusImage,
  type StimulusResponse,
} from "../api/projects";
import { getErrorMessage } from "../utils/errorMessages";

/**
 * The study's stimulus library: the artefacts participants are shown during
 * the interview (pack shots, ad creative, screen mockups, written concepts).
 *
 * Kept out of ProjectDetail.tsx, which is long enough already.
 */
export function StimulusLibrary({
  projectId,
  stimuli,
  onChange,
  readOnly = false,
}: {
  projectId: string;
  stimuli: StimulusResponse[];
  onChange: (next: StimulusResponse[]) => void;
  readOnly?: boolean;
}) {
  const { t } = useTranslation("project");
  const { t: tCommon } = useTranslation("common");
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTextForm, setShowTextForm] = useState(false);
  const [draft, setDraft] = useState({ name: "", body: "", caption: "", ai_description: "" });

  async function handleFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const created = await uploadStimulusImage(projectId, file, {
        // The filename is a usable default label; the researcher can rename it.
        name: file.name.replace(/\.[^.]+$/, "") || t("stimulus.untitled"),
      });
      onChange([...stimuli, created]);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleCreateText() {
    if (!draft.name.trim() || !draft.body.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createTextStimulus(projectId, {
        name: draft.name.trim(),
        body: draft.body.trim(),
        caption: draft.caption.trim() || null,
        ai_description: draft.ai_description.trim() || null,
      });
      onChange([...stimuli, created]);
      setDraft({ name: "", body: "", caption: "", ai_description: "" });
      setShowTextForm(false);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(asset: StimulusResponse) {
    const warning =
      asset.question_count > 0
        ? t("stimulus.deleteAttachedConfirm", { count: asset.question_count })
        : t("stimulus.deleteConfirm");
    if (!window.confirm(warning)) return;
    setBusy(true);
    setError(null);
    try {
      await deleteStimulus(projectId, asset.id);
      onChange(stimuli.filter((a) => a.id !== asset.id));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stimulus-library">
      <div className="stimulus-library__head">
        <div>
          <h4 className="stimulus-library__title">{t("stimulus.title")}</h4>
          <p className="stimulus-library__hint">{t("stimulus.hint")}</p>
        </div>
        {!readOnly && (
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              {t("stimulus.addImage")}
            </button>
            <button
              className="btn btn-secondary btn-sm"
              disabled={busy}
              onClick={() => setShowTextForm((v) => !v)}
            >
              {t("stimulus.addText")}
            </button>
          </div>
        )}
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        style={{ display: "none" }}
        onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
      />

      {error && <div className="error-banner" role="alert">{error}</div>}

      {showTextForm && !readOnly && (
        <div className="stimulus-library__form">
          <input
            className="field-input"
            placeholder={t("stimulus.namePlaceholder")}
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <textarea
            className="field-input"
            rows={4}
            placeholder={t("stimulus.bodyPlaceholder")}
            value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })}
          />
          <input
            className="field-input"
            placeholder={t("stimulus.captionPlaceholder")}
            value={draft.caption}
            onChange={(e) => setDraft({ ...draft, caption: e.target.value })}
          />
          <input
            className="field-input"
            placeholder={t("stimulus.aiDescriptionPlaceholder")}
            value={draft.ai_description}
            onChange={(e) => setDraft({ ...draft, ai_description: e.target.value })}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn-primary btn-sm"
              disabled={busy || !draft.name.trim() || !draft.body.trim()}
              onClick={handleCreateText}
            >
              {tCommon("save")}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowTextForm(false)}>
              {tCommon("cancel")}
            </button>
          </div>
        </div>
      )}

      {stimuli.length === 0 ? (
        <p className="stimulus-library__empty">{t("stimulus.empty")}</p>
      ) : (
        <ul className="stimulus-library__list">
          {stimuli.map((a) => (
            <li key={a.id} className="stimulus-library__item">
              {a.kind === "image" && a.url ? (
                <img src={a.url} alt="" className="stimulus-library__thumb" />
              ) : (
                <div className="stimulus-library__thumb stimulus-library__thumb--text" aria-hidden="true">
                  {t("stimulus.textBadge")}
                </div>
              )}
              <div className="stimulus-library__meta">
                <span className="stimulus-library__name">{a.name}</span>
                <span className="stimulus-library__usage">
                  {a.question_count > 0
                    ? t("stimulus.usedOn", { count: a.question_count })
                    : t("stimulus.unused")}
                </span>
              </div>
              {!readOnly && (
                <button
                  className="btn btn-ghost btn-xs"
                  disabled={busy}
                  onClick={() => handleDelete(a)}
                >
                  {tCommon("delete")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Attach one library asset to one guide question. Rendered inside the
 * expanded question card in the Setup tab.
 */
export function StimulusPicker({
  stimuli,
  value,
  onSelect,
  disabled = false,
}: {
  stimuli: StimulusResponse[];
  value: string | null | undefined;
  onSelect: (stimulusId: string | null) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation("project");

  if (stimuli.length === 0) {
    return <p className="stimulus-picker__empty">{t("stimulus.pickerEmpty")}</p>;
  }

  return (
    <select
      className="field-input stimulus-picker"
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => onSelect(e.target.value || null)}
      aria-label={t("stimulus.pickerLabel")}
    >
      <option value="">{t("stimulus.pickerNone")}</option>
      {stimuli.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name}
        </option>
      ))}
    </select>
  );
}
