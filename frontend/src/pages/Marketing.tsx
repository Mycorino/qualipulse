import { useState } from "react";
import { Link } from "react-router-dom";
import "./Marketing.css";
import client from "../api/client";

const HOW_IT_WORKS = [
  {
    step: "01",
    title: "Build your interview guide",
    desc: "Paste your research brief and let AI draft your guide — objectives, screening criteria, and questions tailored to what you need to learn. Edit anything, then you're ready.",
  },
  {
    step: "02",
    title: "Share a link, participants speak",
    desc: "Send one link. Participants complete the voice interview in their own time, on any device. The AI conducts the conversation, asks follow-ups, and keeps things on track.",
  },
  {
    step: "03",
    title: "Get a memo, not a pile of transcripts",
    desc: "Within hours of your first response, you'll have a structured research memo: key themes, supporting quotes, tensions worth investigating, and clear recommendations — formatted to share with stakeholders immediately.",
  },
];

const PLANS = [
  {
    name: "Solo",
    price: "$0",
    period: "",
    desc: "For individual researchers",
    features: [
      "3 projects",
      "25 participants per project",
      "AI interview guide builder",
      "AI themes & quotes analysis",
      "2 interview links per project",
    ],
    cta: "Get started free",
    highlight: false,
  },
  {
    name: "Team",
    price: "$49",
    period: "/mo",
    desc: "For in-house research teams",
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
    name: "Lab",
    price: "$149",
    period: "/mo",
    desc: "For research programs",
    features: [
      "Unlimited projects",
      "500 participants per project",
      "Everything in Team",
      "Custom branding",
      "10 team members",
      "Priority support",
    ],
    cta: "Start 14-day free trial",
    highlight: false,
  },
];

export default function Marketing() {
  const [nlEmail, setNlEmail] = useState("");
  const [nlLoading, setNlLoading] = useState(false);
  const [nlDone, setNlDone] = useState(false);
  const [nlError, setNlError] = useState("");

  async function handleNewsletter(e: React.FormEvent) {
    e.preventDefault();
    if (!nlEmail) return;
    setNlLoading(true);
    setNlError("");
    try {
      await client.post("/auth/newsletter", { email: nlEmail });
      setNlDone(true);
    } catch {
      setNlError("Something went wrong. Please try again.");
    } finally {
      setNlLoading(false);
    }
  }

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
          <div className="mkt-badge">Built for UX researchers</div>
          <h1 className="mkt-h1">
            From screener to synthesis —<br />in hours, not weeks
          </h1>
          <p className="mkt-sub">
            QualiPulse runs your qualitative interviews for you. Build a guide, share
            a link, and participants complete a voice interview in their own time.
            You get back structured transcripts, emergent themes, and a
            stakeholder-ready research memo. Automatically.
          </p>
          <div className="mkt-hero-ctas">
            <Link to="/signup" className="btn btn-primary mkt-btn-lg">Run your first study free</Link>
            <Link to="/login" className="mkt-link-secondary">Already have an account?</Link>
          </div>
          <p className="mkt-hero-note">Free plan available · 14-day trial on paid plans · No credit card required</p>
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
            <span className="mkt-stat-label">interviews synthesised</span>
          </div>
        </div>
      </section>

      {/* Social proof */}
      <section className="mkt-social-proof">
        <div className="mkt-social-inner">
          <div className="mkt-social-stats">
            <div className="mkt-social-stat">
              <span className="mkt-social-num">500+</span>
              <span className="mkt-social-label">Interviews conducted</span>
            </div>
            <div className="mkt-social-stat">
              <span className="mkt-social-num">4.8h</span>
              <span className="mkt-social-label">Avg time saved per study</span>
            </div>
            <div className="mkt-social-stat">
              <span className="mkt-social-num">92%</span>
              <span className="mkt-social-label">Completion rate</span>
            </div>
          </div>
          <div className="mkt-testimonials">
            <div className="mkt-testimonial">
              <p>"We used to spend two weeks scheduling and running interviews. With QualiPulse, we had actionable insights in two days."</p>
              <span className="mkt-testimonial-author">— Product Research Lead, Series B SaaS</span>
            </div>
            <div className="mkt-testimonial">
              <p>"The AI follow-ups catch things I would have missed. It's like having a trained interviewer available 24/7."</p>
              <span className="mkt-testimonial-author">— UX Researcher, Fintech Startup</span>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="mkt-section" id="how">
        <h2 className="mkt-section-title">How it works</h2>
        <p className="mkt-section-sub">Three steps from research question to insight memo.</p>
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
            <p>No account needed. Open the link, speak naturally, and you're done — right in your browser, on any device.</p>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="mkt-section" id="pricing">
        <h2 className="mkt-section-title">Simple pricing</h2>
        <p className="mkt-section-sub">Start free. No credit card. Upgrade when your research program grows.</p>
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
                to={`/signup?plan=${p.name.toLowerCase()}`}
                className={`btn ${p.highlight ? "btn-primary" : "btn-secondary"} mkt-plan-cta`}
              >
                {p.cta}
              </Link>
            </div>
          ))}
        </div>
        <p className="mkt-plans-enterprise">
          Running a large research program?{" "}
          <a href="mailto:hello@qualipulse.com">Talk to us about Enterprise</a>
        </p>
      </section>

      {/* Newsletter */}
      <section className="mkt-newsletter" id="newsletter">
        <div className="mkt-newsletter-inner">
          <h2 className="mkt-newsletter-title">Stay in the loop</h2>
          <p className="mkt-newsletter-desc">
            Get occasional updates on qualitative research best practices, product news, and tips for better insights.
          </p>
          {nlDone ? (
            <div className="mkt-newsletter-success">
              You're subscribed! Check your inbox for a welcome email.
            </div>
          ) : (
            <form className="mkt-newsletter-form" onSubmit={handleNewsletter}>
              <input
                type="email"
                className="mkt-newsletter-input"
                placeholder="you@company.com"
                value={nlEmail}
                onChange={(e) => setNlEmail(e.target.value)}
                required
              />
              <button type="submit" className="btn btn-primary" disabled={nlLoading}>
                {nlLoading ? "..." : "Subscribe"}
              </button>
            </form>
          )}
          {nlError && <p className="mkt-newsletter-error">{nlError}</p>}
          <p className="mkt-newsletter-note">No spam, ever. Unsubscribe anytime.</p>
        </div>
      </section>

      {/* Footer */}
      <footer className="mkt-footer">
        <span className="mkt-logo">QualiPulse</span>
        <div className="mkt-footer-links">
          <Link to="/login">Log in</Link>
          <Link to="/signup">Sign up</Link>
          <Link to="/terms">Terms</Link>
          <Link to="/privacy">Privacy</Link>
          <a href="mailto:hello@qualipulse.com">Contact</a>
        </div>
        <span className="mkt-footer-copy">&copy; 2026 QualiPulse &middot; GDPR-compliant</span>
      </footer>
    </div>
  );
}
