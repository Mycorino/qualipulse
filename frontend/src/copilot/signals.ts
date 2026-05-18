/**
 * Copilot nudge tier — change detection (Nudge project, N1).
 *
 * A nudge is event-driven: "something changed while you were looking
 * elsewhere." Distinct from the always-on NBA chip, which is state-driven
 * ("here's what to do next").
 *
 * Detection is client-side: the app already refetches instrument state, so
 * we keep a per-scope snapshot in localStorage and diff each fetch against
 * it. A localStorage baseline means the diff works across a tab close /
 * reopen — the highest-value case (you return and something finished).
 *
 * No nudge ever fires for a change on the surface the researcher is
 * currently watching — see `suppressed` below.
 */

export type NudgeEvent = "analysis_ready" | "analysis_stale" | "data_milestone";

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
}

interface SignalStore {
  lastSeen: Record<string, ProjectSnapshot>;
  nudges: Nudge[]; // active, undismissed — persisted so a reload can't drop one
  dismissed: string[];
}

const STORE_KEY = "copilot_signals_v1";
const DISMISSED_CAP = 200;
/** Below this many completed interviews, analysis isn't worth running. */
const ANALYSE_THRESHOLD = 3;

function loadStore(): SignalStore {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<SignalStore>;
      return {
        lastSeen: parsed.lastSeen ?? {},
        nudges: parsed.nudges ?? [],
        dismissed: parsed.dismissed ?? [],
      };
    }
  } catch {
    // corrupt / unavailable storage — start clean
  }
  return { lastSeen: {}, nudges: [], dismissed: [] };
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
  if (event === "data_milestone") return section === "responses";
  // analysis_ready / analysis_stale
  return section === "analysis";
}

const NUDGE_TEXT: Record<NudgeEvent, (n: number) => string> = {
  analysis_ready: () => "Your analysis is ready to review.",
  data_milestone: (n) =>
    `You've got ${n} completed interviews — enough to analyse.`,
  analysis_stale: (n) =>
    `${n} new interview(s) since the last analysis — worth refreshing.`,
};
const NUDGE_TONE: Record<NudgeEvent, Nudge["tone"]> = {
  analysis_ready: "positive",
  data_milestone: "positive",
  analysis_stale: "neutral",
};

function makeNudge(
  event: NudgeEvent,
  scopeId: string,
  idSuffix: string | number,
  n: number,
): Nudge {
  return {
    id: `${scopeId}:${event}:${idSuffix}`,
    event,
    scopeId,
    text: NUDGE_TEXT[event](n),
    tone: NUDGE_TONE[event],
    createdAt: Date.now(),
  };
}

/**
 * Diff this scope's snapshot against the stored baseline, append any new
 * nudges, advance the baseline, and return the active nudge list for the
 * scope. `activeSection` suppresses nudges for the surface in view.
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
          curr.analysisParticipantCount,
        ),
      );
    }

    if (
      prev.completedCount < ANALYSE_THRESHOLD &&
      curr.completedCount >= ANALYSE_THRESHOLD
    ) {
      candidates.push(
        makeNudge("data_milestone", scopeId, ANALYSE_THRESHOLD, curr.completedCount),
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
        makeNudge("analysis_stale", scopeId, curr.completedCount, currGap),
      );
    }

    for (const nudge of candidates) {
      if (suppressed(nudge.event, activeSection)) continue;
      if (store.dismissed.includes(nudge.id)) continue;
      if (store.nudges.some((n) => n.id === nudge.id)) continue;
      store.nudges.push(nudge);
    }
  }

  store.lastSeen[scopeId] = curr;
  saveStore(store);
  return store.nudges.filter((n) => n.scopeId === scopeId);
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
