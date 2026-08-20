/**
 * Dependency-free funnel analytics.
 *
 * Events are POSTed to our own backend (`/telemetry/event`), which
 * re-emits them into the same `analytics event=...` log stream as the
 * server-side milestones. No third-party SDK, no cookie, no cross-site
 * identifier, and nothing to add to `connect-src` — which is also why
 * this needs no consent banner.
 *
 * The backend keeps a closed list of accepted event names; adding one
 * here without adding it there is a silent no-op.
 */

import { getAttribution } from "./attribution";

// A bored user clicking around must not be able to spam the endpoint,
// and a render loop must not be able to either.
const MAX_EVENTS_PER_SESSION = 60;
let sent = 0;
const firedOnce = new Set<string>();

export type AnalyticsEvent =
  | "page_view"
  | "cta_signup_click"
  | "pricing_viewed"
  | "pricing_interval_toggled"
  | "newsletter_submit"
  | "analysis_viewed";

interface TrackOptions {
  /** Which instance of a repeated control fired this ("hero", "nav", ...). */
  location?: string;
  /** Fire at most once per page load, keyed on event + location. */
  once?: boolean;
}

export function track(event: AnalyticsEvent, opts: TrackOptions = {}): void {
  try {
    if (sent >= MAX_EVENTS_PER_SESSION) return;

    const key = `${event}:${opts.location ?? ""}`;
    if (opts.once) {
      if (firedOnce.has(key)) return;
      firedOnce.add(key);
    }
    sent += 1;

    const attribution = getAttribution() ?? {};
    const payload = JSON.stringify({
      event,
      location: opts.location,
      path: window.location.pathname.slice(0, 200),
      // Only useful on the entry pageview, and it is the one field that
      // could carry a long tracking URL, so cap it hard.
      referrer:
        event === "page_view" ? document.referrer.slice(0, 300) || undefined : undefined,
      lang: localStorage.getItem("qp_language")?.slice(0, 5) || undefined,
      ...attribution,
    });

    // keepalive so a click that immediately navigates away still reports;
    // raw fetch so this never touches the axios auth/refresh interceptor.
    fetch("/api/telemetry/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Analytics must never break a click handler.
  }
}

let lastPath: string | null = null;

/**
 * Fire one `page_view` for the current SPA route and reset the
 * once-per-page guards.
 *
 * Guarded on the path rather than on effect runs, so React StrictMode's
 * double-invoked effects in dev don't double-count, and neither does a
 * re-render triggered by a query-string change.
 */
export function trackPageView(): void {
  const path = window.location.pathname;
  if (path === lastPath) return;
  lastPath = path;
  firedOnce.clear();
  track("page_view");
}
