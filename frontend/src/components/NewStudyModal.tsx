import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createSurvey } from "../api/surveys";
import { createProject } from "../api/projects";
import { useToast } from "./Toast";

/**
 * NewStudyModal — Sprint 18, the "What do you want to learn?" angle picker.
 *
 * The deliberate entry point into a Study. The researcher names the
 * study and picks one of three angles:
 *
 *   - Survey a lot of people   → quanti-only start
 *   - Talk to people in depth  → quali-only start
 *   - Both (recommended)       → hybrid start
 *
 * The pick is NOT a hard commitment — it only decides which instrument
 * gets created first. A survey study can grow an interview round later
 * via the Screener Bridge; an interview study can grow a validation
 * survey. The angle just routes to the right builder.
 *
 * Mechanically there's no "create Study" call — Studies are auto-created
 * by the first instrument (Decision 8):
 *   - Survey / Both → POST /surveys/ (study auto-created) → survey editor
 *   - Interview     → /projects/new?name= (wizard creates the project,
 *                     study auto-created)
 */

type Angle = "survey" | "interview" | "both";

interface AngleCard {
  angle: Angle;
  icon: string;
  title: string;
  blurb: string;
  recommended?: boolean;
}

const ANGLES: AngleCard[] = [
  {
    angle: "survey",
    icon: "📊",
    title: "Survey a lot of people",
    blurb: "Start broad. Collect structured responses, see the patterns, size the problem.",
  },
  {
    angle: "interview",
    icon: "🎙",
    title: "Talk to people in depth",
    blurb: "Go deep. AI-moderated voice interviews that adapt to each participant.",
  },
  {
    angle: "both",
    icon: "📊🎙",
    title: "Both — start broad, then go deep",
    blurb: "Survey first, then interview the most interesting segments. The full mixed-methods loop.",
    recommended: true,
  },
];

export function NewStudyModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const go = async (angle: Angle) => {
    const studyName = name.trim();
    if (!studyName) return;
    setBusy(true);
    try {
      if (angle === "interview") {
        // Create the interview round directly (its Study auto-creates),
        // then drop into the workspace — the copilot drafts the guide.
        const project = await createProject({
          name: studyName,
          language: "en",
          questions: [],
        });
        navigate(`/projects/${project.id}?tab=setup`);
        return;
      }
      // survey + both → create the survey, which auto-creates the Study.
      const survey = await createSurvey({
        name: studyName,
        role: angle === "both" ? "screener" : "standalone",
      });
      navigate(`/surveys/${survey.id}/edit`);
    } catch {
      toast("Could not create the study", "error");
      setBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Start a new study"
      className="new-study-modal__overlay"
      onClick={onClose}
    >
      <div className="new-study-modal" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="new-study-modal__close"
          onClick={onClose}
          aria-label="Close"
        >
          ✕
        </button>

        <div className="new-study-modal__eyebrow">New study</div>
        <h2 className="new-study-modal__title">What do you want to learn?</h2>
        <p className="new-study-modal__sub">
          Name your study, then pick how to start. You can always add the other instrument
          later — the choice just decides what you build first.
        </p>

        <label className="new-study-modal__label" htmlFor="new-study-name">
          Study name
        </label>
        <input
          id="new-study-name"
          type="text"
          className="new-study-modal__name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Why new users churn"
          autoFocus
        />

        <div className="new-study-modal__angles">
          {ANGLES.map((a) => (
            <button
              key={a.angle}
              type="button"
              className={`new-study-modal__angle${a.recommended ? " new-study-modal__angle--recommended" : ""}`}
              onClick={() => go(a.angle)}
              disabled={busy || !name.trim()}
            >
              {a.recommended && (
                <span className="new-study-modal__badge">Recommended</span>
              )}
              <span className="new-study-modal__angle-icon" aria-hidden="true">
                {a.icon}
              </span>
              <span className="new-study-modal__angle-title">{a.title}</span>
              <span className="new-study-modal__angle-blurb">{a.blurb}</span>
            </button>
          ))}
        </div>

        {!name.trim() && (
          <p className="new-study-modal__hint">Enter a name to choose an angle.</p>
        )}
      </div>
    </div>
  );
}
