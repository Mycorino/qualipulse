/**
 * Copilot teaser tier — the proactive "little popup" on the collapsed dock.
 *
 * Users told us they never opened the copilot because they didn't know what
 * it does. The teaser fixes discoverability: when the dock is collapsed and
 * there's something genuinely worth doing (a fresh nudge, or an actionable
 * next-best-action), a small speech bubble appears above the FAB and its CTA
 * runs the suggestion — one click, and the agent demonstrates itself.
 *
 * This module is only the persistence layer (what was already teased, and
 * whether the panel was ever opened). The frequency rules live in
 * ResearchCopilotPanel:
 * - one teaser per surface mount, shown after a short delay;
 * - a given suggestion (keyed by surface + NBA/nudge id) teases ONCE ever —
 *   the resolver's id changes as the study advances, so each new stage earns
 *   one fresh popup and an ignored one never nags again;
 * - auto-hides after a while; the persistent dock chip keeps the suggestion.
 */

const STORE_KEY = "copilot_teaser_v1";
const SEEN_CAP = 200;

interface TeaserStore {
  /** Teaser keys (`{surfaceId}:{kind}:{id}`) that were already shown. */
  seen: string[];
  /** The user has opened the copilot panel at least once (any surface). */
  openedPanel: boolean;
}

function loadStore(): TeaserStore {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<TeaserStore>;
      return {
        seen: Array.isArray(parsed.seen) ? parsed.seen : [],
        openedPanel: parsed.openedPanel === true,
      };
    }
  } catch {
    // corrupt / unavailable storage — start clean
  }
  return { seen: [], openedPanel: false };
}

function saveStore(store: TeaserStore): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    // storage full / disabled — teasers degrade to once-per-mount
  }
}

/** Has this exact suggestion already been teased? */
export function teaserSeen(key: string): boolean {
  return loadStore().seen.includes(key);
}

/** Record that a suggestion was teased — it never pops again. */
export function markTeaserSeen(key: string): void {
  const store = loadStore();
  if (store.seen.includes(key)) return;
  store.seen.push(key);
  if (store.seen.length > SEEN_CAP) {
    store.seen = store.seen.slice(-SEEN_CAP);
  }
  saveStore(store);
}

/** Has the user ever opened the copilot panel? Gates the first-run
 *  explainer line ("I'm your research copilot…") on the teaser. */
export function hasOpenedCopilot(): boolean {
  return loadStore().openedPanel;
}

export function markCopilotOpened(): void {
  const store = loadStore();
  if (store.openedPanel) return;
  store.openedPanel = true;
  saveStore(store);
}
