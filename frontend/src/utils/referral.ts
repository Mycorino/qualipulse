// Affiliate referral attribution.
//
// Referral links point at the marketing page (/?ref=code), but signup happens
// several clicks later (and, for Google SSO, across an OAuth round-trip that
// drops query params). So the code is persisted in localStorage on first
// touch and read back at signup time, with a 60-day attribution window.

const STORAGE_KEY = "qp_ref";
const ATTRIBUTION_WINDOW_MS = 60 * 24 * 60 * 60 * 1000; // 60 days

const CODE_RE = /^[a-z0-9_-]{3,50}$/;

/** Persist ?ref= from the current URL, if present and well-formed. First touch wins. */
export function captureRefFromUrl(): void {
  try {
    const code = new URLSearchParams(window.location.search).get("ref")?.trim().toLowerCase();
    if (!code || !CODE_RE.test(code)) return;
    if (getStoredRefCode()) return; // first-touch attribution
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ code, at: Date.now() }));
  } catch {
    // Storage unavailable (private mode, etc.) — attribution is best-effort.
  }
}

/** The stored referral code, or undefined if absent/expired/malformed. */
export function getStoredRefCode(): string | undefined {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return undefined;
    const { code, at } = JSON.parse(raw) as { code?: string; at?: number };
    if (!code || !CODE_RE.test(code) || !at || Date.now() - at > ATTRIBUTION_WINDOW_MS) {
      localStorage.removeItem(STORAGE_KEY);
      return undefined;
    }
    return code;
  } catch {
    return undefined;
  }
}
