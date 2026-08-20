/**
 * First-touch marketing attribution.
 *
 * Signup happens several clicks and, for Google SSO, a full OAuth
 * round-trip after the visitor lands, and both of those drop query
 * params. So the utm_* trio is stashed in localStorage on first touch and
 * replayed at signup, where the backend stamps it onto the Company row.
 * Same shape and same 60-day window as the affiliate code in
 * `referral.ts` — the two solve the identical problem.
 *
 * No cookie, no third-party host, no cross-site identifier: this is only
 * ever read back on our own signup call.
 */

const STORAGE_KEY = "qp_attribution";
const ATTRIBUTION_WINDOW_MS = 60 * 24 * 60 * 60 * 1000; // 60 days

export interface Attribution {
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
}

/** Trim to the charset the backend accepts, so nothing is silently dropped later. */
function clean(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  const text = value
    .replace(/[^A-Za-z0-9 ._\-/:+@]/g, "")
    .trim()
    .slice(0, 100);
  return text || undefined;
}

/**
 * Persist attribution from the current URL. First touch wins.
 *
 * Untagged traffic falls back to the referring hostname so organic and
 * social visits are still attributable without every inbound link having
 * to carry UTM params. A direct visit stores nothing at all, which means
 * "first touch" really reads as "first *attributable* touch": someone who
 * arrives direct today and comes back through a campaign link next week
 * is credited to that campaign rather than to nothing.
 */
export function captureAttributionFromUrl(): void {
  try {
    if (getAttribution()) return;

    const params = new URLSearchParams(window.location.search);
    let source = clean(params.get("utm_source"));
    let medium = clean(params.get("utm_medium"));
    const campaign = clean(params.get("utm_campaign"));

    if (!source && document.referrer) {
      try {
        const host = new URL(document.referrer).hostname.replace(/^www\./, "");
        if (host && host !== window.location.hostname) {
          source = clean(host);
          medium = medium ?? "referral";
        }
      } catch {
        // Malformed referrer — ignore, direct traffic is a fine default.
      }
    }

    if (!source && !medium && !campaign) return;

    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ s: source, m: medium, c: campaign, at: Date.now() })
    );
  } catch {
    // Storage unavailable (private mode, etc.) — attribution is best-effort.
  }
}

/** Stored first-touch attribution, or undefined if absent/expired. */
export function getAttribution(): Attribution | undefined {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return undefined;
    const { s, m, c, at } = JSON.parse(raw) as {
      s?: string;
      m?: string;
      c?: string;
      at?: number;
    };
    if (!at || Date.now() - at > ATTRIBUTION_WINDOW_MS) {
      localStorage.removeItem(STORAGE_KEY);
      return undefined;
    }
    if (!s && !m && !c) return undefined;
    return { utm_source: s, utm_medium: m, utm_campaign: c };
  } catch {
    return undefined;
  }
}
