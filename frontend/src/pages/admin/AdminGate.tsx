import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import axios from "axios";
import appClient from "../../api/client";

/**
 * The admin sign-in screen.
 *
 * Staff sign in to the app with their own account (password + 2FA like
 * anyone else), then step up here with a fresh authenticator code to mint a
 * 30-minute admin token. The token lives in React state only: never
 * localStorage / sessionStorage, so a script injection cannot lift it and a
 * page refresh simply asks for a new code.
 *
 * While ADMIN_ALLOW_SHARED_KEY is on server-side, the old shared-key form is
 * still reachable behind a collapsed link so nobody gets locked out during
 * the rollout. It disappears on its own once the flag is flipped.
 */

export interface AdminSession {
  token: string;
  identity: string;
  /** ms epoch. null on the legacy shared-key path (no expiry on our side). */
  expiresAt: number | null;
  via: "account" | "shared_key";
}

interface Me {
  email: string;
  is_admin?: boolean;
  totp_enabled?: boolean;
}

interface AuthConfig {
  shared_key_login: boolean;
  token_minutes: number;
}

export function AdminGate({
  onSession,
  notice,
}: {
  onSession: (s: AdminSession) => void;
  /** e.g. "Session expired" after a 401 on the panel. */
  notice?: string | null;
}) {
  const { t } = useTranslation("admin");
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = loading
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [legacyKey, setLegacyKey] = useState("");
  const [legacyName, setLegacyName] = useState("");

  useEffect(() => {
    let cancelled = false;
    axios
      .get<AuthConfig>("/api/admin/auth-config")
      .then((r) => !cancelled && setConfig(r.data))
      .catch(() => !cancelled && setConfig({ shared_key_login: false, token_minutes: 30 }));
    if (!localStorage.getItem("token")) {
      setMe(null);
    } else {
      appClient
        .get<Me>("/auth/me")
        .then((r) => !cancelled && setMe(r.data))
        .catch(() => !cancelled && setMe(null));
    }
    return () => {
      cancelled = true;
    };
  }, []);

  async function submitCode() {
    const trimmed = code.trim();
    if (!trimmed) return;
    setBusy(true);
    setError("");
    try {
      const r = await appClient.post<{ admin_token: string; expires_in: number; identity: string }>(
        "/admin/session",
        { code: trimmed },
      );
      onSession({
        token: r.data.admin_token,
        identity: r.data.identity,
        expiresAt: Date.now() + r.data.expires_in * 1000,
        via: "account",
      });
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      if (status === 429) setError(t("login.errorLocked", "Too many attempts. Try again in 15 minutes."));
      else if (detail === "admin_2fa_required") setError(t("login.error2faRequired", "Enable two-factor authentication on your account first."));
      else if (status === 401) setError(t("login.errorCode", "That code is not valid."));
      else if (status === 403) setError(t("login.errorNotAdmin", "This account is not an admin."));
      else setError(t("login.errorConnect"));
    } finally {
      setBusy(false);
    }
  }

  async function submitLegacy() {
    if (!legacyName.trim()) {
      setError(t("login.errorIdentityRequired"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await axios.get("/api/admin/stats", {
        headers: { Authorization: `Bearer ${legacyKey}`, "X-Admin-Identity": legacyName.trim() },
      });
      onSession({ token: legacyKey, identity: `shared-key:${legacyName.trim()}`, expiresAt: null, via: "shared_key" });
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setError(status === 401 || status === 403 ? t("login.errorInvalidKey") : t("login.errorConnect"));
    } finally {
      setBusy(false);
    }
  }

  const loading = me === undefined || config === null;
  const isAdmin = !!me?.is_admin;

  return (
    <div className="adm-gate">
      <div className="adm-gate__card">
        <div className="adm-gate__brand">
          <span className="adm-gate__logo">Q</span>
          <div>
            <h1>{t("login.title")}</h1>
            <p>{t("login.subtitle")}</p>
          </div>
        </div>

        {notice && <div className="adm-gate__notice">{notice}</div>}

        {loading ? (
          <p className="adm-gate__muted">{t("login.loading", "Checking your account…")}</p>
        ) : isAdmin && me ? (
          me.totp_enabled ? (
            <>
              <p className="adm-gate__who">
                {t("login.signedInAs", "Signed in as")} <b>{me.email}</b>
              </p>
              <label className="adm-gate__label" htmlFor="adm-code">
                {t("login.codeLabel", "Authenticator code")}
              </label>
              <input
                id="adm-code"
                className={`adm-gate__input adm-gate__input--code${error ? " is-error" : ""}`}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                placeholder="123 456"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitCode()}
              />
              <p className="adm-gate__hint">
                {t("login.codeHint", "A fresh code is required every time, even if you just signed in. The admin session lasts {{minutes}} minutes.", {
                  minutes: config?.token_minutes ?? 30,
                })}
              </p>
              {error && <p className="adm-gate__error">{error}</p>}
              <button className="adm-gate__btn" onClick={submitCode} disabled={busy || !code.trim()}>
                {busy ? t("login.opening", "Opening…") : t("login.openSession", "Open admin session")}
              </button>
            </>
          ) : (
            <>
              <p className="adm-gate__who">
                {t("login.signedInAs", "Signed in as")} <b>{me.email}</b>
              </p>
              <div className="adm-gate__block">
                <b>{t("login.need2faTitle", "Two-factor authentication is required")}</b>
                <p>{t("login.need2faBody", "Admin access needs an authenticator app on your account. Set it up once, then come back here.")}</p>
                <Link className="adm-gate__btn adm-gate__btn--link" to="/account/security">
                  {t("login.need2faCta", "Set up 2FA")}
                </Link>
              </div>
            </>
          )
        ) : me ? (
          // Signed in, not staff. Do not confirm that an admin area exists.
          <div className="adm-gate__block">
            <b>{t("login.nothingHere", "Nothing to see here")}</b>
            <p>{t("login.nothingHereBody", "This page is not available for your account.")}</p>
            <Link className="adm-gate__btn adm-gate__btn--link" to="/dashboard">
              {t("login.backToApp", "Back to the app")}
            </Link>
          </div>
        ) : (
          <div className="adm-gate__block">
            <b>{t("login.signInFirst", "Sign in to your account first")}</b>
            <p>{t("login.signInFirstBody", "Admins use their normal QualiPulse account plus an authenticator code.")}</p>
            <Link className="adm-gate__btn adm-gate__btn--link" to="/login?next=/admin">
              {t("login.goToLogin", "Go to sign in")}
            </Link>
          </div>
        )}

        {config?.shared_key_login && !isAdmin && (
          <div className="adm-gate__legacy">
            {!legacyOpen ? (
              <button type="button" className="adm-gate__legacy-toggle" onClick={() => setLegacyOpen(true)}>
                {t("login.legacyToggle", "Use the shared admin key instead (being retired)")}
              </button>
            ) : (
              <>
                <label className="adm-gate__label">{t("login.yourName")}</label>
                <input
                  className="adm-gate__input"
                  value={legacyName}
                  onChange={(e) => setLegacyName(e.target.value)}
                  placeholder={t("login.namePlaceholder")}
                />
                <label className="adm-gate__label">{t("login.adminKey")}</label>
                <input
                  className={`adm-gate__input${error ? " is-error" : ""}`}
                  type="password"
                  value={legacyKey}
                  onChange={(e) => setLegacyKey(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submitLegacy()}
                  placeholder={t("login.adminKeyPlaceholder")}
                />
                {error && <p className="adm-gate__error">{error}</p>}
                <button className="adm-gate__btn adm-gate__btn--ghost" onClick={submitLegacy} disabled={busy}>
                  {t("login.signIn")}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Modal asking for a fresh authenticator code before a destructive action. */
export function StepUpDialog({
  action,
  onSubmit,
  onCancel,
  error,
  busy,
}: {
  action: string;
  onSubmit: (code: string) => void;
  onCancel: () => void;
  error?: string | null;
  busy?: boolean;
}) {
  const { t } = useTranslation("admin");
  const [code, setCode] = useState("");
  // A rejected code should not linger in the field for the retry.
  useEffect(() => {
    if (error) setCode("");
  }, [error]);
  return (
    <div className="adm-modal__backdrop" role="dialog" aria-modal="true" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="adm-modal adm-modal--narrow">
        <h3>{t("stepUp.title", "Confirm with your authenticator")}</h3>
        <p className="adm-modal__sub">{t("stepUp.body", "{{action}} needs a fresh code, even inside an open admin session.", { action })}</p>
        <input
          className={`adm-gate__input adm-gate__input--code${error ? " is-error" : ""}`}
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          placeholder="123 456"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && code.trim() && onSubmit(code.trim())}
        />
        {error && <p className="adm-gate__error">{error}</p>}
        <div className="adm-modal__actions">
          <button className="adm-btn" onClick={onCancel} disabled={busy}>
            {t("stepUp.cancel", "Cancel")}
          </button>
          <button className="adm-btn adm-btn--danger" onClick={() => onSubmit(code.trim())} disabled={busy || !code.trim()}>
            {busy ? t("stepUp.working", "Working…") : t("stepUp.confirm", "Confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
