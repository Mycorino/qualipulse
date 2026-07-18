import { useOutletContext } from "react-router-dom";
import type { CompanyResponse } from "../../api/auth";

// Slack notifications are paused while the integration is under review.
// Flip to true to restore the Integrations tab, the home card and the
// /account/integrations route — backend endpoints are untouched.
export const SLACK_INTEGRATION_ENABLED = false;

// ── Shared billing types (consumed by AccountHome + AccountBilling) ──────────

export interface BillingStatus {
  tier: string;
  tier_name: string;
  status: string;
  limits: {
    max_projects: number;
    max_participants_per_project: number;
    ai_analysis: boolean;
    export_csv: boolean;
    team_members: number;
  };
  usage: {
    interview_count: number;
    storage_bytes: number;
  };
  // Credits-aware fields. Null for accounts that haven't been backfilled —
  // fall back to the legacy tier shape.
  plan?: {
    id: string;
    name: string;
    is_legacy: boolean;
    is_custom: boolean;
    is_trial?: boolean;
    monthly_price_cents: number | null;
    annual_price_cents: number | null;
    billing_interval: string | null;
    subscription_status: string;
    current_period_start: string | null;
    current_period_end: string | null;
    trial_end: string | null;
    cancel_at_period_end: boolean;
    overage_enabled: boolean;
  } | null;
  credits?: {
    included_credits: number;
    purchased_credits: number;
    rollover_credits: number;
    used_credits: number;
    overage_credits: number;
    available_credits: number;
    period_start: string | null;
    period_end: string | null;
  } | null;
  // Canonical display block for credit-native accounts — one source of truth
  // so the UI stops mixing the legacy tier with the subscription status.
  display?: {
    plan_name: string;
    is_trial: boolean;
    status: string;
    show_trial_end: boolean;
  } | null;
}

export interface Plan {
  id: string;
  name: string;
  description: string;
  monthly_price_cents: number | null;
  annual_price_cents: number | null;
  currency: string;
  included_credits: number | null;
  credit_period: string;
  max_editors: number | null;
  overage_price_cents: number | null;
  is_custom: boolean;
  entitlements: Record<string, unknown>;
}

export interface CreditPack {
  id: string;
  name: string;
  credits: number;
  price_cents: number;
  currency: string;
  description: string;
  available: boolean;
}

// ── Outlet context shared by every /account sub-route ────────────────────────

export interface AccountOutletContext {
  me: CompanyResponse | null;
  setMe: React.Dispatch<React.SetStateAction<CompanyResponse | null>>;
  billing: BillingStatus | null;
  plans: Plan[];
  packs: CreditPack[];
  /** Re-fetch /auth/me + /billing/status (e.g. after verifying email). */
  reload: () => void;
}

export function useAccount(): AccountOutletContext {
  return useOutletContext<AccountOutletContext>();
}
