import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { acceptInvitation, previewInvitation, InvitationPreview } from "../api/team";
import { useAuth } from "../hooks/useAuth";

export default function AcceptInvitation() {
  const { t } = useTranslation(["settings", "common"]);
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();

  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError(t("team.accept.missingToken"));
      setLoading(false);
      return;
    }
    previewInvitation(token)
      .then(setPreview)
      .catch((err) => {
        const msg =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          t("team.accept.invalidToken");
        setError(msg);
      })
      .finally(() => setLoading(false));
  }, [token, t]);

  async function handleAccept() {
    if (!token) return;
    setAccepting(true);
    setError(null);
    try {
      await acceptInvitation(token);
      navigate("/dashboard?joined=1");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("team.accept.failed");
      setError(msg);
    } finally {
      setAccepting(false);
    }
  }

  if (loading) {
    return (
      <div className="dashboard-page">
        <p className="muted-text">{t("common:loading")}</p>
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      <div className="settings-card" style={{ maxWidth: 520, margin: "48px auto" }}>
        <h1 className="dashboard-title" style={{ marginTop: 0 }}>
          {t("team.accept.title")}
        </h1>

        {error && <p className="error-text">{error}</p>}

        {preview && !error && (
          <>
            <p style={{ lineHeight: 1.6 }}>
              {preview.inviter_name
                ? t("team.accept.invitedByNamed", {
                    inviter: preview.inviter_name,
                    workspace: preview.workspace_name,
                    role: t(`team.roles.${preview.role}`),
                  })
                : t("team.accept.invitedAnon", {
                    workspace: preview.workspace_name,
                    role: t(`team.roles.${preview.role}`),
                  })}
            </p>
            <p style={{ fontSize: 13, color: "var(--text-tertiary)" }}>
              {t("team.accept.sentTo", { email: preview.email })}
            </p>

            {isAuthenticated ? (
              <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
                <button
                  className="btn btn-primary"
                  disabled={accepting}
                  onClick={handleAccept}
                >
                  {accepting ? t("team.accept.joining") : t("team.accept.joinCta")}
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => navigate("/dashboard")}
                >
                  {t("common:cancel")}
                </button>
              </div>
            ) : (
              <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 8 }}>
                <p style={{ fontSize: 14, color: "var(--text-secondary)" }}>
                  {t("team.accept.needLogin")}
                </p>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    className="btn btn-primary"
                    onClick={() =>
                      navigate(
                        `/login?redirect=${encodeURIComponent(`/team/accept?token=${token}`)}`
                      )
                    }
                  >
                    {t("team.accept.signIn")}
                  </button>
                  <button
                    className="btn btn-ghost"
                    onClick={() =>
                      navigate(
                        `/signup?redirect=${encodeURIComponent(`/team/accept?token=${token}`)}`
                      )
                    }
                  >
                    {t("team.accept.createAccount")}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
