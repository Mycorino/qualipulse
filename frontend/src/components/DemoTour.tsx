import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

/**
 * DemoTour — guided spotlight tour of the seeded demo project.
 *
 * Rendered by ProjectDetail when the URL carries `?tour=1` on a demo
 * project (onboarding hands off there via StudyList). The tour drives the
 * real page — each step switches to an actual tab and spotlights its
 * panel — so the user sees live seeded data, not screenshots. Ends on a
 * "create your own study" CTA back on the Studies home.
 *
 * No tour library: six fixed steps over stable panel ids, one cutout div
 * (box-shadow dim trick) and a fixed caption card. Intro and finale reuse
 * the app's modal classes.
 */

export const DEMO_TOUR_DONE_KEY = "qp_demo_tour_done";

type TourTab = "overview" | "setup" | "responses" | "analysis";

interface TourStep {
  key: string;
  /** Tab to activate + spotlight; undefined → centered modal step. */
  tab?: TourTab;
}

const STEPS: TourStep[] = [
  { key: "intro" },
  { key: "overview", tab: "overview" },
  { key: "setup", tab: "setup" },
  { key: "responses", tab: "responses" },
  { key: "analysis", tab: "analysis" },
  { key: "finale" },
];

interface SpotlightRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

interface DemoTourProps {
  goToTab: (tab: TourTab) => void;
  onExit: () => void;
}

export default function DemoTour({ goToTab, onExit }: DemoTourProps) {
  const { t } = useTranslation("project");
  const navigate = useNavigate();
  const [stepIndex, setStepIndex] = useState(0);
  const [spotlight, setSpotlight] = useState<SpotlightRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const step = STEPS[stepIndex];

  const finish = useCallback(() => {
    localStorage.setItem(DEMO_TOUR_DONE_KEY, "1");
    onExit();
  }, [onExit]);

  // Activate the step's tab, then track its panel while content mounts and
  // async data (participants, analysis) reflows the layout.
  useEffect(() => {
    if (!step.tab) {
      setSpotlight(null);
      return;
    }
    goToTab(step.tab);
    window.scrollTo({ top: 0 });
    let cancelled = false;
    const measure = () => {
      if (cancelled) return;
      const el = document.getElementById(`isection-panel-${step.tab}`);
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const pad = 8;
      const top = Math.max(rect.top - pad, 0);
      setSpotlight({
        top,
        left: Math.max(rect.left - pad, 0),
        width: Math.min(rect.width + pad * 2, window.innerWidth),
        height: Math.min(rect.height + pad * 2, window.innerHeight - top - 16),
      });
    };
    const raf = requestAnimationFrame(measure);
    const interval = window.setInterval(measure, 400);
    window.addEventListener("resize", measure);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      clearInterval(interval);
      window.removeEventListener("resize", measure);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepIndex]);

  // Keyboard: Esc skips, focus stays inside the card.
  useEffect(() => {
    const card = cardRef.current;
    card?.querySelector<HTMLButtonElement>("[data-tour-primary]")?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        finish();
        return;
      }
      if (e.key !== "Tab" || !card) return;
      const focusables = card.querySelectorAll<HTMLElement>("button, a[href]");
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [stepIndex, finish]);

  const title = t(`tour.${step.key}_title`);
  const body = t(`tour.${step.key}_body`);

  // Intro + finale: plain centered modals (reuse app modal styles).
  if (!step.tab) {
    const isIntro = step.key === "intro";
    return (
      <div className="modal-overlay demo-tour" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-content demo-tour__modal" ref={cardRef}>
          <h2 className="demo-tour__title">{title}</h2>
          <p className="demo-tour__body">{body}</p>
          <div className="demo-tour__actions">
            {isIntro ? (
              <>
                <button type="button" className="btn btn-ghost" onClick={finish}>
                  {t("tour.skip")}
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  data-tour-primary
                  onClick={() => setStepIndex(1)}
                >
                  {t("tour.start")}
                </button>
              </>
            ) : (
              <>
                <button type="button" className="btn btn-ghost" onClick={finish}>
                  {t("tour.finale_cta_explore")}
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  data-tour-primary
                  onClick={() => {
                    localStorage.setItem(DEMO_TOUR_DONE_KEY, "1");
                    navigate("/dashboard?new=1");
                  }}
                >
                  {t("tour.finale_cta_create")} →
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="demo-tour" role="dialog" aria-modal="true" aria-label={title}>
      {/* Dim everything except the spotlit panel; blocks page interaction
          so the tour stays linear. */}
      {spotlight ? (
        <div
          className="demo-tour__cutout"
          style={{
            top: spotlight.top,
            left: spotlight.left,
            width: spotlight.width,
            height: spotlight.height,
          }}
        />
      ) : (
        <div className="demo-tour__backdrop" />
      )}

      <div className="demo-tour__card" ref={cardRef}>
        <span className="demo-tour__progress">
          {t("tour.stepOf", { current: stepIndex, total: STEPS.length - 2 })}
        </span>
        <h2 className="demo-tour__title">{title}</h2>
        <p className="demo-tour__body">{body}</p>
        <div className="demo-tour__actions">
          <button type="button" className="demo-tour__skip" onClick={finish}>
            {t("tour.skip")}
          </button>
          <div className="demo-tour__nav">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setStepIndex((i) => i - 1)}
            >
              {t("tour.back")}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              data-tour-primary
              onClick={() => setStepIndex((i) => i + 1)}
            >
              {t("tour.next")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
