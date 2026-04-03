import { Link } from "react-router-dom";
import "./Marketing.css";

const HOW_IT_WORKS = [
  {
    step: "01",
    title: "Build your interview guide",
    desc: "Define your research objective, add questions, and set screening criteria. Our AI suggests questions based on your brief.",
  },
  {
    step: "02",
    title: "Share a link",
    desc: "Generate a shareable link and send it to participants. They complete the voice interview in their browser — no app needed.",
  },
  {
    step: "03",
    title: "Get AI-powered insights",
    desc: "Transcripts, themes, JTBDs, tensions, and quotes are automatically synthesised into a research memo ready to share.",
  },
];

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "",
    desc: "Try it out",
    features: ["3 projects", "10 interviews/mo", "Basic analysis"],
    cta: "Get started",
    highlight: false,
  },
  {
    name: "Starter",
    price: "$49",
    period: "/mo",
    desc: "For solo researchers",
    features: ["10 projects", "100 interviews/mo", "Full AI analysis", "CSV export"],
    cta: "Start free trial",
    highlight: true,
  },
  {
    name: "Pro",
    price: "$149",
    period: "/mo",
    desc: "For research teams",
    features: ["Unlimited projects", "Unlimited interviews", "Segment heatmaps", "Priority support"],
    cta: "Start free trial",
    highlight: false,
  },
];

export default function Marketing() {
  return (
    <div className="mkt">
      {/* Nav */}
      <nav className="mkt-nav">
        <span className="mkt-logo">QualiPulse</span>
        <div className="mkt-nav-links">
          <a href="#how">How it works</a>
          <a href="#pricing">Pricing</a>
          <Link to="/login" className="mkt-nav-login">Log in</Link>
          <Link to="/signup" className="btn btn-primary mkt-nav-cta">Get started free</Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="mkt-hero">
        <div className="mkt-hero-inner">
          <div className="mkt-badge">AI-powered qualitative research</div>
          <h1 className="mkt-h1">
            Run voice interviews<br />at scale — without the busywork
          </h1>
          <p className="mkt-sub">
            QualiPulse lets you create an AI-driven interview guide, share a link,
            and get back fully analysed transcripts with themes, quotes, and insights.
            No scheduling. No transcription. No manual coding.
          </p>
          <div className="mkt-hero-ctas">
            <Link to="/signup" className="btn btn-primary mkt-btn-lg">Start for free</Link>
            <Link to="/login" className="mkt-link-secondary">Already have an account →</Link>
          </div>
          <p className="mkt-hero-note">14-day trial · No credit card required</p>
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
            <span className="mkt-stat-label">Top themes</span>
            <span className="mkt-stat-tag">Onboarding friction</span>
            <span className="mkt-stat-tag">Trust building</span>
            <span className="mkt-stat-tag">Time to value</span>
          </div>
          <div className="mkt-preview-stat mkt-stat-count">
            <span className="mkt-stat-num">24</span>
            <span className="mkt-stat-label">interviews analysed</span>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="mkt-section" id="how">
        <h2 className="mkt-section-title">How it works</h2>
        <p className="mkt-section-sub">From research question to insight memo in three steps.</p>
        <div className="mkt-steps">
          {HOW_IT_WORKS.map((s) => (
            <div key={s.step} className="mkt-step">
              <div className="mkt-step-num">{s.step}</div>
              <h3 className="mkt-step-title">{s.title}</h3>
              <p className="mkt-step-desc">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* For participants callout */}
      <section className="mkt-participant-banner">
        <div className="mkt-participant-inner">
          <div className="mkt-participant-icon">🎙️</div>
          <div>
            <h3>Got a link to an interview?</h3>
            <p>You don't need an account. Just open the link you received and complete the voice interview right in your browser.</p>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="mkt-section" id="pricing">
        <h2 className="mkt-section-title">Simple pricing</h2>
        <p className="mkt-section-sub">Start free. Upgrade when you need more.</p>
        <div className="mkt-plans">
          {PLANS.map((p) => (
            <div key={p.name} className={`mkt-plan${p.highlight ? " mkt-plan-highlight" : ""}`}>
              {p.highlight && <div className="mkt-plan-badge">Most popular</div>}
              <div className="mkt-plan-name">{p.name}</div>
              <div className="mkt-plan-price">
                {p.price}<span className="mkt-plan-period">{p.period}</span>
              </div>
              <div className="mkt-plan-desc">{p.desc}</div>
              <ul className="mkt-plan-features">
                {p.features.map((f) => (
                  <li key={f}>
                    <span className="mkt-check">✓</span> {f}
                  </li>
                ))}
              </ul>
              <Link
                to="/signup"
                className={`btn ${p.highlight ? "btn-primary" : "btn-secondary"} mkt-plan-cta`}
              >
                {p.cta}
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="mkt-footer">
        <span className="mkt-logo">QualiPulse</span>
        <div className="mkt-footer-links">
          <Link to="/login">Log in</Link>
          <Link to="/signup">Sign up</Link>
        </div>
        <span className="mkt-footer-copy">© 2026 QualiPulse</span>
      </footer>
    </div>
  );
}
