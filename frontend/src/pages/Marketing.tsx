import { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "./Marketing.css";
import LanguageSwitcher from "../components/LanguageSwitcher";

// Credits-based plan catalogue (PR 3). Prices match the plans seeded in the
// backend ``billing_plans.py`` — keep in sync if either side changes.
const MARKETING_PLANS = [
  {
    id: "exploration",
    monthlyEur: 89,
    annualEur: 890,
    credits: 10,
    surveyResponses: 500,
    highlight: false,
  },
  {
    id: "team",
    monthlyEur: 299,
    annualEur: 2990,
    credits: 50,
    surveyResponses: 2500,
    highlight: true,
  },
  {
    id: "agency",
    monthlyEur: 799,
    annualEur: 7990,
    credits: 150,
    surveyResponses: 10000,
    highlight: false,
  },
] as const;

/* ---- Scroll-triggered animation hook ---- */
function useInView(threshold = 0.15, initiallyVisible = false) {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(initiallyVisible);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, visible };
}

export default function Marketing() {
  const { t } = useTranslation("marketing");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [billingInterval, setBillingInterval] = useState<"monthly" | "annual">("annual");
  const [activePersona, setActivePersona] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const hamburgerRef = useRef<HTMLButtonElement>(null);
  const initialHash = typeof window !== "undefined" ? window.location.hash : "";

  // Scroll-triggered sections (hero + trust bar are above the fold, always visible)
  const painAnim = useInView();
  const howAnim = useInView(0.15, initialHash === "#how");
  const copilotAnim = useInView(0.15, initialHash === "#copilot");
  const qualityAnim = useInView();
  const outputAnim = useInView();
  const mixedAnim = useInView();
  const credibilityAnim = useInView();
  const whoAnim = useInView(0.15, initialHash === "#who");
  const compareAnim = useInView();
  const pricingAnim = useInView(0.15, initialHash === "#pricing");

  useEffect(() => {
    if (!initialHash) return;
    const id = initialHash.slice(1);
    window.requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView();
    });
  }, [initialHash]);

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

  const closeMobileMenu = useCallback(() => setMobileMenuOpen(false), []);

  const personas = t("whoItsFor.items", { returnObjects: true }) as Array<{ title: string; desc: string; examples: string }>;
  const comparisonRows = t("comparison.rows", { returnObjects: true }) as Array<{ feature: string; quali: string; other: string }>;
  const comparisonHeaders = t("comparison.headers", { returnObjects: true }) as string[];
  const qualityItems = t("quality.items", { returnObjects: true }) as Array<{ eyebrow: string; title: string; desc: string }>;
  const faqs = t("faq.items", { returnObjects: true }) as Array<{ question: string; answer: string }>;

  return (
    <div className="mkt">
      {/* ---- Nav ---- */}
      <nav className="mkt-nav">
        <span className="mkt-logo">QualiPulse</span>
        <div className="mkt-nav-links">
          <a href="#how">{t("nav.howItWorks")}</a>
          <a href="#copilot">{t("nav.features")}</a>
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
          aria-label={t("nav.toggleMenu")}
          aria-expanded={mobileMenuOpen}
        >
          <span className="mkt-hamburger-line" />
          <span className="mkt-hamburger-line" />
          <span className="mkt-hamburger-line" />
        </button>
        {mobileMenuOpen && (
          <div className="mkt-mobile-menu" ref={menuRef}>
            <a href="#how" onClick={closeMobileMenu}>{t("nav.howItWorks")}</a>
            <a href="#copilot" onClick={closeMobileMenu}>{t("nav.features")}</a>
            <a href="#who" onClick={closeMobileMenu}>{t("nav.whoItsFor")}</a>
            <a href="#pricing" onClick={closeMobileMenu}>{t("nav.pricing")}</a>
            <LanguageSwitcher style={{ marginRight: 4 }} />
            <Link to="/login" onClick={closeMobileMenu}>{t("nav.login")}</Link>
            <Link to="/signup" className="btn btn-primary mkt-mobile-cta" onClick={closeMobileMenu}>{t("nav.startTrial")}</Link>
          </div>
        )}
      </nav>

      {/* ---- Hero ---- */}
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
            <a href="#how" className="mkt-btn-secondary">{t("hero.secondaryCta")} ↓</a>
          </div>
          <p className="mkt-hero-note">{t("hero.note")}</p>
        </div>

        <div className="mkt-hero-preview" aria-label={t("hero.previewLabel")}>
          <div className="mkt-hero-report">
            <div className="mkt-hero-report-header">
              <div>
                <span className="mkt-report-kicker">{t("hero.reportKicker")}</span>
                <strong>{t("output.projectName")}</strong>
              </div>
              <span>{t("hero.reportMeta")}</span>
            </div>
            <div className="mkt-hero-report-summary">
              <span>{t("output.summaryTitle")}</span>
              <p>{t("hero.reportSummary")}</p>
            </div>
            <div className="mkt-hero-report-grid">
              {(t("hero.reportMetrics", { returnObjects: true }) as Array<{ value: string; label: string }>).map((metric) => (
                <div key={metric.label}>
                  <strong>{metric.value}</strong>
                  <span>{metric.label}</span>
                </div>
              ))}
            </div>
            <div className="mkt-hero-report-theme">
              <div>
                <strong>{t("output.theme1Title")}</strong>
                <span>{t("output.theme1Count")}</span>
              </div>
              <blockquote>{t("output.theme1Quote")}</blockquote>
            </div>
            <div className="mkt-hero-report-actions">
              {(t("hero.reportActions", { returnObjects: true }) as string[]).map((action) => (
                <span key={action}>{action}</span>
              ))}
            </div>
          </div>
          <div className="mkt-hero-interview-strip" aria-hidden="true">
            <div>
              <span className="mkt-preview-dot red" />
              <span className="mkt-preview-dot yellow" />
              <span className="mkt-preview-dot green" />
            </div>
            <p>"{t("hero.interviewQuestion")}"</p>
            <div className="mkt-preview-wave">
              {Array.from({ length: 14 }).map((_, i) => (
                <span key={i} className="mkt-wave-bar" style={{ animationDelay: `${i * 0.07}s` }} />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---- Trust Bar ---- */}
      <section className="mkt-trust-bar">
        <div className="mkt-trust-bar-inner">
          {(t("trustBar.stats", { returnObjects: true }) as Array<{ number: string; label: string }>).map((stat, i) => (
            <div key={i} className="mkt-trust-bar-stat">
              <span className="mkt-trust-bar-number">{stat.number}</span>
              <span className="mkt-trust-bar-label">{stat.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Pain points ---- */}
      <section className={`mkt-pain${painAnim.visible ? " visible" : ""}`} ref={painAnim.ref as React.RefObject<HTMLElement>}>
        <div className="mkt-pain-inner">
          <h2 className="mkt-section-title">{t("painPoints.title")}</h2>
          <p className="mkt-section-sub">{t("painPoints.subtitle")}</p>
          <div className="mkt-pain-grid">
            {(t("painPoints.items", { returnObjects: true }) as Array<{ title: string; desc: string }>).map((p, i) => (
              <div key={p.title} className="mkt-pain-card" style={{ animationDelay: `${i * 0.08}s` }}>
                <h3>{p.title}</h3>
                <p>{p.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- How it works ---- */}
      <section className={`mkt-section${howAnim.visible ? " visible" : ""}`} id="how" ref={howAnim.ref as React.RefObject<HTMLElement>}>
        <h2 className="mkt-section-title">{t("howItWorks.title")}</h2>
        <p className="mkt-section-sub">{t("howItWorks.subtitle")}</p>
        <div className="mkt-steps">
          {(t("howItWorks.steps", { returnObjects: true }) as Array<{ title: string; desc: string }>).map((s, i) => (
            <div key={i} className="mkt-step" style={{ animationDelay: `${i * 0.1}s` }}>
              <div className="mkt-step-num">0{i + 1}</div>
              <h3 className="mkt-step-title">{s.title}</h3>
              <p className="mkt-step-desc">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Output preview (the memo — pays off the hero promise) ---- */}
      <section className={`mkt-output${outputAnim.visible ? " visible" : ""}`} ref={outputAnim.ref as React.RefObject<HTMLElement>}>
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

      {/* ---- Mid CTA ---- */}
      <div className="mkt-mid-cta">
        <Link to="/signup" className="btn btn-primary mkt-btn-lg">{t("midCta.text")}</Link>
      </div>

      {/* ---- Quant + qual: mixed methods (the differentiating wedge) ---- */}
      <section className={`mkt-quality${mixedAnim.visible ? " visible" : ""}`} ref={mixedAnim.ref as React.RefObject<HTMLElement>}>
        <div className="mkt-quality-inner">
          <div className="mkt-quality-heading">
            <div className="mkt-badge">{t("mixedMethods.badge")}</div>
            <h2 className="mkt-section-title">{t("mixedMethods.title")}</h2>
            <p className="mkt-section-sub">{t("mixedMethods.subtitle")}</p>
          </div>
          <div className="mkt-quality-grid">
            {(t("mixedMethods.items", { returnObjects: true }) as Array<{ eyebrow: string; title: string; desc: string }>).map((item, i) => (
              <article key={item.title} className="mkt-quality-card" style={{ animationDelay: `${i * 0.08}s` }}>
                <span>{item.eyebrow}</span>
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Research Copilot Showcase ---- */}
      <section className={`mkt-copilot${copilotAnim.visible ? " visible" : ""}`} id="copilot" ref={copilotAnim.ref as React.RefObject<HTMLElement>}>
        <div className="mkt-copilot-inner">
          <div className="mkt-copilot-text">
            <div className="mkt-badge">{t("copilot.badge")}</div>
            <h2 className="mkt-section-title" style={{ textAlign: "left" }}>{t("copilot.title")}</h2>
            <p className="mkt-copilot-subtitle">{t("copilot.subtitle")}</p>
            <ul className="mkt-copilot-features">
              {(t("copilot.features", { returnObjects: true }) as Array<{ icon: string; text: string }>).map((f, i) => (
                <li key={i}>
                  <span className="mkt-copilot-icon">{f.icon}</span>
                  <span>{f.text}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="mkt-copilot-mockup">
            <div className="mkt-preview-card">
              <div className="mkt-preview-header">
                <span className="mkt-preview-dot red" />
                <span className="mkt-preview-dot yellow" />
                <span className="mkt-preview-dot green" />
                <span className="mkt-preview-title">{t("copilot.previewTitle")}</span>
              </div>
              <div className="mkt-copilot-chat">
                <div className="mkt-copilot-bubble mkt-copilot-user">
                  {t("copilot.chatUser")}
                </div>
                <div className="mkt-copilot-bubble mkt-copilot-ai">
                  <p>{t("copilot.chatAi")}</p>
                  <div className="mkt-copilot-proposal">
                    <div className="mkt-copilot-proposal-title">{t("copilot.proposalTitle")}</div>
                    <div className="mkt-copilot-proposal-body">{t("copilot.proposalBody")}</div>
                    <span className="mkt-copilot-accept" aria-hidden="true">
                      {t("copilot.acceptLabel")}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Interview Quality ---- */}
      <section className={`mkt-quality${qualityAnim.visible ? " visible" : ""}`} ref={qualityAnim.ref as React.RefObject<HTMLElement>}>
        <div className="mkt-quality-inner">
          <div className="mkt-quality-heading">
            <div className="mkt-badge">{t("quality.badge")}</div>
            <h2 className="mkt-section-title">{t("quality.title")}</h2>
            <p className="mkt-section-sub">{t("quality.subtitle")}</p>
          </div>
          <div className="mkt-quality-grid">
            {qualityItems.map((item, i) => (
              <article key={item.title} className="mkt-quality-card" style={{ animationDelay: `${i * 0.08}s` }}>
                <span>{item.eyebrow}</span>
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Credibility: try before you trust (honest pre-proof play) ---- */}
      <section className={`mkt-quality${credibilityAnim.visible ? " visible" : ""}`} ref={credibilityAnim.ref as React.RefObject<HTMLElement>}>
        <div className="mkt-quality-inner">
          <div className="mkt-quality-heading">
            <div className="mkt-badge">{t("credibility.badge")}</div>
            <h2 className="mkt-section-title">{t("credibility.title")}</h2>
            <p className="mkt-section-sub">{t("credibility.subtitle")}</p>
          </div>
          <div className="mkt-pain-grid">
            {(t("credibility.items", { returnObjects: true }) as Array<{ title: string; desc: string }>).map((item, i) => (
              <div key={item.title} className="mkt-pain-card" style={{ animationDelay: `${i * 0.08}s` }}>
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Mid CTA ---- */}
      <div className="mkt-mid-cta">
        <Link to="/signup" className="btn btn-primary mkt-btn-lg">{t("midCta.text2")}</Link>
      </div>

      {/* ---- Who it's for — Pill selector ---- */}
      <section className={`mkt-section${whoAnim.visible ? " visible" : ""}`} id="who" ref={whoAnim.ref as React.RefObject<HTMLElement>}>
        <h2 className="mkt-section-title">{t("whoItsFor.title")}</h2>
        <p className="mkt-section-sub">{t("whoItsFor.subtitle")}</p>
        <div className="mkt-persona-pills">
          {personas.map((p, i) => (
            <button
              key={i}
              className={`mkt-persona-pill${activePersona === i ? " active" : ""}`}
              aria-pressed={activePersona === i}
              onClick={() => setActivePersona(i)}
            >
              {p.title}
            </button>
          ))}
        </div>
        <div className="mkt-persona-card" key={activePersona}>
          <h3 className="mkt-use-case-title">{personas[activePersona].title}</h3>
          <p className="mkt-use-case-desc">{personas[activePersona].desc}</p>
          <span className="mkt-use-case-examples">{personas[activePersona].examples}</span>
        </div>
      </section>

      {/* ---- Comparison Table ---- */}
      <section className={`mkt-compare${compareAnim.visible ? " visible" : ""}`} ref={compareAnim.ref as React.RefObject<HTMLElement>}>
        <div className="mkt-compare-inner">
          <h2 className="mkt-section-title">{t("comparison.title")}</h2>
          <p className="mkt-section-sub">{t("comparison.subtitle")}</p>
          <div className="mkt-compare-table">
            <div className="mkt-compare-row mkt-compare-head">
              {comparisonHeaders.map((h, i) => (
                <div key={i}>{h}</div>
              ))}
            </div>
            {comparisonRows.map((row, i) => (
              <div key={i} className="mkt-compare-row">
                <div className="mkt-compare-feature">{row.feature}</div>
                <div className="mkt-compare-quali">{row.quali}</div>
                <div className="mkt-compare-other">{row.other}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Trust ---- */}
      <section className="mkt-trust">
        <div className="mkt-trust-inner">
          <div className="mkt-badge">{t("trust.eyebrow")}</div>
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

      {/* ---- Pricing ---- */}
      <section className={`mkt-section${pricingAnim.visible ? " visible" : ""}`} id="pricing" ref={pricingAnim.ref as React.RefObject<HTMLElement>}>
        <h2 className="mkt-section-title">{t("pricing.title")}</h2>
        <p className="mkt-section-sub">{t("pricing.subtitle")}</p>

        <div className="mkt-billing-toggle" role="group" aria-label={t("pricing.billingToggleLabel", { defaultValue: "Billing interval" })}>
          <button
            type="button"
            aria-pressed={billingInterval === "monthly"}
            className={billingInterval === "monthly" ? "active" : ""}
            onClick={() => setBillingInterval("monthly")}
          >
            {t("pricing.billingMonthly", { defaultValue: "Monthly" })}
          </button>
          <button
            type="button"
            aria-pressed={billingInterval === "annual"}
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
            const isAnnual = billingInterval === "annual";
            const display = isAnnual ? Math.round(p.annualEur / 12) : p.monthlyEur;
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
                    {t("pricing.billedAnnuallyAs", { amount: p.annualEur, defaultValue: "Billed €{{amount}} per year" })}
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
          {t("pricing.creditDefinition", { defaultValue: "1 credit = 1 completed participant interview, up to 15 minutes." })}
        </p>
        <p className="mkt-plans-enterprise">
          {t("pricing.enterprise")}{" "}
          <a href="mailto:hello@qualipulse.com">{t("pricing.enterpriseCta")}</a>
        </p>
        <div className="mkt-faq">
          <h3>{t("faq.title")}</h3>
          <div className="mkt-faq-grid">
            {faqs.map((item) => (
              <details key={item.question} className="mkt-faq-item">
                <summary>{item.question}</summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Final CTA ---- */}
      <section className="mkt-final-cta">
        <div className="mkt-final-cta-inner">
          <h2>{t("finalCta.title")}</h2>
          <p>{t("finalCta.subtitle")}</p>
          <Link to="/signup" className="btn mkt-btn-lg mkt-btn-inverted">{t("finalCta.cta")}</Link>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="mkt-footer">
        <div className="mkt-footer-grid">
          <div className="mkt-footer-col mkt-footer-brand">
            <span className="mkt-logo">QualiPulse</span>
            <p className="mkt-footer-tagline">{t("footer.tagline")}</p>
          </div>
          <div className="mkt-footer-col">
            <h4>{t("footer.productTitle")}</h4>
            <a href="#copilot">{t("footer.features")}</a>
            <a href="#copilot">{t("footer.copilotLink")}</a>
            <a href="#pricing">{t("footer.pricingLink")}</a>
            <Link to="/blog">{t("footer.blog")}</Link>
          </div>
          <div className="mkt-footer-col">
            <h4>{t("footer.companyTitle")}</h4>
            <Link to="/login">{t("footer.login")}</Link>
            <Link to="/signup">{t("footer.signup")}</Link>
            <a href="mailto:hello@qualipulse.com">{t("footer.contact")}</a>
          </div>
          <div className="mkt-footer-col">
            <h4>{t("footer.legalTitle")}</h4>
            <Link to="/terms">{t("footer.terms")}</Link>
            <Link to="/privacy">{t("footer.privacy")}</Link>
            <Link to="/dpa">{t("footer.dpa")}</Link>
            <Link to="/subprocessors">{t("footer.subprocessors")}</Link>
            <Link to="/participant-notice">{t("footer.participantNotice")}</Link>
            <Link to="/ai-use-policy">{t("footer.aiUsePolicy")}</Link>
            <Link to="/retention-policy">{t("footer.retentionPolicy")}</Link>
          </div>
        </div>
        <div className="mkt-footer-bottom">
          <span>{t("footer.copy")}</span>
          <span>{t("footer.interviewLink")}</span>
        </div>
      </footer>
    </div>
  );
}
