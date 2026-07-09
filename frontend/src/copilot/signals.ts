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
  | "study_report_ready"
  | "memo_ready"
  | "memo_stale";

export interface Nudge {
  /** Stable id — encodes the event + triggering value, so the same
   *  occurrence never re-fires but a genuinely new one does. */
  id: string;
  event: NudgeEvent;
  scopeId: string;
  /** i18n key in the `dashboard` namespace (+ interpolation params).
   *  Stored as a key so persisted nudges re-localize on language switch. */
  textKey: string;
  textParams?: Record<string, string | number>;
  /** Legacy field — nudges persisted before the i18n refactor. */
  text?: string;
  tone: "positive" | "neutral" | "caution";
  createdAt: number;
}

/** The diff-relevant slice of an interview project's state. */
export interface ProjectSnapshot {
  analysisStatus: string; // "none" | "generating" | "ready" | "failed"
  completedCount: number;
  analysisParticipantCount: number;
  lowQualityCount: number;
  /** Version of the latest analysis — disambiguates re-runs that happen
   *  to cover the same participant count (id-reuse would otherwise keep
   *  a re-run permanently suppressed after one dismissal). */
  analysisVersion?: number;
}

/** The diff-relevant slice of a study, for home-page detection. */
export interface StudySnapshot {
  hasReport: boolean;
}

/** The diff-relevant slice of a decision memo, for home-page detection. */
export interface MemoSnapshot {
  status: string; // "generating" | "ready" | "failed"
  stale: boolean;
}

interface SignalStore {
  lastSeen: Record<string, ProjectSnapshot>;
  studyLastSeen: Record<string, StudySnapshot>;
  memoLastSeen: Record<string, MemoSnapshot>;
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
  memo_ready: "positive",
  memo_stale: "neutral",
};

function loadStore(): SignalStore {
  let store: SignalStore = {
    lastSeen: {},
    studyLastSeen: {},
    memoLastSeen: {},
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
        memoLastSeen: parsed.memoLastSeen ?? {},
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
  textKey: string,
  textParams?: Record<string, string | number>,
): Nudge {
  return {
    id: `${scopeId}:${event}:${idSuffix}`,
    event,
    scopeId,
    textKey,
    textParams,
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
          `${curr.analysisVersion ?? 0}-${curr.analysisParticipantCount}`,
          "nudges.analysisReady",
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
          "nudges.dataMilestone",
          { count: curr.completedCount },
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
          "nudges.analysisStale",
          { count: currGap },
        ),
      );
    }
    if (curr.lowQualityCount > prev.lowQualityCount) {
      candidates.push(
        makeNudge(
          "quality_flag",
          scopeId,
          curr.lowQualityCount,
          "nudges.qualityFlag",
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

/** A decision memo seen on the home page, for memo_ready / memo_stale. */
export interface MemoInput {
  id: string;
  name: string;
  status: string; // "generating" | "ready" | "failed"
  stale: boolean;
}

/**
 * Diff the studies list (and, when provided, the decision-memo list)
 * against the stored baseline and emit a nudge for any study that gained
 * a report, any memo that finished generating, and any memo that went
 * stale since last seen. Returns all active workspace nudges.
 */
export function detectWorkspaceNudges(
  studies: StudyReportInput[],
  memos: MemoInput[] = [],
): Nudge[] {
  const store = loadStore();
  const studyIds = new Set(studies.map((s) => s.id));
  const memoIds = new Set(memos.map((m) => m.id));

  for (const s of studies) {
    const prev = store.studyLastSeen[s.id];
    if (prev && !prev.hasReport && s.hasReport) {
      addNudge(
        store,
        makeNudge(
          "study_report_ready",
          s.id,
          "report",
          "nudges.studyReportReady",
          { name: s.name },
        ),
      );
    }
    store.studyLastSeen[s.id] = { hasReport: s.hasReport };
  }

  for (const m of memos) {
    const prev = store.memoLastSeen[m.id];
    if (prev) {
      if (prev.status !== "ready" && m.status === "ready") {
        addNudge(
          store,
          makeNudge("memo_ready", m.id, "ready", "nudges.memoReady", {
            name: m.name,
          }),
        );
      }
      if (m.status === "ready" && !prev.stale && m.stale) {
        addNudge(
          store,
          makeNudge("memo_stale", m.id, "stale", "nudges.memoStale", {
            name: m.name,
          }),
        );
      }
    }
    store.memoLastSeen[m.id] = { status: m.status, stale: m.stale };
  }

  saveStore(store);
  return store.nudges.filter(
    (n) =>
      (n.event === "study_report_ready" && studyIds.has(n.scopeId)) ||
      ((n.event === "memo_ready" || n.event === "memo_stale") &&
        memoIds.has(n.scopeId)),
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
