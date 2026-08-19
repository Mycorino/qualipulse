import client from "./client";

/**
 * Recontact API client — mirrors backend/app/routers/panel_recontact.py.
 *
 * The workspace's pool of past participants who consented to be recontacted,
 * plus per-study invitations with a derived funnel (sent → started →
 * completed).
 */

export type BlockedReason = "already_participated" | "already_invited" | "cooldown";

export interface PoolProfile {
  profile_id: number;
  email: string;
  first_name: string | null;
  preferred_language: string | null;
  age_range: string | null;
  country: string | null;
  job_function: string | null;
  seniority: string | null;
  industry: string | null;
  company_size: string | null;
  last_active: string | null;
  consent_at: string | null;
  /** Present on invite-candidates rows: why this person can't be invited. */
  blocked_reason?: BlockedReason | null;
  /** Present on workspace-panel rows. */
  studies_participated?: number;
  interviews_completed?: number;
  invites_sent?: number;
  last_invited_at?: string | null;
}

export interface InviteCandidatesResponse {
  candidates: PoolProfile[];
  cooldown_days: number;
  batch_max: number;
  daily_limit: number;
  daily_remaining: number;
}

export interface InviteRow {
  id: string;
  email: string;
  sent_at: string | null;
  language: string | null;
  status: "sent" | "started" | "completed";
}

export interface InviteFunnel {
  invites: InviteRow[];
  summary: { invited: number; started: number; completed: number };
}

export interface SendInvitesResult {
  sent: number;
  skipped: { profile_id: number; reason: string }[];
}

export interface WorkspacePanelResponse {
  profiles: PoolProfile[];
  stats: { pool_size: number; invited_30d: number };
}

export async function getInviteCandidates(projectId: string): Promise<InviteCandidatesResponse> {
  const { data } = await client.get(`/projects/${projectId}/invite-candidates`);
  return data;
}

export async function getProjectInvites(projectId: string): Promise<InviteFunnel> {
  const { data } = await client.get(`/projects/${projectId}/invites`);
  return data;
}

export async function sendInvites(
  projectId: string,
  profileIds: number[],
): Promise<SendInvitesResult> {
  const { data } = await client.post(`/projects/${projectId}/invites`, {
    profile_ids: profileIds,
  });
  return data;
}

export async function getWorkspacePanel(): Promise<WorkspacePanelResponse> {
  const { data } = await client.get("/workspace/panel");
  return data;
}

/** Public — participant-facing opt-out from the invite email footer. */
export async function panelOptOut(token: string): Promise<void> {
  await client.post("/panel/opt-out", { token });
}
