import client from "../api/client";

export interface BillingConfig {
  stripe_publishable_key: string | null;
  embedded_checkout: boolean;
}

const DISABLED: BillingConfig = { stripe_publishable_key: null, embedded_checkout: false };

let cached: Promise<BillingConfig> | null = null;

/**
 * Fetch (once per page load) whether the backend supports Stripe Embedded
 * Checkout. On any error, report it as disabled — callers then use the
 * hosted checkout.stripe.com redirect, which is the pre-embedded behaviour.
 */
export function getBillingConfig(): Promise<BillingConfig> {
  if (!cached) {
    cached = client
      .get<BillingConfig>("/billing/config")
      .then((r) => r.data)
      .catch(() => {
        cached = null; // transient failure — allow a retry on the next call
        return DISABLED;
      });
  }
  return cached;
}
