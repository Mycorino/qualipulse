import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import "./Marketing.css";
import LanguageSwitcher from "../components/LanguageSwitcher";

const PLANS = [
  {
    id: "starter",
    name: "Starter",
    price: "€49",
    period: "/mo",
    desc: "For individual researchers starting out",
    features: [
      "1 project",
      "10 participants per project",
      "AI interview guide builder",
      "AI themes & quotes analysis",
      "2 interview links per project",
    ],
    cta: "Start 14-day free trial",
    highlight: false,
  },
  {
    id: "team",
    name: "Team",
    price: "€99",
    period: "/mo",
    desc: "For in-house research teams running regular studies",
    features: [
      "5 projects",
      "50 participants per project",
      "Full AI synthesis memo",
      "Demographic segments & heatmaps",
      "CSV export",
      "3 team members",
    ],
    cta: "Start 14-day free trial",
    highlight: true,
  },
  {
    id: "lab",
    name: "Lab",
    price: "€199",
    period: "/mo",
    desc: "For research programs and agencies",
    features: [
      "Unlimited projects",
      "500 participants per project",
      "Everything in Team",
      "Custom branding on interviews",
      "10 team members",
      "Priority support",
    ],
    cta: "Start 14-day free trial",
    highlight: false,
  },
];

export default function Marketing() {
  const { t } = useTranslation("marketing");

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
              <span className="mkt-preview-title">Interview in progress</span>
            </div>
            <div className="mkt-preview-body">
              <div className="mkt-preview-question">
                "Can you walk me through the last time you had to onboard a new tool at work?"
              </div>
              <div className="mkt-preview-wave">
                {Array.from({ length: 20 }).map((_, i) => (
                  <span key={i} className="mkt-wave-bar" style={{ animationDelay: `${i * 0.07}s` }} />
                ))}
              </div>
              <div className="mkt-preview-status">Recording · 0:42</div>
            </div>
          </div>
          <div className="mkt-preview-stat mkt-stat-themes">
            <span className="mkt-stat-label">Emerging themes</span>
            <span className="mkt-stat-tag">Onboarding friction</span>
            <span className="mkt-stat-tag">Trust building</span>
            <span className="mkt-stat-tag">Time to value</span>
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
          <h2 className="mkt-section-title">From 12 interviews to this — automatically</h2>
          <p className="mkt-section-sub">This is what your AI-generated research memo looks like. Themes, quotes, tensions, and recommendations — ready to share.</p>
          <div className="mkt-output-card">
            <div className="mkt-output-header">
              <span className="mkt-output-project">SaaS Onboarding Experience Study</span>
              <span className="mkt-output-meta">12 participants · Generated in 45 seconds</span>
            </div>
            <div className="mkt-output-summary">
              <h4>Summary</h4>
              <p>Participants consistently reported that initial setup complexity is the primary barrier to adoption. Most valued a guided onboarding experience but found current implementations overly generic. Three key themes emerged around time-to-value expectations, the role of social proof in building confidence, and frustrations with feature discovery.</p>
            </div>
            <div className="mkt-output-themes">
              <h4>Key Themes</h4>
              <div className="mkt-output-theme">
                <div className="mkt-output-theme-header">
                  <span className="mkt-output-theme-title">Time-to-value anxiety</span>
                  <span className="mkt-output-theme-count">Mentioned by 9 of 12 participants</span>
                </div>
                <blockquote>"I need to see value in the first 10 minutes or I'm gone. I don't have time to watch tutorials."</blockquote>
                <span className="mkt-output-theme-attr">— Product Manager, Series A startup</span>
              </div>
              <div className="mkt-output-theme">
                <div className="mkt-output-theme-header">
                  <span className="mkt-output-theme-title">Feature discovery friction</span>
                  <span className="mkt-output-theme-count">Mentioned by 7 of 12 participants</span>
                </div>
                <blockquote>"I only found out about the export feature after three months. I'd been doing it manually."</blockquote>
                <span className="mkt-output-theme-attr">— UX Designer, Fintech</span>
              </div>
            </div>
            <div className="mkt-output-recs">
              <h4>Recommendations</h4>
              <ul>
                <li>Implement a task-based onboarding flow that delivers value within the first session</li>
                <li>Add contextual feature hints triggered by user behaviour patterns</li>
                <li>Create role-specific setup paths (researcher vs. PM vs. designer)</li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Who it's for */}
      <section className="mkt-section" id="who">
        <h2 className="mkt-section-title">Built for people who need insights, not busywork</h2>
        <p className="mkt-section-sub">Whether you run research full-time or fit it in between product decisions.</p>
        <div className="mkt-use-cases">
          {[
            { title: "UX Researchers", desc: "Run more studies in less time. Offload the logistics, keep the analytical rigor. AI handles moderation and initial synthesis — you steer the interpretation.", examples: "Discovery research, evaluative studies, continuous research programs" },
            { title: "Product Managers", desc: "Get user insights without waiting for the research team's backlog. Set up a study in minutes, send the link to beta users, get a synthesis you can act on.", examples: "Feature validation, churn investigation, onboarding feedback" },
            { title: "Consultants & Agencies", desc: "Run qualitative research for clients at scale. Custom branding, shareable reports, multiple projects running in parallel.", examples: "Client research engagements, market research, stakeholder interviews" },
          ].map((uc) => (
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
          <h2 className="mkt-section-title">You might be wondering...</h2>
          <p className="mkt-section-sub">How does QualiPulse compare to tools you may already know?</p>
          <div className="mkt-diff-list">
            {[
              { vs: "UserTesting / dscout", point: "Those platforms help you recruit and run moderated sessions. QualiPulse replaces the moderator with AI, runs interviews asynchronously, and synthesises the results. No scheduling, no session fees." },
              { vs: "Dovetail / EnjoyHQ", point: "Those are analysis-and-repository tools for research you've already done. QualiPulse handles the full workflow: guide creation, interview collection, and synthesis in one place." },
              { vs: "Google Forms / Typeform", point: "Surveys give you structured data. QualiPulse gives you qualitative depth — follow-up questions, probing, voice responses — without the overhead of live interviews." },
            ].map((c) => (
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
          <h3>"We built QualiPulse because we were tired of spending 80% of our research time on logistics and 20% on thinking. We wanted to flip that ratio."</h3>
          <div className="mkt-trust-meta">
            <span className="mkt-trust-name">Corino Fontana</span>
            <span className="mkt-trust-role">Founder, QualiPulse</span>
          </div>
          <div className="mkt-trust-badges">
            <span>GDPR compliant</span>
            <span>Data encrypted at rest</span>
            <span>EU-hosted infrastructure</span>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="mkt-section" id="pricing">
        <h2 className="mkt-section-title">{t("pricing.title")}</h2>
        <p className="mkt-section-sub">{t("pricing.subtitle")}</p>
        <div className="mkt-plans">
          {PLANS.map((p) => (
            <div key={p.id} className={`mkt-plan${p.highlight ? " mkt-plan-highlight" : ""}`}>
              {p.highlight && <div className="mkt-plan-badge">{t("pricing.recommended")}</div>}
              <div className="mkt-plan-name">{p.name}</div>
              <div className="mkt-plan-price">
                {p.price}<span className="mkt-plan-period">{p.period}</span>
              </div>
              <div className="mkt-plan-desc">{p.desc}</div>
              <ul className="mkt-plan-features">
                {p.features.map((f) => (
                  <li key={f}>
                    <span className="mkt-check">&#10003;</span> {f}
                  </li>
                ))}
              </ul>
              <Link
                to={`/signup?plan=${p.id}`}
                className={`btn ${p.highlight ? "btn-primary" : "btn-secondary"} mkt-plan-cta`}
              >
                {p.cta}
              </Link>
            </div>
          ))}
        </div>
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
        <span className="mkt-footer-copy">{t("footer.copy")} &middot; <Link to="/interview/demo" style={{color: "inherit"}}>{t("footer.interviewLink")}</Link></span>
      </footer>
    </div>
  );
}
