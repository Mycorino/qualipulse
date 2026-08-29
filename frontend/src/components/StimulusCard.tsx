import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Stimulus } from "../api/interviews";

/**
 * The artefact a participant is shown while a question is on screen:
 * a pack shot, ad creative, screen mockup, or a written concept statement.
 *
 * Images open full-screen on tap. Concept tests live or die on whether the
 * participant can actually read the small print on a pack, and phone screens
 * are small.
 */
export default function StimulusCard({ stimulus }: { stimulus: Stimulus | null | undefined }) {
  const { t } = useTranslation("interview");
  const [zoomed, setZoomed] = useState(false);

  // A new question means a new artefact: never leave the previous one
  // expanded over the next question.
  useEffect(() => {
    setZoomed(false);
  }, [stimulus?.id]);

  useEffect(() => {
    if (!zoomed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomed(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed]);

  if (!stimulus) return null;

  const caption = stimulus.caption?.trim();

  if (stimulus.kind === "text") {
    if (!stimulus.body?.trim()) return null;
    return (
      <div className="stimulus-card stimulus-card-text">
        <p className="stimulus-text-body">{stimulus.body}</p>
        {caption && <p className="stimulus-caption">{caption}</p>}
      </div>
    );
  }

  if (!stimulus.url) return null;

  return (
    <>
      <div className="stimulus-card stimulus-card-image">
        <button
          type="button"
          className="stimulus-image-button"
          onClick={() => setZoomed(true)}
          aria-label={t("interview.stimulusZoom")}
        >
          <img
            src={stimulus.url}
            /* Deliberately neutral: describing the artefact would tell the
               participant what to think about it before they have looked. */
            alt={t("interview.stimulusAlt")}
            className="stimulus-image"
          />
        </button>
        {caption && <p className="stimulus-caption">{caption}</p>}
      </div>

      {zoomed && (
        <div
          className="stimulus-zoom-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={t("interview.stimulusAlt")}
          onClick={() => setZoomed(false)}
        >
          <img src={stimulus.url} alt={t("interview.stimulusAlt")} className="stimulus-zoom-image" />
          <button
            type="button"
            className="btn btn-secondary stimulus-zoom-close"
            onClick={() => setZoomed(false)}
          >
            {t("interview.stimulusClose")}
          </button>
        </div>
      )}
    </>
  );
}
