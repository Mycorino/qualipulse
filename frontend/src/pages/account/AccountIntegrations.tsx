import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { updateSlackWebhook, testSlackWebhook } from "../../api/auth";
import { useAccount, SLACK_INTEGRATION_ENABLED } from "./accountContext";

export default function AccountIntegrations() {
  const { t } = useTranslation(["settings", "common"]);
  const { me, setMe } = useAccount();
  const [slackUrl, setSlackUrl] = useState(me?.slack_webhook_url ?? "");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    setSaving(true);
    try {
      const trimmed = slackUrl.trim();
      await updateSlackWebhook(trimmed || null);
      setMe((m) => (m ? { ...m, slack_webhook_url: trimmed || null } : m));
      setMessage({
        type: "success",
        text: trimmed ? t("integrations.slack.saved") : t("integrations.slack.cleared"),
      });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("integrations.slack.saveError");
      setMessage({ type: "error", text: msg });
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setMessage(null);
    setTesting(true);
    try {
      await testSlackWebhook(slackUrl.trim() || null);
      setMessage({ type: "success", text: t("integrations.slack.testSent") });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("integrations.slack.testFailed");
      setMessage({ type: "error", text: msg });
    } finally {
      setTesting(false);
    }
  }

  // Slack is paused — keep deep links working by bouncing to Account home.
  if (!SLACK_INTEGRATION_ENABLED) {
    return <Navigate to="/account" replace />;
  }

  return (
    <div className="settings-section">
      <div className="settings-card">
        <h2 className="settings-section-title">{t("integrations.slack.title")}</h2>
        <p className="muted-text" style={{ marginTop: -4, marginBottom: 16 }}>
          {t("integrations.slack.description")}
        </p>

        <ol style={{ fontSize: 14, color: "var(--text-secondary)", paddingLeft: 20, marginBottom: 16, lineHeight: 1.7 }}>
          <li>
            {t("integrations.slack.step1")}{" "}
            <a
              href="https://api.slack.com/messaging/webhooks"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "var(--brand-500)" }}
            >
              api.slack.com/messaging/webhooks
            </a>
          </li>
          <li>{t("integrations.slack.step2")}</li>
          <li>{t("integrations.slack.step3")}</li>
        </ol>

        <form className="auth-form" style={{ maxWidth: 560 }} onSubmit={handleSave}>
          <div>
            <label className="field-label">{t("integrations.slack.urlLabel")}</label>
            <input
              className="field-input"
              type="url"
              value={slackUrl}
              onChange={(e) => setSlackUrl(e.target.value)}
              placeholder="https://hooks.slack.com/services/T.../B.../..."
              autoComplete="off"
            />
            <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 6 }}>
              {t("integrations.slack.urlHint")}
            </p>
          </div>

          {message && (
            <p
              style={{
                fontSize: 14,
                color: message.type === "success" ? "var(--success)" : "var(--danger)",
                margin: 0,
              }}
            >
              {message.text}
            </p>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? t("profile.saving") : t("integrations.slack.save")}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={testing || !slackUrl.trim()}
              onClick={handleTest}
            >
              {testing ? t("integrations.slack.testing") : t("integrations.slack.test")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
