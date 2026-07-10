// Affiliate referral attribution.
//
// Affiliate links point at the landing page (`/?ref=code`), but signup
// happens several clicks later — so the code must be persisted, not just
// read from the signup URL. First-touch wins within the TTL window.

const STORAGE_KEY = "qp_ref_code";
const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

/** Persist `?ref=` from the current URL, if present. Call on landing pages. */
export function captureRefFromUrl(): void {
  try {
    const ref = new URLSearchParams(window.location.search).get("ref");
    if (!ref) return;
    const code = ref.trim().toLowerCase();
    if (!code || getStoredRefCode()) return; // first touch wins
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ code, ts: Date.now() }));
  } catch {
    // Storage unavailable (private mode etc.) — attribution is best-effort.
  }
}

/** The persisted referral code, or undefined if absent/expired. */
export function getStoredRefCode(): string | undefined {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return undefined;
    const { code, ts } = JSON.parse(raw) as { code?: string; ts?: number };
    if (!code || !ts || Date.now() - ts > TTL_MS) {
      localStorage.removeItem(STORAGE_KEY);
      return undefined;
    }
    return code;
  } catch {
    return undefined;
  }
}

/** Drop the persisted code once a signup has been attributed. */
export function clearStoredRefCode(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
