/**
 * "Start a churn study" on the marketing site → /signup?template=customer-churn.
 *
 * The template id has to survive the signup form, the Google OAuth round-trip
 * (which drops query params) and the onboarding wizard, so it is stashed in
 * localStorage the same way the pricing-page plan choice is
 * (`qp_selected_plan`). Consumed once, by whichever surface the user reaches
 * first after signing in: the onboarding handoff for a new account, the
 * studies home for a returning one.
 *
 * Bounded TTL: a visitor who clicked a card, abandoned signup and comes back
 * weeks later should not get a study created under them. A week leaves room
 * for the email-verification step that gates study creation (see
 * templateStudy.ts), which can happen a day or two after signup.
 */
const KEY = "qp_pending_template";
const TTL_MS = 7 * 24 * 60 * 60 * 1000;
const ID_RE = /^[a-z0-9-]{3,40}$/;

export function setPendingTemplate(id: string): void {
  if (!ID_RE.test(id)) return;
  try {
    localStorage.setItem(KEY, JSON.stringify({ id, at: Date.now() }));
  } catch {
    /* storage unavailable: the deep link degrades to a normal signup */
  }
}

export function getPendingTemplate(): string | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { id?: unknown; at?: unknown };
    const id = typeof parsed.id === "string" ? parsed.id : "";
    const at = typeof parsed.at === "number" ? parsed.at : 0;
    if (!ID_RE.test(id) || Date.now() - at > TTL_MS) {
      localStorage.removeItem(KEY);
      return null;
    }
    return id;
  } catch {
    return null;
  }
}

export function clearPendingTemplate(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
