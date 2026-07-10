import client from "../api/client";

const PAID_PLANS = ["exploration", "team", "agency"];

/**
 * When the user picked a paid plan on the pricing page ("Choose Team" etc.,
 * stashed in localStorage by Signup.tsx), create a Stripe Checkout session
 * for it and return the redirect URL — so paid intent is charged upfront
 * instead of silently landing in the free-trial flow.
 *
 * Returns null when no paid plan was chosen or the session can't be created
 * (billing not configured in dev, network error). Callers fall through to
 * the normal /welcome flow; if the user cancels checkout they land there
 * too and onboarding bootstraps the free trial as usual.
 */
export async function checkoutUrlForSelectedPlan(): Promise<string | null> {
  const plan = localStorage.getItem("qp_selected_plan");
  if (!plan || !PAID_PLANS.includes(plan)) return null;
  const rawInterval = localStorage.getItem("qp_selected_interval");
  const interval = rawInterval === "annual" ? "annual" : "monthly";
  try {
    const { data } = await client.post<{ checkout_url: string }>("/billing/checkout", {
      plan_id: plan,
      billing_interval: interval,
      success_url: `${window.location.origin}/welcome?checkout=success`,
      cancel_url: `${window.location.origin}/welcome`,
    });
    return data.checkout_url || null;
  } catch {
    return null;
  }
}
