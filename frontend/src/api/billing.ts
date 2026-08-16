import client from "./client";

export interface CreditUsage {
  included_credits: number;
  purchased_credits: number;
  rollover_credits: number;
  used_credits: number;
  overage_credits: number;
  available_credits: number;
  period_start: string | null;
  period_end: string | null;
}

export interface Invoice {
  id: string;
  number: string | null;
  created: string;
  amount_paid: number;
  currency: string;
  status: string | null;
  hosted_invoice_url: string | null;
  invoice_pdf: string | null;
}

/**
 * Past invoices for the workspace, newest first.
 *
 * Empty for accounts with no Stripe customer yet (the endpoint returns
 * `[]` rather than erroring), so the caller only has to handle "none".
 */
export async function getInvoices(): Promise<Invoice[]> {
  try {
    const { data } = await client.get<Invoice[]>("/billing/invoices");
    return data;
  } catch {
    return [];
  }
}

/**
 * Current-period credit balance for the workspace.
 *
 * Returns `null` for legacy-plan accounts (the endpoint 404s) — callers
 * treat null as "credits don't apply here", so credit-based gating is
 * simply skipped.
 */
export async function getCreditUsage(): Promise<CreditUsage | null> {
  try {
    const { data } = await client.get<CreditUsage>("/billing/usage");
    return data;
  } catch {
    return null;
  }
}

/**
 * Dunning check: true when the workspace has a Stripe subscription whose
 * last payment failed (status "past_due", set by the Stripe webhook).
 * Legacy/trial accounts without Stripe state always return false, so the
 * global banner never shows for them.
 */
export async function isBillingPastDue(): Promise<boolean> {
  try {
    const { data } = await client.get<{
      status?: string;
      stripe_customer_id?: string | null;
      plan?: { subscription_status?: string; is_legacy?: boolean } | null;
    }>("/billing/status");
    if (!data?.stripe_customer_id) return false;
    // Credit-native accounts carry the truth on plan.subscription_status;
    // legacy Stripe accounts on the top-level company status.
    const subStatus =
      data.plan && !data.plan.is_legacy ? data.plan.subscription_status : data.status;
    return subStatus === "past_due";
  } catch {
    return false;
  }
}

/** Canonical plan-display block emitted by GET /billing/status. */
export interface PlanDisplay {
  plan_name: string;
  is_trial: boolean;
  status: string;
}

/**
 * Current plan for lightweight chrome (hub rail). Returns `null` when the
 * account has no credit-native display block (legacy plans) — callers hide
 * the plan line rather than guessing.
 */
export async function getPlanDisplay(): Promise<PlanDisplay | null> {
  try {
    const { data } = await client.get<{ display?: PlanDisplay }>("/billing/status");
    return data?.display ?? null;
  } catch {
    return null;
  }
}
