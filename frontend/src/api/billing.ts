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
