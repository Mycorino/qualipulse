/**
 * Copilot nudge tier — change detection (Nudge project, N1 + N2).
 *
 * A nudge is event-driven: "something changed while you were looking
 * elsewhere." Distinct from the always-on NBA chip, which is state-driven
 * ("here's what to do next").
 *
 * Detection is client-side: the app already refetches state, so we keep a
 * per-scope snapshot in localStorage and diff each fetch against it. A
 * localStorage baseline means the diff works across a tab close / reopen —
 * the highest-value case (you return and something finished).
 *
 * No nudge fires for a change on the surface the researcher is currently
 * watching (`suppressed`); a nudge for a surface they then visit
 * auto-expires; and every nudge expires after 24h.
 */

export type NudgeEvent =
  | "analysis_ready"
  | "analysis_stale"
  | "data_milestone"
  | "quality_flag"
  | "study_report_ready";

export interface Nudge {
  /** Stable id — encodes the event + triggering value, so the same
   *  occurrence never re-fires but a genuinely new one does. */
  id: string;
  event: NudgeEvent;
  scopeId: string;
  text: string;
  tone: "positive" | "neutral" | "caution";
  createdAt: number;
}

/** The diff-relevant slice of an interview project's state. */
export interface ProjectSnapshot {
  analysisStatus: string; // "none" | "generating" | "ready" | "failed"
  completedCount: number;
  analysisParticipantCount: number;
  lowQualityCount: number;
}

/** The diff-relevant slice of a study, for home-page detection. */
export interface StudySnapshot {
  hasReport: boolean;
}

interface SignalStore {
  lastSeen: Record<string, ProjectSnapshot>;
  studyLastSeen: Record<string, StudySnapshot>;
  nudges: Nudge[]; // active, undismissed — persisted so a reload can't drop one
  dismissed: string[];
}

const STORE_KEY = "copilot_signals_v2";
const DISMISSED_CAP = 200;
/** Below this many completed interviews, analysis isn't worth running. */
const ANALYSE_THRESHOLD = 3;
/** Every nudge auto-expires after this long. */
const NUDGE_TTL_MS = 24 * 60 * 60 * 1000;

const NUDGE_TONE: Record<NudgeEvent, Nudge["tone"]> = {
  analysis_ready: "positive",
  data_milestone: "positive",
  analysis_stale: "neutral",
  quality_flag: "caution",
  study_report_ready: "positive",
};

function loadStore(): SignalStore {
  let store: SignalStore = {
    lastSeen: {},
    studyLastSeen: {},
    nudges: [],
    dismissed: [],
  };
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<SignalStore>;
      store = {
        lastSeen: parsed.lastSeen ?? {},
        studyLastSeen: parsed.studyLastSeen ?? {},
        nudges: parsed.nudges ?? [],
        dismissed: parsed.dismissed ?? [],
      };
    }
  } catch {
    // corrupt / unavailable storage — start clean
  }
  // Prune nudges older than the TTL on every load.
  const cutoff = Date.now() - NUDGE_TTL_MS;
  store.nudges = store.nudges.filter((n) => n.createdAt >= cutoff);
  return store;
}

function saveStore(store: SignalStore): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    // storage full / disabled — nudges degrade to in-memory only
  }
}

/** Is a change on `event`'s home surface the one being watched right now? */
function suppressed(event: NudgeEvent, activeSection?: string): boolean {
  const section = (activeSection ?? "").toLowerCase();
  if (event === "data_milestone" || event === "quality_flag") {
    return section === "responses";
  }
  if (event === "analysis_ready" || event === "analysis_stale") {
    return section === "analysis";
  }
  return false;
}

function makeNudge(
  event: NudgeEvent,
  scopeId: string,
  idSuffix: string | number,
  text: string,
): Nudge {
  return {
    id: `${scopeId}:${event}:${idSuffix}`,
    event,
    scopeId,
    text,
    tone: NUDGE_TONE[event],
    createdAt: Date.now(),
  };
}

/** Add a freshly-detected nudge to the store unless dismissed / duplicate. */
function addNudge(store: SignalStore, nudge: Nudge): void {
  if (store.dismissed.includes(nudge.id)) return;
  if (store.nudges.some((n) => n.id === nudge.id)) return;
  store.nudges.push(nudge);
}

/**
 * Diff this round's snapshot against the stored baseline, append any new
 * nudges, advance the baseline, and return the active nudge list for the
 * scope. `activeSection` suppresses (and auto-expires) nudges for the
 * surface in view.
 */
export function detectProjectNudges(
  scopeId: string,
  curr: ProjectSnapshot,
  activeSection?: string,
): Nudge[] {
  const store = loadStore();
  const prev = store.lastSeen[scopeId];

  // First sighting of this scope — set a baseline, never nudge.
  if (prev) {
    const candidates: Nudge[] = [];

    if (prev.analysisStatus !== "ready" && curr.analysisStatus === "ready") {
      candidates.push(
        makeNudge(
          "analysis_ready",
          scopeId,
          curr.analysisParticipantCount,
          "Your analysis is ready to review.",
        ),
      );
    }
    if (
      prev.completedCount < ANALYSE_THRESHOLD &&
      curr.completedCount >= ANALYSE_THRESHOLD
    ) {
      candidates.push(
        makeNudge(
          "data_milestone",
          scopeId,
          ANALYSE_THRESHOLD,
          `You've got ${curr.completedCount} completed interviews — enough to analyse.`,
        ),
      );
    }
    const prevGap = prev.completedCount - prev.analysisParticipantCount;
    const currGap = curr.completedCount - curr.analysisParticipantCount;
    if (
      prevGap < ANALYSE_THRESHOLD &&
      currGap >= ANALYSE_THRESHOLD &&
      curr.analysisStatus === "ready"
    ) {
      candidates.push(
        makeNudge(
          "analysis_stale",
          scopeId,
          curr.completedCount,
          `${currGap} new interviews since the last analysis — worth refreshing.`,
        ),
      );
    }
    if (curr.lowQualityCount > prev.lowQualityCount) {
      candidates.push(
        makeNudge(
          "quality_flag",
          scopeId,
          curr.lowQualityCount,
          "A low-quality interview just came in — worth a look.",
        ),
      );
    }

    for (const nudge of candidates) {
      if (suppressed(nudge.event, activeSection)) continue;
      addNudge(store, nudge);
    }
  }

  // Auto-expire: a nudge for a surface the researcher is now on has been
  // seen — drop it (without recording a dismissal).
  store.nudges = store.nudges.filter(
    (n) => !(n.scopeId === scopeId && suppressed(n.event, activeSection)),
  );

  store.lastSeen[scopeId] = curr;
  saveStore(store);
  return store.nudges.filter((n) => n.scopeId === scopeId);
}

/** A study seen on the home page, for `study_report_ready` detection. */
export interface StudyReportInput {
  id: string;
  name: string;
  hasReport: boolean;
}

/**
 * Diff the studies list against the stored baseline and emit a nudge for
 * any study that gained a report since last seen. Returns all active
 * workspace nudges (study-scoped).
 */
export function detectWorkspaceNudges(studies: StudyReportInput[]): Nudge[] {
  const store = loadStore();
  const ids = new Set(studies.map((s) => s.id));

  for (const s of studies) {
    const prev = store.studyLastSeen[s.id];
    if (prev && !prev.hasReport && s.hasReport) {
      addNudge(
        store,
        makeNudge(
          "study_report_ready",
          s.id,
          "report",
          `“${s.name}” — the analysis report is ready.`,
        ),
      );
    }
    store.studyLastSeen[s.id] = { hasReport: s.hasReport };
  }

  saveStore(store);
  return store.nudges.filter(
    (n) => n.event === "study_report_ready" && ids.has(n.scopeId),
  );
}

/** Dismiss a nudge — it never returns. */
export function dismissNudge(id: string): void {
  const store = loadStore();
  store.nudges = store.nudges.filter((n) => n.id !== id);
  if (!store.dismissed.includes(id)) {
    store.dismissed.push(id);
    if (store.dismissed.length > DISMISSED_CAP) {
      store.dismissed = store.dismissed.slice(-DISMISSED_CAP);
    }
  }
  saveStore(store);
}

/** The active, undismissed nudges for one scope. */
export function activeNudgesFor(scopeId: string): Nudge[] {
  return loadStore().nudges.filter((n) => n.scopeId === scopeId);
}
