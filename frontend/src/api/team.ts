import client from "./client";

export type TeamRole = "owner" | "admin" | "editor" | "viewer";

export interface TeamMember {
  id: string;
  company_id: string;
  name: string;
  email: string;
  role: TeamRole;
  joined_at: string;
}

export interface TeamInvitation {
  id: string;
  email: string;
  role: TeamRole;
  expires_at: string;
  created_at: string;
}

export interface InvitationPreview {
  workspace_name: string;
  inviter_name: string | null;
  role: TeamRole;
  email: string;
  expires_at: string;
  already_member: boolean;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  role: TeamRole;
}

export async function listTeamMembers(): Promise<TeamMember[]> {
  const { data } = await client.get<TeamMember[]>("/team/members");
  return data;
}

export async function listTeamInvitations(): Promise<TeamInvitation[]> {
  const { data } = await client.get<TeamInvitation[]>("/team/invitations");
  return data;
}

export async function inviteTeamMember(email: string, role: TeamRole): Promise<TeamInvitation> {
  const { data } = await client.post<TeamInvitation>("/team/invite", { email, role });
  return data;
}

export async function revokeTeamInvitation(invitationId: string): Promise<void> {
  await client.delete(`/team/invitations/${invitationId}`);
}

export async function removeTeamMember(memberRowId: string): Promise<void> {
  await client.delete(`/team/members/${memberRowId}`);
}

export async function previewInvitation(token: string): Promise<InvitationPreview> {
  const { data } = await client.get<InvitationPreview>(`/team/invitations/preview/${token}`);
  return data;
}

export async function acceptInvitation(token: string): Promise<{ message: string; workspace_id: string }> {
  const { data } = await client.post<{ message: string; workspace_id: string }>(
    "/team/invitations/accept",
    { token }
  );
  return data;
}

export async function listMyWorkspaces(): Promise<WorkspaceSummary[]> {
  const { data } = await client.get<WorkspaceSummary[]>("/team/workspaces");
  return data;
}
