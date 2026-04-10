import { useState, FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { signup } from "../api/auth";
import { useAuth } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";
import { useToast } from "../components/Toast";
import LanguageSwitcher from "../components/LanguageSwitcher";

function getPasswordStrength(pw: string, t: (key: string) => string): { label: string; color: string; width: string } {
  if (pw.length === 0) return { label: "", color: "", width: "0%" };
  if (pw.length < 8) return { label: t("signup.passwordStrength.tooShort"), color: "var(--danger)", width: "25%" };
  const hasUpper = /[A-Z]/.test(pw);
  const hasLower = /[a-z]/.test(pw);
  const hasNum = /[0-9]/.test(pw);
  const hasSpecial = /[^A-Za-z0-9]/.test(pw);
  const score = [hasUpper, hasLower, hasNum, hasSpecial].filter(Boolean).length;
  if (score <= 1) return { label: t("signup.passwordStrength.weak"), color: "var(--danger)", width: "25%" };
  if (score === 2) return { label: t("signup.passwordStrength.fair"), color: "var(--warning)", width: "50%" };
  if (score === 3) return { label: t("signup.passwordStrength.good"), color: "var(--success)", width: "75%" };
  return { label: t("signup.passwordStrength.strong"), color: "var(--success)", width: "100%" };
}

export default function Signup() {
  const { t } = useTranslation("auth");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [showLoginHint, setShowLoginHint] = useState(false);
  const [loading, setLoading] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const { saveToken } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Plan chosen on landing page (?plan=free|starter|team|lab)
  const selectedPlan = searchParams.get("plan") ?? undefined;
  const refCode = searchParams.get("ref") ?? undefined;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedName) {
      setError(t("signup.errors.nameRequired"));
      return;
    }
    if (!trimmedEmail || !/^[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}$/.test(trimmedEmail)) {
      setError(t("signup.errors.emailInvalid"));
      return;
    }
    if (password.length < 8) {
      setError(t("signup.errors.passwordTooShort"));
      return;
    }
    if (!termsAccepted) {
      setError(t("signup.errors.termsRequired"));
      return;
    }

    setLoading(true);
    try {
      const res = await signup(trimmedName, trimmedEmail, password, {
        plan: selectedPlan,
        refCode,
      });
      saveToken(res.access_token, res.refresh_token);
      toast(t("signup.accountCreated"), "success");
      navigate("/welcome");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        setError(t("signup.errors.emailExists"));
        setShowLoginHint(true);
      } else {
        const msg = getErrorMessage(err, t("signup.createAccount"));
        if (msg.toLowerCase().includes("already")) {
          setError(msg);
          setShowLoginHint(true);
        } else {
          setError(msg);
          setShowLoginHint(false);
        }
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
          <LanguageSwitcher />
        </div>
        <div className="auth-logo">QualiPulse</div>
        <h1 className="auth-title">{t("signup.title")}</h1>
        <p className="auth-subtitle">{t("signup.subtitle")}</p>

        {error && (
          <div className="error-banner">
            {error}
            {showLoginHint && (
              <> <Link to="/login" style={{ color: "var(--primary)", fontWeight: 600 }}>{t("signup.signInInstead")}</Link></>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="signup-name">{t("signup.nameLabel")}</label>
          <input
            id="signup-name"
            type="text"
            className="field-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("signup.namePlaceholder")}
            required
            autoFocus
            autoComplete="name"
          />

          <label className="field-label" htmlFor="signup-email">{t("signup.emailLabel")}</label>
          <input
            id="signup-email"
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            required
            autoComplete="email"
          />

          <label className="field-label" htmlFor="signup-password">{t("signup.passwordLabel")}</label>
          <div style={{ position: "relative" }}>
            <input
              id="signup-password"
              type={showPassword ? "text" : "password"}
              className="field-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("signup.passwordPlaceholder")}
              required
              minLength={8}
              autoComplete="new-password"
              style={{ paddingRight: "52px" }}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              style={{
                position: "absolute",
                right: "12px",
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-muted)",
                fontSize: "13px",
                padding: "4px",
              }}
              tabIndex={-1}
            >
              {showPassword ? t("login.hidePassword") : t("login.showPassword")}
            </button>
          </div>
          {password && (() => {
            const strength = getPasswordStrength(password, t);
            return (
              <div style={{ marginTop: "6px" }}>
                <div style={{ height: "3px", background: "var(--border)", borderRadius: "2px", overflow: "hidden" }}>
                  <div style={{ height: "100%", width: strength.width, background: strength.color, borderRadius: "2px", transition: "all 0.2s" }} />
                </div>
                <span style={{ fontSize: "12px", color: strength.color, marginTop: "2px", display: "block" }}>{strength.label}</span>
              </div>
            );
          })()}

          <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginTop: 8, marginBottom: 4 }}>
            <input
              id="signup-terms"
              type="checkbox"
              checked={termsAccepted}
              onChange={(e) => setTermsAccepted(e.target.checked)}
              style={{ marginTop: 3, accentColor: "var(--primary)" }}
            />
            <label htmlFor="signup-terms" style={{ fontSize: "0.813rem", color: "var(--text-secondary)", cursor: "pointer" }}>
              {t("signup.termsCheckboxPrefix")} <Link to="/terms">{t("signup.termsLink")}</Link> {t("signup.termsAnd")} <Link to="/privacy">{t("signup.privacyLink")}</Link>.
            </label>
          </div>

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? t("signup.creatingAccount") : t("signup.createAccount")}
          </button>
        </form>

        <p className="auth-footer">
          {t("signup.alreadyHaveAccount")} <Link to="/login">{t("signup.signIn")}</Link>
        </p>
      </div>
    </div>
  );
}
