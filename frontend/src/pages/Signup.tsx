import { useState, useEffect, FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useHead } from "../hooks/useHead";
import { signup, getGoogleAuthorizeUrl } from "../api/auth";
import { useAuth, setCachedOnboarded } from "../hooks/useAuth";
import { getErrorMessage } from "../utils/errorMessages";
import { checkoutUrlForSelectedPlan } from "../utils/planCheckout";
import { getStoredRefCode } from "../utils/referral";
import { getAttribution } from "../utils/attribution";
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
  const { t, i18n } = useTranslation("auth");
  useHead({ title: t("signup.metaTitle") });
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [showLoginHint, setShowLoginHint] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);

  async function handleGoogleSignIn() {
    setError("");
    setGoogleLoading(true);
    try {
      const url = await getGoogleAuthorizeUrl("/welcome", i18n.language, refCode ?? "", getAttribution() ?? {});
      window.location.href = url;
    } catch (err: unknown) {
      setError(getErrorMessage(err, t("login.googleError")));
      setGoogleLoading(false);
    }
  }
  const { saveToken } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Plan chosen on landing page (?plan=exploration|team|agency, ?interval=monthly|annual)
  const selectedPlan = searchParams.get("plan") ?? undefined;
  const selectedInterval = searchParams.get("interval") ?? undefined;
  // URL param wins; otherwise fall back to the code captured when the visitor
  // first landed on the marketing page (60-day attribution window).
  const refCode = searchParams.get("ref") ?? getStoredRefCode();

  // Stash the pricing-page choice so later checkout surfaces (paywall,
  // billing) can preselect it. localStorage survives the Google OAuth
  // round-trip, which loses query params.
  useEffect(() => {
    if (selectedPlan) localStorage.setItem("qp_selected_plan", selectedPlan);
    if (selectedInterval) localStorage.setItem("qp_selected_interval", selectedInterval);
  }, [selectedPlan, selectedInterval]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    const trimmedFirst = firstName.trim();
    const trimmedLast = lastName.trim();
    const trimmedCompany = companyName.trim();
    const trimmedEmail = email.trim().toLowerCase();

    if (!trimmedFirst) {
      setError(t("signup.errors.firstNameRequired"));
      return;
    }
    if (!trimmedLast) {
      setError(t("signup.errors.lastNameRequired"));
      return;
    }
    if (!trimmedCompany) {
      setError(t("signup.errors.companyNameRequired"));
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
      const uiLang = (i18n.language || "en").toLowerCase().startsWith("fr") ? "fr" : "en";
      const res = await signup(trimmedCompany, trimmedEmail, password, {
        plan: selectedPlan,
        refCode,
        preferredLanguage: uiLang,
        firstName: trimmedFirst,
        lastName: trimmedLast,
        attribution: getAttribution(),
      });
      saveToken(res.access_token, res.refresh_token);
      setCachedOnboarded(false);
      // Paid intent is charged upfront: "Choose Exploration/Team/Agency" on
      // the pricing page routes through Stripe Checkout now, not the trial.
      // Soft-fails to the normal flow (null) when billing isn't configured
      // or the session can't be created; cancelling checkout also lands on
      // /welcome, where onboarding bootstraps the free trial as usual.
      const checkoutUrl = await checkoutUrlForSelectedPlan();
      if (checkoutUrl) {
        window.location.href = checkoutUrl;
        return;
      }
      toast(t("signup.accountCreated"), "success");
      navigate("/welcome", { replace: true });
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        setError(t("signup.errors.emailExists"));
        setShowLoginHint(true);
      } else {
        const msg = getErrorMessage(err, t("signup.errors.generic"));
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
        <Link to="/" className="auth-logo" style={{ textDecoration: "none", color: "inherit" }}>QualiPulse</Link>
        <h1 className="auth-title">{t("signup.title")}</h1>
        <p className="auth-subtitle">{t("signup.subtitle")}</p>
        <p className="auth-offer-note">{t("signup.offerNote")}</p>

        {error && (
          <div className="error-banner">
            {error}
            {showLoginHint && (
              <> <Link to="/login" style={{ color: "var(--primary)", fontWeight: 600 }}>{t("signup.signInInstead")}</Link></>
            )}
          </div>
        )}

        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={googleLoading}
          className="btn btn-secondary btn-block google-btn"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            marginBottom: 12,
          }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.49h4.84a4.14 4.14 0 0 1-1.8 2.71v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A8.99 8.99 0 0 0 9 18z"/>
            <path fill="#FBBC05" d="M3.97 10.71a5.4 5.4 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3.01-2.33z"/>
            <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A8.96 8.96 0 0 0 9 0 8.99 8.99 0 0 0 .96 4.96l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/>
          </svg>
          {googleLoading ? t("login.googleStarting") : t("login.google")}
        </button>

        <div className="auth-divider" style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          margin: "16px 0",
          color: "var(--text-muted)",
          fontSize: "var(--text-xs)",
        }}>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          <span>{t("login.or")}</span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>

        <form onSubmit={handleSubmit}>
          <div className="signup-name-row">
            <div style={{ flex: 1 }}>
              <label className="field-label" htmlFor="signup-first-name">{t("signup.firstNameLabel")}</label>
              <input
                id="signup-first-name"
                type="text"
                className="field-input"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder={t("signup.firstNamePlaceholder")}
                required
                autoFocus
                autoComplete="given-name"
              />
            </div>
            <div style={{ flex: 1 }}>
              <label className="field-label" htmlFor="signup-last-name">{t("signup.lastNameLabel")}</label>
              <input
                id="signup-last-name"
                type="text"
                className="field-input"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder={t("signup.lastNamePlaceholder")}
                required
                autoComplete="family-name"
              />
            </div>
          </div>

          <label className="field-label">{t("onboarding.languageLabel")}</label>
          <div role="group" aria-label={t("onboarding.languageLabel")} style={{ display: "flex", gap: 8, marginBottom: 4 }}>
            {[
              { code: "en", label: "English" },
              { code: "fr", label: "Français" },
            ].map((opt) => {
              const active = (i18n.language || "en").toLowerCase().startsWith(opt.code);
              return (
                <button
                  key={opt.code}
                  type="button"
                  onClick={() => i18n.changeLanguage(opt.code)}
                  aria-pressed={active}
                  className={`onboarding-chip ${active ? "selected" : ""}`}
                  style={{ flex: 1 }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2, marginBottom: 12 }}>
            {t("onboarding.languageHint")}
          </p>

          <label className="field-label" htmlFor="signup-company">{t("signup.companyNameLabel")}</label>
          <input
            id="signup-company"
            type="text"
            className="field-input"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder={t("signup.companyNamePlaceholder")}
            required
            autoComplete="organization"
          />

          <label className="field-label" htmlFor="signup-email">{t("signup.emailLabel")}</label>
          <input
            id="signup-email"
            type="email"
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("signup.emailPlaceholder")}
            required
            autoComplete="email"
            aria-describedby="signup-email-hint"
          />
          <p id="signup-email-hint" style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2, marginBottom: 12 }}>
            {t("signup.emailHint")}
          </p>

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
              className="password-toggle"
              tabIndex={0}
              aria-label={showPassword ? t("login.hidePassword") : t("login.showPassword")}
            >
              {showPassword ? t("login.hidePassword") : t("login.showPassword")}
            </button>
          </div>
          {password && (() => {
            const strength = getPasswordStrength(password, t);
            return (
              <div style={{ marginTop: "6px" }}>
                <div
                  role="progressbar"
                  aria-label={t("signup.passwordLabel")}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={parseInt(strength.width, 10) || 0}
                  style={{ height: "3px", background: "var(--border)", borderRadius: "2px", overflow: "hidden" }}
                >
                  <div style={{ height: "100%", width: strength.width, background: strength.color, borderRadius: "2px", transition: "all 0.2s" }} />
                </div>
                <span aria-live="polite" style={{ fontSize: "12px", color: strength.color, marginTop: "2px", display: "block" }}>{strength.label}</span>
              </div>
            );
          })()}

          <div className="signup-terms-row">
            <input
              id="signup-terms"
              type="checkbox"
              checked={termsAccepted}
              onChange={(e) => setTermsAccepted(e.target.checked)}
              className="signup-terms-checkbox"
            />
            <label htmlFor="signup-terms" className="signup-terms-label">
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
