import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

/**
 * DemoTour — click-through guided tour of the seeded demo study.
 *
 * The tour never drives the app for the user. It starts as a callout on
 * the Studies home pointing at the demo study row (DemoStudyCallout); the
 * user clicks the row themselves to open it. Inside the study, "go" steps
 * highlight the real tab buttons and wait for the user's own click before
 * advancing, and "describe" steps ring a specific element with a small
 * card placed next to it — no full-screen backdrop, the page stays
 * scrollable and interactive throughout.
 *
 * Handoff: onboarding lands on /dashboard?tour=1 → StudyList shows the
 * callout and arms sessionStorage (DEMO_TOUR_ARMED_KEY) → the user opens
 * the demo study → ProjectDetail mounts DemoTour. Completion or skip
 * writes DEMO_TOUR_DONE_KEY so it never re-triggers; the demo banner's
 * "Replay tour" (?tour=1 on the project page) overrides the done flag.
 */

export const DEMO_TOUR_DONE_KEY = "qp_demo_tour_done";
export const DEMO_TOUR_ARMED_KEY = "qp_demo_tour_armed";
const DEMO_TOUR_PHASE_KEY = "qp_demo_tour_phase";

/**
 * The tour runs in two phases. "study" is the main arc — home → workspace →
 * interview round. "memo" is the capstone after the interview-round finale:
 * back on the Studies home, ringing the cross-study decision memo card so
 * the user opens its print-ready report. Phase gates which surface's coach
 * marks are live, so nothing double-fires when the user revisits a page.
 */
export type DemoTourPhase = "study" | "memo";

export function getDemoTourPhase(): DemoTourPhase {
  return sessionStorage.getItem(DEMO_TOUR_PHASE_KEY) === "memo" ? "memo" : "study";
}

export function setDemoTourPhase(phase: DemoTourPhase) {
  sessionStorage.setItem(DEMO_TOUR_PHASE_KEY, phase);
}

export function armDemoTour() {
  sessionStorage.setItem(DEMO_TOUR_ARMED_KEY, "1");
  setDemoTourPhase("study");
}

/** Armed by the Studies-home callout and not yet completed/skipped. */
export function isDemoTourArmed(): boolean {
  return (
    sessionStorage.getItem(DEMO_TOUR_ARMED_KEY) === "1" &&
    localStorage.getItem(DEMO_TOUR_DONE_KEY) !== "1"
  );
}

/** Complete or dismiss the tour everywhere — it never re-triggers. */
export function skipDemoTour() {
  localStorage.setItem(DEMO_TOUR_DONE_KEY, "1");
  sessionStorage.removeItem(DEMO_TOUR_ARMED_KEY);
  sessionStorage.removeItem(DEMO_TOUR_PHASE_KEY);
}

type TourTab = "overview" | "setup" | "responses" | "analysis";

interface TourStep {
  key: string;
  /** Tab this step lives on. */
  tab: TourTab;
  /** Describe steps: element to ring. Falls back to the tab's panel. */
  anchor?: string;
  /** Go steps: highlight this tab's button and wait for the user to click it. */
  clickTab?: TourTab;
}

const STEPS: TourStep[] = [
  { key: "overviewHero", tab: "overview", anchor: "#isection-panel-overview .project-hero-strip" },
  { key: "overviewStats", tab: "overview", anchor: "#isection-panel-overview .stats-row" },
  { key: "overviewLink", tab: "overview", anchor: '[data-tour="overview-link"]' },
  { key: "goSetup", tab: "overview", clickTab: "setup" },
  { key: "setupGuide", tab: "setup", anchor: "#isection-panel-setup .guide-section" },
  { key: "goResponses", tab: "setup", clickTab: "responses" },
  { key: "responsesList", tab: "responses", anchor: "#isection-panel-responses .participants-list" },
  { key: "goAnalysis", tab: "responses", clickTab: "analysis" },
  { key: "analysisReport", tab: "analysis", anchor: "#isection-panel-analysis .analysis-report" },
  { key: "finale", tab: "analysis" },
];

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

function rectsEqual(a: Rect | null, b: Rect | null): boolean {
  if (a === null || b === null) return a === b;
  return a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height;
}

/**
 * Track the viewport rect of the first element matching `selector`,
 * re-measuring through layout shifts, scrolling and async data loads.
 * Scrolls the element into view once per selector change.
 */
function useAnchorRect(selector: string | null, fallbackSelector?: string): Rect | null {
  const [rect, setRect] = useState<Rect | null>(null);
  useEffect(() => {
    if (!selector) {
      setRect(null);
      return;
    }
    let cancelled = false;
    let scrolled = false;
    const measure = () => {
      if (cancelled) return;
      const el =
        document.querySelector(selector) ??
        (fallbackSelector ? document.querySelector(fallbackSelector) : null);
      if (!el) {
        setRect(null);
        return;
      }
      if (!scrolled) {
        scrolled = true;
        const r = el.getBoundingClientRect();
        // Bring the anchor comfortably into view. Absolute target instead of
        // scrollIntoView/scrollBy: it never tucks the anchor under sticky
        // headers, handles anchors taller than the viewport, and stays
        // idempotent when StrictMode double-runs the effect.
        if (r.top < 80 || r.top > window.innerHeight - 240) {
          window.scrollTo({
            top: Math.max(window.scrollY + r.top - 120, 0),
            behavior: "smooth",
          });
        }
      }
      const r = el.getBoundingClientRect();
      const next = { top: r.top, left: r.left, width: r.width, height: r.height };
      setRect((prev) => (rectsEqual(prev, next) ? prev : next));
    };
    const raf = requestAnimationFrame(measure);
    const interval = window.setInterval(measure, 300);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      clearInterval(interval);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [selector, fallbackSelector]);
  return rect;
}

/**
 * Place the card adjacent to the anchor — below if it fits, above
 * otherwise. Returns null when neither fits (caller docks the card so it
 * never sits on top of the anchored content).
 */
function useCardPos(
  rect: Rect | null,
  cardRef: React.RefObject<HTMLDivElement>,
  contentKey: string,
): { top: number; left: number } | null {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  useLayoutEffect(() => {
    const card = cardRef.current;
    if (!rect || !card) {
      setPos(null);
      return;
    }
    const gap = 14;
    const ch = card.offsetHeight;
    const cw = card.offsetWidth;
    let top: number;
    if (rect.top + rect.height + gap + ch <= window.innerHeight - 16) {
      top = rect.top + rect.height + gap;
    } else if (rect.top - gap - ch >= 16) {
      top = rect.top - gap - ch;
    } else {
      setPos(null);
      return;
    }
    const left = Math.min(Math.max(rect.left, 16), Math.max(window.innerWidth - cw - 16, 16));
    setPos({ top, left });
  }, [rect, cardRef, contentKey]);
  return pos;
}

interface DemoTourProps {
  /** The instrument tab currently active — the tour advances on the user's own tab clicks. */
  currentTab: TourTab;
  goToTab: (tab: TourTab) => void;
  onExit: () => void;
}

export default function DemoTour({ currentTab, goToTab, onExit }: DemoTourProps) {
  const { t } = useTranslation("project");
  const navigate = useNavigate();
  const [stepIndex, setStepIndex] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);
  const step = STEPS[stepIndex];
  const isFinale = step.key === "finale";

  const finish = useCallback(() => {
    skipDemoTour();
    onExit();
  }, [onExit]);

  // The tour always starts on Overview (relevant for banner replays from
  // another tab). A fresh interview-round run is always the "study" phase —
  // the finale flips it to "memo" right before handing back to the home.
  useEffect(() => {
    setDemoTourPhase("study");
    goToTab("overview");
    window.scrollTo({ top: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // React to the user's own tab clicks: a "go" step advances when its
  // target tab opens; on a describe step, wandering to another tab jumps
  // to that tab's step so the card never talks about an invisible panel.
  const stepIndexRef = useRef(stepIndex);
  useEffect(() => {
    stepIndexRef.current = stepIndex;
  }, [stepIndex]);
  const mountedRef = useRef(false);
  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const current = STEPS[stepIndexRef.current];
    if (current.clickTab) {
      if (currentTab === current.clickTab) setStepIndex(stepIndexRef.current + 1);
      return;
    }
    if (current.tab !== currentTab) {
      const idx = STEPS.findIndex((s) => !s.clickTab && s.tab === currentTab);
      if (idx >= 0) setStepIndex(idx);
    }
  }, [currentTab]);

  const selector = step.clickTab ? `#isection-tab-${step.clickTab}` : step.anchor ?? null;
  const rect = useAnchorRect(selector, step.clickTab ? undefined : `#isection-panel-${step.tab}`);
  const pos = useCardPos(rect, cardRef, step.key);

  // Focus follows the expected action: the real tab button on "go" steps,
  // the card's primary button otherwise.
  useEffect(() => {
    if (step.clickTab) {
      document.getElementById(`isection-tab-${step.clickTab}`)?.focus();
    } else {
      cardRef.current?.querySelector<HTMLButtonElement>("[data-tour-primary]")?.focus();
    }
  }, [stepIndex, step.clickTab]);

  // Esc skips from anywhere. No focus trap — the page stays interactive.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [finish]);

  const goBack = () => {
    for (let i = stepIndex - 1; i >= 0; i--) {
      if (!STEPS[i].clickTab) {
        if (STEPS[i].tab !== currentTab) goToTab(STEPS[i].tab);
        setStepIndex(i);
        return;
      }
    }
  };

  const title = t(`tour.${step.key}_title`);
  const body = t(`tour.${step.key}_body`);
  const docked = pos === null;

  return (
    <div className="demo-tour">
      {rect && (
        <div
          className={`demo-tour__ring${step.clickTab ? " demo-tour__ring--pulse" : ""}`}
          style={{
            top: rect.top - 6,
            left: rect.left - 6,
            width: rect.width + 12,
            height: rect.height + 12,
          }}
        />
      )}

      <div
        className={`demo-tour__card${docked ? " demo-tour__card--dock" : ""}`}
        style={docked ? undefined : { top: pos.top, left: pos.left }}
        ref={cardRef}
        role="dialog"
        aria-label={title}
      >
        {!isFinale && (
          <span className="demo-tour__progress">
            {t("tour.stepOf", { current: stepIndex + 1, total: STEPS.length - 1 })}
          </span>
        )}
        <h2 className="demo-tour__title">{title}</h2>
        <p className="demo-tour__body">{body}</p>
        {step.clickTab && <p className="demo-tour__click-hint">☝︎ {t("tour.clickHint")}</p>}
        <div className="demo-tour__actions">
          {isFinale ? (
            <>
              <button type="button" className="btn btn-ghost btn-sm" onClick={finish}>
                {t("tour.finale_cta_explore")}
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                data-tour-primary
                onClick={() => {
                  // Bridge to the capstone: hand back to the Studies home
                  // where the decision-memo callout picks up (phase=memo).
                  setDemoTourPhase("memo");
                  navigate("/dashboard");
                }}
              >
                {t("tour.finale_cta_memo")} →
              </button>
            </>
          ) : (
            <>
              <button type="button" className="demo-tour__skip" onClick={finish}>
                {t("tour.skip")}
              </button>
              <div className="demo-tour__nav">
                {stepIndex > 0 && (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={goBack}>
                    {t("tour.back")}
                  </button>
                )}
                {!step.clickTab && (
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    data-tour-primary
                    onClick={() => setStepIndex((i) => i + 1)}
                  >
                    {t("tour.next")}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

interface DemoCalloutProps {
  /** Element to ring — the callout renders nothing until it's in the DOM. */
  selector: string;
  eyebrow: string;
  title: string;
  body: string;
  clickHint: string;
  skipLabel: string;
  /** Called after skipDemoTour() has run — hide any local state. */
  onSkip: () => void;
  /**
   * Optional in-card primary action. Used by the capstone memo callout so
   * the report opens from the card itself (not only the ringed control).
   * The handler runs first, then skipDemoTour() + onSkip() end the tour.
   */
  primaryLabel?: string;
  onPrimary?: () => void;
}

/**
 * DemoCallout — a single coach mark used on the way *to* something (Studies
 * home row, workspace tab, interview round card, the decision memo). It
 * rings a real click target and waits: the user's own click navigates or
 * opens, nothing is automatic. Renders nothing until the anchor is in the
 * DOM, so a seeding/loading delay just means the callout pops in when the
 * target does.
 */
export function DemoCallout({
  selector,
  eyebrow,
  title,
  body,
  clickHint,
  skipLabel,
  onSkip,
  primaryLabel,
  onPrimary,
}: DemoCalloutProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const rect = useAnchorRect(selector);
  const pos = useCardPos(rect, cardRef, title);

  if (!rect) return null;

  const end = () => {
    skipDemoTour();
    onSkip();
  };

  return (
    <div className="demo-tour">
      <div
        className="demo-tour__ring demo-tour__ring--pulse"
        style={{
          top: rect.top - 6,
          left: rect.left - 6,
          width: rect.width + 12,
          height: rect.height + 12,
        }}
      />
      <div
        className={`demo-tour__card${pos === null ? " demo-tour__card--dock" : ""}`}
        style={pos === null ? undefined : { top: pos.top, left: pos.left }}
        ref={cardRef}
        role="dialog"
        aria-label={title}
      >
        <span className="demo-tour__progress">{eyebrow}</span>
        <h2 className="demo-tour__title">{title}</h2>
        <p className="demo-tour__body">{body}</p>
        <p className="demo-tour__click-hint">☝︎ {clickHint}</p>
        <div className="demo-tour__actions">
          <button type="button" className="demo-tour__skip" onClick={end}>
            {skipLabel}
          </button>
          {primaryLabel && onPrimary && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              data-tour-primary
              onClick={() => {
                onPrimary();
                end();
              }}
            >
              {primaryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
