import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "./Marketing.css";
import LanguageSwitcher from "../components/LanguageSwitcher";

// Credits-based plan catalogue (PR 3). Prices match the plans seeded in the
// backend ``billing_plans.py`` — keep in sync if either side changes.
// Trial isn't shown on the public pricing page (it's automatic on signup).
const MARKETING_PLANS = [
  {
    id: "exploration",
    monthlyEur: 89,
    annualEur: 890,  // 12-month savings handled in copy
    credits: 25,
    // Sprint 12: survey response cap per period. Surveys are quota-based,
    // not credit-priced (roadmap section 1.6).
    surveyResponses: 500,
    highlight: false,
  },
  {
    id: "team",
    monthlyEur: 299,
    annualEur: 2990,
    credits: 100,
    surveyResponses: 2500,
    highlight: true,
  },
  {
    id: "agency",
    monthlyEur: 799,
    annualEur: 7990,
    credits: 300,
    surveyResponses: 10000,
    highlight: false,
  },
] as const;

export default function Marketing() {
  const { t } = useTranslation("marketing");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  // Pricing toggle (PR 3) — defaults to annual since the savings are noticeable.
  const [billingInterval, setBillingInterval] = useState<"monthly" | "annual">("annual");
  const menuRef = useRef<HTMLDivElement>(null);
  const hamburgerRef = useRef<HTMLButtonElement>(null);

  // Close menu on outside click
  useEffect(() => {
    if (!mobileMenuOpen) return;
    function handleClick(e: MouseEvent) {
      if (
        menuRef.current && !menuRef.current.contains(e.target as Node) &&
        hamburgerRef.current && !hamburgerRef.current.contains(e.target as Node)
      ) {
        setMobileMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [mobileMenuOpen]);

  const closeMobileMenu = () => setMobileMenuOpen(false);

  return (
    <div className="mkt">
      {/* Nav */}
      <nav className="mkt-nav">
        <span className="mkt-logo">QualiPulse</span>
        <div className="mkt-nav-links">
          <a href="#how">{t("nav.howItWorks")}</a>
          <a href="#who">{t("nav.whoItsFor")}</a>
          <a href="#pricing">{t("nav.pricing")}</a>
          <LanguageSwitcher style={{ marginRight: 4 }} />
          <Link to="/login" className="mkt-nav-login">{t("nav.login")}</Link>
          <Link to="/signup" className="btn btn-primary mkt-nav-cta">{t("nav.startTrial")}</Link>
        </div>
        <button
          ref={hamburgerRef}
          className={`mkt-hamburger${mobileMenuOpen ? " open" : ""}`}
          onClick={() => setMobileMenuOpen((v) => !v)}
          aria-label="Toggle menu"
          aria-expanded={mobileMenuOpen}
        >
          <span className="mkt-hamburger-line" />
          <span className="mkt-hamburger-line" />
          <span className="mkt-hamburger-line" />
        </button>
        {mobileMenuOpen && (
          <div className="mkt-mobile-menu" ref={menuRef}>
            <a href="#how" onClick={closeMobileMenu}>{t("nav.howItWorks")}</a>
            <a href="#who" onClick={closeMobileMenu}>{t("nav.whoItsFor")}</a>
            <a href="#pricing" onClick={closeMobileMenu}>{t("nav.pricing")}</a>
            <LanguageSwitcher style={{ marginRight: 4 }} />
            <Link to="/login" onClick={closeMobileMenu}>{t("nav.login")}</Link>
            <Link to="/signup" className="btn btn-primary mkt-mobile-cta" onClick={closeMobileMenu}>{t("nav.startTrial")}</Link>
          </div>
        )}
      </nav>

      {/* Hero */}
      <section className="mkt-hero">
        <div className="mkt-hero-inner">
          <div className="mkt-badge">{t("hero.badge")}</div>
          <h1 className="mkt-h1">
            {t("hero.title").split("\n").map((line, i) => (
              <span key={i}>{line}{i === 0 && <br />}</span>
            ))}
          </h1>
          <p className="mkt-sub">{t("hero.subtitle")}</p>
          <div className="mkt-hero-ctas">
            <Link to="/signup" className="btn btn-primary mkt-btn-lg">{t("hero.cta")}</Link>
          </div>
          <p className="mkt-hero-note">{t("hero.note")}</p>
        </div>

        {/* Fake UI preview */}
        <div className="mkt-hero-preview">
          <div className="mkt-preview-card">
            <div className="mkt-preview-header">
              <span className="mkt-preview-dot red" />
              <span className="mkt-preview-dot yellow" />
              <span className="mkt-preview-dot green" />
              <span className="mkt-preview-title">{t("preview.interviewInProgress")}</span>
            </div>
            <div className="mkt-preview-body">
              <div className="mkt-preview-question">
                "{t("hero.interviewQuestion")}"
              </div>
              <div className="mkt-preview-wave">
                {Array.from({ length: 20 }).map((_, i) => (
                  <span key={i} className="mkt-wave-bar" style={{ animationDelay: `${i * 0.07}s` }} />
                ))}
              </div>
              <div className="mkt-preview-status">{t("preview.recording")} · 0:42</div>
            </div>
          </div>
          <div className="mkt-preview-stat mkt-stat-themes">
            <span className="mkt-stat-label">{t("preview.emergingThemes")}</span>
            {(t("hero.themeTags", { returnObjects: true }) as string[]).map((tag) => (
              <span key={tag} className="mkt-stat-tag">{tag}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Pain points */}
      <section className="mkt-pain">
        <div className="mkt-pain-inner">
          <h2 className="mkt-section-title">{t("painPoints.title")}</h2>
          <p className="mkt-section-sub">{t("painPoints.subtitle")}</p>
          <div className="mkt-pain-grid">
            {(t("painPoints.items", { returnObjects: true }) as Array<{ title: string; desc: string }>).map((p) => (
              <div key={p.title} className="mkt-pain-card">
                <h3>{p.title}</h3>
                <p>{p.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="mkt-section" id="how">
        <h2 className="mkt-section-title">{t("howItWorks.title")}</h2>
        <p className="mkt-section-sub">{t("howItWorks.subtitle")}</p>
        <div className="mkt-steps">
          {(t("howItWorks.steps", { returnObjects: true }) as Array<{ title: string; desc: string }>).map((s, i) => (
            <div key={i} className="mkt-step">
              <div className="mkt-step-num">0{i + 1}</div>
              <h3 className="mkt-step-title">{s.title}</h3>
              <p className="mkt-step-desc">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Output preview */}
      <section className="mkt-output">
        <div className="mkt-output-inner">
          <h2 className="mkt-section-title">{t("output.title")}</h2>
          <p className="mkt-section-sub">{t("output.subtitle")}</p>
          <div className="mkt-output-card">
            <div className="mkt-output-header">
              <span className="mkt-output-project">{t("output.projectName")}</span>
              <span className="mkt-output-meta">{t("output.meta")}</span>
            </div>
            <div className="mkt-output-summary">
              <h4>{t("output.summaryTitle")}</h4>
              <p>{t("output.summaryText")}</p>
            </div>
            <div className="mkt-output-themes">
              <h4>{t("output.keyThemesTitle")}</h4>
              <div className="mkt-output-theme">
                <div className="mkt-output-theme-header">
                  <span className="mkt-output-theme-title">{t("output.theme1Title")}</span>
                  <span className="mkt-output-theme-count">{t("output.theme1Count")}</span>
                </div>
                <blockquote>{t("output.theme1Quote")}</blockquote>
                <span className="mkt-output-theme-attr">{t("output.theme1Attr")}</span>
              </div>
              <div className="mkt-output-theme">
                <div className="mkt-output-theme-header">
                  <span className="mkt-output-theme-title">{t("output.theme2Title")}</span>
                  <span className="mkt-output-theme-count">{t("output.theme2Count")}</span>
                </div>
                <blockquote>{t("output.theme2Quote")}</blockquote>
                <span className="mkt-output-theme-attr">{t("output.theme2Attr")}</span>
              </div>
            </div>
            <div className="mkt-output-recs">
              <h4>{t("output.recsTitle")}</h4>
              <ul>
                <li>{t("output.rec1")}</li>
                <li>{t("output.rec2")}</li>
                <li>{t("output.rec3")}</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Who it's for */}
      <section className="mkt-section" id="who">
        <h2 className="mkt-section-title">{t("whoItsFor.title")}</h2>
        <p className="mkt-section-sub">{t("whoItsFor.subtitle")}</p>
        <div className="mkt-use-cases">
          {(t("whoItsFor.items", { returnObjects: true }) as Array<{ title: string; desc: string; examples: string }>).map((uc) => (
            <div key={uc.title} className="mkt-use-case">
              <h3 className="mkt-use-case-title">{uc.title}</h3>
              <p className="mkt-use-case-desc">{uc.desc}</p>
              <span className="mkt-use-case-examples">{uc.examples}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Differentiator */}
      <section className="mkt-diff">
        <div className="mkt-diff-inner">
          <h2 className="mkt-section-title">{t("differentiator.title")}</h2>
          <p className="mkt-section-sub">{t("differentiator.subtitle")}</p>
          <div className="mkt-diff-list">
            {(t("differentiator.items", { returnObjects: true }) as Array<{ vs: string; point: string }>).map((c) => (
              <div key={c.vs} className="mkt-diff-row">
                <span className="mkt-diff-vs">vs. {c.vs}</span>
                <p className="mkt-diff-point">{c.point}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust */}
      <section className="mkt-trust">
        <div className="mkt-trust-inner">
          <h3>{t("trust.quote")}</h3>
          <div className="mkt-trust-meta">
            <span className="mkt-trust-name">{t("trust.name")}</span>
            <span className="mkt-trust-role">{t("trust.role")}</span>
          </div>
          <div className="mkt-trust-badges">
            {(t("trust.badges", { returnObjects: true }) as string[]).map((badge) => (
              <span key={badge}>{badge}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing — credits-based plans (PR 3 rebuild) */}
      <section className="mkt-section" id="pricing">
        <h2 className="mkt-section-title">{t("pricing.title")}</h2>
        <p className="mkt-section-sub">{t("pricing.subtitle")}</p>

        {/* Monthly / annual toggle. Uses the existing .mkt-billing-toggle
            shape (pill group with .active state) — see Marketing.css. */}
        <div className="mkt-billing-toggle" role="tablist" aria-label={t("pricing.billingToggleLabel", { defaultValue: "Billing interval" })}>
          <button
            role="tab"
            aria-selected={billingInterval === "monthly"}
            className={billingInterval === "monthly" ? "active" : ""}
            onClick={() => setBillingInterval("monthly")}
          >
            {t("pricing.billingMonthly", { defaultValue: "Monthly" })}
          </button>
          <button
            role="tab"
            aria-selected={billingInterval === "annual"}
            className={billingInterval === "annual" ? "active" : ""}
            onClick={() => setBillingInterval("annual")}
          >
            {t("pricing.billingAnnual", { defaultValue: "Annual" })}{" "}
            <span className="mkt-billing-toggle-save">
              {t("pricing.billingAnnualSave", { defaultValue: "Save 17%" })}
            </span>
          </button>
        </div>

        <div className="mkt-plans">
          {MARKETING_PLANS.map((p) => {
            const features = t(`pricing.plans.${p.id}.features`, { returnObjects: true }) as string[];
            const monthlyAmount = p.monthlyEur;
            const annualAmount = p.annualEur;
            const isAnnual = billingInterval === "annual";
            const display = isAnnual
              ? Math.round(annualAmount / 12)  // monthly equivalent of annual price
              : monthlyAmount;
            return (
              <div key={p.id} className={`mkt-plan${p.highlight ? " mkt-plan-highlight" : ""}`}>
                {p.highlight && <div className="mkt-plan-badge">{t("pricing.recommended")}</div>}
                <div className="mkt-plan-name">{t(`pricing.plans.${p.id}.name`)}</div>
                <div className="mkt-plan-price">
                  €{display}
                  <span className="mkt-plan-period">{t("pricing.perMonth")}</span>
                </div>
                {isAnnual && (
                  <div className="mkt-plan-billed-as">
                    {t("pricing.billedAnnuallyAs", { amount: annualAmount, defaultValue: "Billed €{{amount}} per year" })}
                  </div>
                )}
                <div className="mkt-plan-credits">
                  <strong>{p.credits}</strong> {t("pricing.creditsPerMonth", { defaultValue: "interview credits / month" })}
                </div>
                <div className="mkt-plan-credits" style={{ marginTop: 4, fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                  <strong className="tabular">{p.surveyResponses.toLocaleString()}</strong> {t("pricing.surveyResponsesPerMonth", { defaultValue: "survey responses / month" })}
                </div>
                <div className="mkt-plan-desc">{t(`pricing.plans.${p.id}.desc`)}</div>
                <ul className="mkt-plan-features">
                  {features.map((f, i) => (
                    <li key={i}>
                      <span className="mkt-check">&#10003;</span> {f}
                    </li>
                  ))}
                </ul>
                <Link
                  to={`/signup?plan=${p.id}&interval=${billingInterval}`}
                  className={`btn ${p.highlight ? "btn-primary" : "btn-secondary"} mkt-plan-cta`}
                >
                  {t(`pricing.plans.${p.id}.cta`)}
                </Link>
              </div>
            );
          })}
        </div>
        <p className="mkt-plans-credit-note">
          {t("pricing.creditDefinition", {
            defaultValue: "1 credit = 1 completed participant interview, up to 15 minutes."
          })}
        </p>
        <p className="mkt-plans-enterprise">
          {t("pricing.enterprise")}{" "}
          <a href="mailto:hello@qualipulse.com">{t("pricing.enterpriseCta")}</a>
        </p>
      </section>

      {/* Final CTA */}
      <section className="mkt-final-cta">
        <div className="mkt-final-cta-inner">
          <h2>{t("finalCta.title")}</h2>
          <p>{t("finalCta.subtitle")}</p>
          <Link to="/signup" className="btn btn-primary mkt-btn-lg">{t("finalCta.cta")}</Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="mkt-footer">
        <span className="mkt-logo">QualiPulse</span>
        <div className="mkt-footer-links">
          <Link to="/login">{t("footer.login")}</Link>
          <Link to="/signup">{t("footer.signup")}</Link>
          <Link to="/terms">{t("footer.terms")}</Link>
          <Link to="/privacy">{t("footer.privacy")}</Link>
          <a href="mailto:hello@qualipulse.com">{t("footer.contact")}</a>
        </div>
        {/* The "Got an interview link?" text used to wrap a <Link to="/i/demo">
            that pointed at a non-existent demo token — Googlebot crawled it from
            every public page and Search Console flagged it as 404. Participants
            don't need a link here anyway (they already have their own from the
            invitation email), so we keep the helper copy but drop the broken link. */}
        <span className="mkt-footer-copy">{t("footer.copy")} &middot; {t("footer.interviewLink")}</span>
      </footer>
    </div>
  );
}
