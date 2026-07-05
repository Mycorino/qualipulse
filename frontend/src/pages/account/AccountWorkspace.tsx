import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  listTeamMembers,
  listTeamInvitations,
  inviteTeamMember,
  revokeTeamInvitation,
  removeTeamMember,
  TeamMember,
  TeamInvitation,
  TeamRole,
} from "../../api/team";

export default function AccountWorkspace() {
  const { t, i18n } = useTranslation(["settings", "common"]);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [invites, setInvites] = useState<TeamInvitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<TeamRole>("editor");
  const [inviting, setInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [m, inv] = await Promise.all([
          listTeamMembers(),
          listTeamInvitations().catch(() => []),
        ]);
        setMembers(m);
        setInvites(inv);
      } catch {
        /* handled by interceptor */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const email = inviteEmail.trim();
    if (!email) return;
    setInviting(true);
    try {
      const invite = await inviteTeamMember(email, inviteRole);
      setInvites((prev) => [invite, ...prev.filter((p) => p.email !== email)]);
      setInviteEmail("");
      setSuccess(t("team.inviteSent", { email }));
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("team.inviteError");
      setError(msg);
    } finally {
      setInviting(false);
    }
  }

  async function handleRevoke(id: string) {
    try {
      await revokeTeamInvitation(id);
      setInvites((prev) => prev.filter((i) => i.id !== id));
    } catch {
      /* handled by interceptor */
    }
  }

  async function handleRemove(memberRowId: string) {
    if (memberRowId === "owner") return;
    if (!confirm(t("team.removeConfirm"))) return;
    try {
      await removeTeamMember(memberRowId);
      setMembers((prev) => prev.filter((m) => m.id !== memberRowId));
    } catch {
      /* handled by interceptor */
    }
  }

  return (
    <div className="settings-section">
      <div className="settings-card">
        <h2 className="settings-section-title">{t("team.inviteTitle")}</h2>
        <p className="muted-text" style={{ marginTop: -4, marginBottom: 16 }}>
          {t("team.inviteDescription")}
        </p>
        <form
          className="auth-form"
          style={{ maxWidth: 560, display: "flex", flexDirection: "column", gap: 12 }}
          onSubmit={handleInvite}
        >
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              className="field-input"
              type="email"
              placeholder={t("team.emailPlaceholder")}
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              required
              style={{ flex: 1, minWidth: 220 }}
            />
            <select
              className="field-input"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as TeamRole)}
              style={{ width: 140 }}
            >
              <option value="admin">{t("team.roles.admin")}</option>
              <option value="editor">{t("team.roles.editor")}</option>
              <option value="viewer">{t("team.roles.viewer")}</option>
            </select>
            <button className="btn btn-primary" type="submit" disabled={inviting}>
              {inviting ? t("team.inviting") : t("team.sendInvite")}
            </button>
          </div>
          {error && <p className="error-text" style={{ margin: 0 }}>{error}</p>}
          {success && <p style={{ color: "var(--success)", fontSize: 14, margin: 0 }}>{success}</p>}
        </form>
      </div>

      <div className="settings-card" style={{ marginTop: 20 }}>
        <h2 className="settings-section-title">{t("team.membersTitle")}</h2>
        {loading ? (
          <p className="muted-text">{t("common:loading")}</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {members.map((m) => (
              <div
                key={m.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 14px",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{m.name}</div>
                  <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>{m.email}</div>
                </div>
                <span className="badge" style={{ textTransform: "capitalize" }}>
                  {t(`team.roles.${m.role}`)}
                </span>
                {m.id !== "owner" && (
                  <button className="btn btn-ghost btn-sm" onClick={() => handleRemove(m.id)}>
                    {t("team.remove")}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {invites.length > 0 && (
        <div className="settings-card" style={{ marginTop: 20 }}>
          <h2 className="settings-section-title">{t("team.pendingTitle")}</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {invites.map((i) => (
              <div
                key={i.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 14px",
                  border: "1px dashed var(--border)",
                  borderRadius: 8,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{i.email}</div>
                  <div style={{ fontSize: 13, color: "var(--text-tertiary)" }}>
                    {t("team.invitedAs", { role: t(`team.roles.${i.role}`) })} ·{" "}
                    {t("team.expiresOn", { date: new Date(i.expires_at).toLocaleDateString(i18n.language) })}
                  </div>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => handleRevoke(i.id)}>
                  {t("team.revoke")}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
