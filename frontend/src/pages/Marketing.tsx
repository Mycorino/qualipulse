import { useState, useEffect, useRef, useCallback, lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import { useHead } from "../hooks/useHead";
import "./Marketing.css";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { track } from "../utils/analytics";
import { USE_CASES, signupPathForTemplate } from "../marketing/useCases";
import { loadDemoReport } from "../marketing/demoReport";
import type { SharedReportData } from "./SharedReport";

// The real shared-report component, loaded only when a visitor opens the
// panel (never during prerender, where the panel is closed).
const SharedReportEmbed = lazy(() =>
  import("./SharedReport").then((m) => ({ default: m.SharedReportEmbed })),
);

// Credits-based plan catalogue (PR 3). Prices match the plans seeded in the
// backend ``billing_plans.py``; keep in sync if either side changes.
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

// Prepaid credit packs, mirrored from ``CREDIT_PACKS`` in billing_plans.py
// (test_credit_packs.py pins these numbers). Priced at the matching plan's
// overage rate so prepaying is never dearer than going over.
const MARKETING_PACKS = [
  { id: "pack_25", credits: 25, eur: 175 },
  { id: "pack_50", credits: 50, eur: 300 },
  { id: "pack_100", credits: 100, eur: 500 },
] as const;

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* ---- Scroll-triggered animation hook ---- */
function useInView(threshold = 0.12, initiallyVisible = false) {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(initiallyVisible);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion()) { setVisible(true); return; }
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, visible };
}

/** Fire one analytics event the first time an element scrolls into view. */
function useTrackInView(
  ref: React.RefObject<HTMLElement | null>,
  event: "pricing_viewed"
) {
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    // Deliberately a separate observer from useInView: that one reports
    // "visible" immediately under prefers-reduced-motion, which would
    // count a section as seen by someone who never scrolled to it.
    const obs = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          track(event, { once: true });
          obs.disconnect();
        }
      },
      { threshold: 0.3 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [ref, event]);
}

/* ---- Live interview simulation (hero) ----
   A looping mock of the product's characteristic moment: an AI voice
   interview with an adaptive follow-up that quotes the participant's own
   words back. Waveform energy tracks who is "speaking". */
const LIVE_LINES = [
  { who: "ai", key: "q1", badge: false },
  { who: "p", key: "a1", badge: false },
  { who: "ai", key: "q2", badge: true },
  { who: "p", key: "a2", badge: false },
] as const;

const WAVE_BARS = 72;

function LiveInterviewCard() {
  const { t } = useTranslation("marketing");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const energyRef = useRef(0.25);
  const [shown, setShown] = useState(0);
  const [secs, setSecs] = useState(462);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    let phase = 0;
    const draw = () => {
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      const bw = w / WAVE_BARS;
      for (let i = 0; i < WAVE_BARS; i++) {
        const p = phase * 0.9 + i * 0.55;
        const amp = (Math.sin(p) * 0.5 + 0.5) * (Math.sin(p * 0.31 + 2) * 0.5 + 0.5);
        const bh = 3 + amp * energyRef.current * (h - 8);
        ctx.fillStyle = i % 9 === 0 ? "#6d8ef8" : "rgba(238,241,247,0.26)";
        ctx.fillRect(i * bw + 1, (h - bh) / 2, bw - 3, bh);
      }
      phase += 0.06;
    };
    if (prefersReducedMotion()) {
      energyRef.current = 0.6;
      draw();
      return;
    }
    let raf = 0;
    const loop = () => { draw(); raf = requestAnimationFrame(loop); };
    loop();
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion()) { setShown(LIVE_LINES.length); return; }
    let timer: ReturnType<typeof setTimeout>;
    let idx = 0;
    const step = () => {
      if (idx >= LIVE_LINES.length) {
        timer = setTimeout(() => {
          setShown(0);
          idx = 0;
          energyRef.current = 0.25;
          timer = setTimeout(step, 700);
        }, 5200);
        return;
      }
      const line = LIVE_LINES[idx];
      idx += 1;
      setShown(idx);
      energyRef.current = line.who === "ai" ? 0.3 : 0.85;
      timer = setTimeout(step, line.who === "ai" ? 2600 : 3400);
    };
    timer = setTimeout(step, 600);
    const clock = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => { clearTimeout(timer); clearInterval(clock); };
  }, []);

  const mm = Math.floor(secs / 60), ss = secs % 60;
  const clockLabel = `${mm < 10 ? "0" : ""}${mm}:${ss < 10 ? "0" : ""}${ss}`;

  return (
    <div className="mkt-live-card" aria-label={t("live.study")}>
      <div className="mkt-live-head">
        <span className="mkt-rec-dot" aria-hidden="true" />
        <span className="mkt-live-study">{t("live.study")}</span>
        <span>{t("live.participantName")}</span>
        <span className="mkt-live-clock">{clockLabel}</span>
      </div>
      <div className="mkt-wave-row">
        <canvas ref={canvasRef} width={600} height={56} aria-hidden="true" />
      </div>
      <div className="mkt-live-transcript">
        {LIVE_LINES.map((line, i) => (
          <div key={line.key} className={`mkt-live-line${line.who === "ai" ? " ai" : ""}${i < shown ? " on" : ""}`}>
            <div className="mkt-live-speaker">
              <span className={line.who === "ai" ? "mkt-live-who-ai" : undefined}>
                {line.who === "ai" ? t("live.aiLabel") : t("live.participantLabel")}
              </span>
              {line.badge && <span className="mkt-followup-badge">{t("live.followUpBadge")}</span>}
            </div>
            <p>{t(`live.${line.key}`)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- Evidence traceability demo ----
   Click a memo finding → the verbatim quote that backs it lights up with
   participant + timestamp. The product's core trust promise, made tactile. */
function EvidenceDemo() {
  const { t } = useTranslation("marketing");
  const [active, setActive] = useState(0);
  const claims = t("evidence.claims", { returnObjects: true }) as Array<{
    title: string; time: string; sub: string; meta: string;
  }>;

  return (
    <div className="mkt-evi-grid">
      <div className="mkt-evi-panel">
        <div className="mkt-evi-panel-head">{t("evidence.memoHead")}</div>
        <div className="mkt-evi-claims" role="tablist" aria-label={t("evidence.memoHead")}>
          {claims.map((c, i) => (
            <button
              key={c.title}
              type="button"
              role="tab"
              aria-selected={active === i}
              className={`mkt-claim${active === i ? " active" : ""}`}
              onClick={() => setActive(i)}
            >
              <span className="mkt-claim-title">
                <span>{c.title}</span>
                <span className="mkt-claim-ref">→ {c.time}</span>
              </span>
              <span className="mkt-claim-sub">{c.sub}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="mkt-evi-panel">
        <div className="mkt-evi-panel-head">{t("evidence.transcriptHead")}</div>
        <div className="mkt-evi-transcript">
          {claims.map((c, i) => (
            <div key={c.title} className={`mkt-t-line${active === i ? " hit" : ""}`}>
              <div className="mkt-t-meta"><span>{c.time}</span><span>{c.meta}</span></div>
              <p>
                <Trans t={t} i18nKey={`evidence.claims.${i}.quote`} components={{ m: <mark /> }} />
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Marketing() {
  const { t, i18n } = useTranslation("marketing");
  const isFr = i18n.language?.startsWith("fr");

  useHead({
    title: t("meta.title"),
    metas: [
      { name: "description", content: t("meta.description") },
      { property: "og:title", content: t("meta.title") },
      { property: "og:description", content: t("meta.description") },
      { property: "og:url", content: "https://app.qualipulse.com/" },
      { property: "og:image", content: "https://app.qualipulse.com/og-image.png" },
      { property: "og:locale", content: isFr ? "fr_FR" : "en_US" },
    ],
    links: [{ rel: "canonical", href: "https://app.qualipulse.com/" }],
    // One @graph so the page ships every entity in a single data block:
    // the product with its real plan prices, the publisher, and the pricing
    // FAQ (eligible for FAQ rich results, content comes from faq.items).
    jsonLd: {
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "SoftwareApplication",
          name: "QualiPulse",
          applicationCategory: "BusinessApplication",
          operatingSystem: "Web",
          description: t("meta.description"),
          url: "https://app.qualipulse.com",
          // Prices come from MARKETING_PLANS (kept in sync with billing_plans.py).
          offers: [
            {
              "@type": "Offer",
              name: t("pricing.trial.name"),
              price: "0",
              priceCurrency: "EUR",
              description: t("pricing.trial.desc"),
            },
            ...MARKETING_PLANS.map((p) => ({
              "@type": "Offer",
              name: t(`pricing.plans.${p.id}.name`),
              price: String(p.monthlyEur),
              priceCurrency: "EUR",
              description: t(`pricing.plans.${p.id}.desc`),
            })),
          ],
        },
        {
          "@type": "Organization",
          name: "QualiPulse",
          url: "https://app.qualipulse.com",
          logo: "https://app.qualipulse.com/apple-touch-icon.png",
          description: t("meta.description"),
        },
        {
          "@type": "FAQPage",
          mainEntity: (
            t("faq.items", { returnObjects: true }) as Array<{ question: string; answer: string }>
          ).map((item) => ({
            "@type": "Question",
            name: item.question,
            acceptedAnswer: { "@type": "Answer", text: item.answer },
          })),
        },
      ],
    },
  });

  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [billingInterval, setBillingInterval] = useState<"monthly" | "annual">("monthly");
  // "Open the real report": the example study's shared report, rendered in
  // place under the screenshot so the visitor never leaves the page (and
  // the signup CTA stays one click away in the panel bar).
  const [reportOpen, setReportOpen] = useState(false);
  const [reportData, setReportData] = useState<SharedReportData | null>(null);
  const reportPanelRef = useRef<HTMLDivElement>(null);
  const openReport = useCallback(() => {
    setReportOpen(true);
    track("cta_signup_click", { location: "report_open" });
    loadDemoReport(i18n.language).then(setReportData).catch(() => setReportOpen(false));
    window.requestAnimationFrame(() => {
      reportPanelRef.current?.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [i18n.language]);
  const closeReport = useCallback(() => {
    setReportOpen(false);
    window.requestAnimationFrame(() => {
      document.getElementById("evidence")?.scrollIntoView({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    });
  }, []);
  const menuRef = useRef<HTMLDivElement>(null);
  const hamburgerRef = useRef<HTMLButtonElement>(null);
  const initialHash = typeof window !== "undefined" ? window.location.hash : "";

  const problemAnim = useInView();
  const howAnim = useInView(0.12, initialHash === "#how");
  const useCasesAnim = useInView(0.12, initialHash === "#use-cases");
  const foundingAnim = useInView();
  const evidenceAnim = useInView(0.12, initialHash === "#evidence");
  const diffAnim = useInView();
  const pricingAnim = useInView(0.12, initialHash === "#pricing");
  const faqAnim = useInView(0.12, initialHash === "#faq");

  // "Did they even reach pricing?" is the first question any homepage
  // conversion number raises, so it gets its own event.
  useTrackInView(pricingAnim.ref, "pricing_viewed");

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

  const heroFacts = t("hero.facts", { returnObjects: true }) as string[];
  const howSteps = t("how.steps", { returnObjects: true }) as Array<{ num: string; title: string; desc: string }>;
  const guideLines = t("how.guideLines", { returnObjects: true }) as string[];
  const foundingItems = t("founding.items", { returnObjects: true }) as Array<{ title: string; desc: string }>;
  const diffItems = (t("diff.items", { returnObjects: true }) as Array<{ title: string; desc: string }>).slice(0, 3);
  const trialFeatures = t("pricing.trial.features", { returnObjects: true }) as string[];
  const faqs = t("faq.items", { returnObjects: true }) as Array<{ question: string; answer: string }>;

  // FR price convention: "89 €" (narrow no-break space); EN: "€89".
  const formatEur = (n: number) => (isFr ? `${n} €` : `€${n}`);

  const miniWaveHeights = [8, 14, 22, 12, 18, 26, 10, 16, 24, 14, 8, 20, 26, 12, 18, 10, 22, 16, 8, 14, 24, 18, 12, 20];

  return (
    <div className="mkt">
      {/* ---- Nav ---- */}
      <nav className="mkt-nav">
        <Link to="/" className="mkt-logo" aria-label="QualiPulse">
          QualiPulse <span className="mkt-logo-dot" aria-hidden="true" />
        </Link>
        <div className="mkt-nav-links">
          <a href="#use-cases">{t("nav.useCases")}</a>
          <a href="#how">{t("nav.howItWorks")}</a>
          <a href="#evidence">{t("nav.evidence")}</a>
          <a href="#pricing">{t("nav.pricing")}</a>
          <a href="#faq">{t("nav.faq")}</a>
          <LanguageSwitcher variant="dark" />
          <Link to="/login" className="mkt-nav-login">{t("nav.login")}</Link>
          <Link to="/signup" className="mkt-btn mkt-btn-primary mkt-nav-cta" onClick={() => track("cta_signup_click", { location: "nav" })}>{t("nav.startTrial")}</Link>
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
            <a href="#use-cases" onClick={closeMobileMenu}>{t("nav.useCases")}</a>
            <a href="#how" onClick={closeMobileMenu}>{t("nav.howItWorks")}</a>
            <a href="#evidence" onClick={closeMobileMenu}>{t("nav.evidence")}</a>
            <a href="#pricing" onClick={closeMobileMenu}>{t("nav.pricing")}</a>
            <a href="#faq" onClick={closeMobileMenu}>{t("nav.faq")}</a>
            <LanguageSwitcher variant="dark" />
            <Link to="/login" onClick={closeMobileMenu}>{t("nav.login")}</Link>
            <Link to="/signup" className="mkt-btn mkt-btn-primary mkt-mobile-cta" onClick={() => { track("cta_signup_click", { location: "nav_mobile" }); closeMobileMenu(); }}>{t("nav.startTrial")}</Link>
          </div>
        )}
      </nav>

      {/* ---- Hero ---- */}
      <header className="mkt-hero">
        <div className="mkt-wrap mkt-hero-grid">
          <div>
            <span className="mkt-eyebrow">{t("hero.eyebrow")}</span>
            <h1 className="mkt-h1">{t("hero.title")}</h1>
            <p className="mkt-hero-sub">
              <Trans t={t} i18nKey="hero.sub" components={{ b: <strong /> }} />
            </p>
            <div className="mkt-hero-ctas">
              <Link to="/signup" className="mkt-btn mkt-btn-primary mkt-btn-lg" onClick={() => track("cta_signup_click", { location: "hero" })}>{t("hero.cta")}</Link>
              <a href="#evidence" className="mkt-btn mkt-btn-ghost">{t("hero.secondaryCta")}</a>
            </div>
            <div className="mkt-hero-facts">
              {heroFacts.map((fact) => (
                <span key={fact}><span className="mkt-fact-tick" aria-hidden="true">●</span>{fact}</span>
              ))}
            </div>
          </div>
          <LiveInterviewCard />
        </div>
      </header>

      {/* ---- Audience strip ---- */}
      <div className="mkt-strip">
        <div className="mkt-wrap mkt-strip-inner">
          <span><Trans t={t} i18nKey="strip.audience" components={{ b: <b /> }} /></span>
          <span>{t("strip.credit")}</span>
          <span><Trans t={t} i18nKey="strip.speed" components={{ b: <b /> }} /></span>
        </div>
      </div>

      {/* ---- Use cases: three problem-led entry points ---- */}
      <section
        className={`mkt-section${useCasesAnim.visible ? " visible" : ""}`}
        id="use-cases"
        ref={useCasesAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("useCases.eyebrow")}</span>
            <h2>{t("useCases.title")}</h2>
            <p>{t("useCases.subtitle")}</p>
          </div>
          <div className="mkt-uc-grid">
            {USE_CASES.map((u) => (
              <article key={u.slug} className="mkt-uc-card">
                <span className="mkt-uc-persona">{t(`useCases.items.${u.key}.persona`)}</span>
                <p className="mkt-uc-trigger">{t(`useCases.items.${u.key}.trigger`)}</p>
                <h3>{t(`useCases.items.${u.key}.title`)}</h3>
                <p>{t(`useCases.items.${u.key}.desc`)}</p>
                <div className="mkt-uc-sample">
                  <small>{t("useCases.sampleLabel")}</small>
                  {t(`useCases.items.${u.key}.sample`)}
                </div>
                <div className="mkt-uc-actions">
                  <Link
                    to={signupPathForTemplate(u.templateId)}
                    className="mkt-btn mkt-btn-primary"
                    onClick={() => track("cta_signup_click", { location: `usecase_${u.slug}` })}
                  >
                    {t(`useCases.items.${u.key}.cta`)}
                  </Link>
                  <Link to={`/use-cases/${u.slug}`} className="mkt-uc-more">
                    {t("useCases.learnMore")} →
                  </Link>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Problem ---- */}
      <section
        className={`mkt-section${problemAnim.visible ? " visible" : ""}`}
        id="problem"
        ref={problemAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap mkt-problem-grid">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("problem.eyebrow")}</span>
            <h2>{t("problem.title")}</h2>
            <p>{t("problem.subtitle")}</p>
          </div>
          <div className="mkt-timeline" aria-hidden="true">
            {(["oldWay", "newWay"] as const).map((way) => {
              const steps = t(`problem.${way}.steps`, { returnObjects: true }) as Array<{ label: string; time: string }>;
              return (
                <div key={way} className={`mkt-timeline-col mkt-timeline-${way}`}>
                  <div className="mkt-timeline-head">
                    <span>{t(`problem.${way}.title`)}</span>
                    <strong>{t(`problem.${way}.total`)}</strong>
                  </div>
                  <ol>
                    {steps.map((step) => (
                      <li key={step.label}>
                        <span>{step.label}</span>
                        <small>{step.time}</small>
                      </li>
                    ))}
                  </ol>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ---- How it works ---- */}
      <section
        className={`mkt-section mkt-section-tight${howAnim.visible ? " visible" : ""}`}
        id="how"
        ref={howAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("how.eyebrow")}</span>
            <h2>{t("how.title")}</h2>
            <p>{t("how.subtitle")}</p>
          </div>
          <div className="mkt-steps">
            <div className="mkt-step">
              <span className="mkt-step-num">{howSteps[0]?.num}</span>
              <h3>{howSteps[0]?.title}</h3>
              <p>{howSteps[0]?.desc}</p>
              <div className="mkt-step-visual" aria-hidden="true">
                <div className="mkt-memo-verdict">{t("how.objectiveLine")}</div>
              </div>
            </div>
            <div className="mkt-step">
              <span className="mkt-step-num">{howSteps[1]?.num}</span>
              <h3>{howSteps[1]?.title}</h3>
              <p>{howSteps[1]?.desc}</p>
              <div className="mkt-step-visual" aria-hidden="true">
                {guideLines.map((line, i) => (
                  <div key={line} className={`mkt-guide-line${i === 2 ? " dim" : ""}`}>
                    <span className="mkt-guide-num">{i < 2 ? `1.${i + 1}` : "2.1"}</span>
                    <span>{line}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="mkt-step">
              <span className="mkt-step-num">{howSteps[2]?.num}</span>
              <h3>{howSteps[2]?.title}</h3>
              <p>{howSteps[2]?.desc}</p>
              <div className="mkt-step-visual" aria-hidden="true">
                <div className="mkt-link-pill">
                  qualipulse.com/i/x7Kd…
                  <span className="mkt-copy-tag">{t("how.copied")}</span>
                </div>
                <div className="mkt-mini-wave">
                  {miniWaveHeights.map((h, i) => (
                    <i key={i} style={{ height: h }} />
                  ))}
                </div>
              </div>
            </div>
            <div className="mkt-step">
              <span className="mkt-step-num">{howSteps[3]?.num}</span>
              <h3>{howSteps[3]?.title}</h3>
              <p>{howSteps[3]?.desc}</p>
              <div className="mkt-step-visual mkt-memo-mini" aria-hidden="true">
                <div className="mkt-memo-verdict">{t("how.memoVerdict")}</div>
                <div className="mkt-memo-row"><span className="mkt-conf">{t("how.confHigh")}</span><span>{t("how.memoRow1")}</span></div>
                <div className="mkt-memo-row"><span className="mkt-conf">{t("how.confMed")}</span><span>{t("how.memoRow2")}</span></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Evidence ---- */}
      <section
        className={`mkt-section mkt-dark${evidenceAnim.visible ? " visible" : ""}`}
        id="evidence"
        ref={evidenceAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("evidence.eyebrow")}</span>
            <h2>{t("evidence.title")}</h2>
            <p>{t("evidence.subtitle")}</p>
          </div>
          <EvidenceDemo />
          <p className="mkt-evi-note">
            <Trans t={t} i18nKey="evidence.note" components={{ b: <strong /> }} />
          </p>
          <figure className="mkt-product">
            <div className="mkt-product-frame">
              <div className="mkt-product-bar" aria-hidden="true"><i /><i /><i /><span>app.qualipulse.com</span></div>
              <img
                src={isFr ? "/marketing/analysis-fr.png" : "/marketing/analysis-en.png"}
                alt={t("product.alt")}
                loading="lazy"
                width={1280}
                height={1000}
              />
            </div>
            <figcaption>
              {t("product.caption")}
              {!reportOpen && (
                <button type="button" className="mkt-btn mkt-btn-outline mkt-product-open" onClick={openReport}>
                  {t("product.openReport")}
                </button>
              )}
            </figcaption>
          </figure>

          {reportOpen && (
            <div className="mkt-report-panel" ref={reportPanelRef}>
              <div className="mkt-report-bar">
                <span className="mkt-report-label">{t("product.panelLabel")}</span>
                <div className="mkt-report-bar-actions">
                  <Link
                    to="/signup"
                    className="mkt-btn mkt-btn-primary"
                    onClick={() => track("cta_signup_click", { location: "report_embed" })}
                  >
                    {t("hero.cta")}
                  </Link>
                  <button type="button" className="mkt-btn mkt-btn-outline" onClick={closeReport}>
                    {t("product.closeReport")}
                  </button>
                </div>
              </div>
              <div className="mkt-report-embed">
                {reportData ? (
                  <Suspense fallback={<div className="mkt-report-loading">{t("product.loading")}</div>}>
                    <SharedReportEmbed data={reportData} />
                  </Suspense>
                ) : (
                  <div className="mkt-report-loading">{t("product.loading")}</div>
                )}
              </div>
              <div className="mkt-report-foot">
                <button type="button" className="mkt-btn mkt-btn-outline" onClick={closeReport}>
                  {t("product.closeReport")}
                </button>
                <Link
                  to="/signup"
                  className="mkt-btn mkt-btn-primary"
                  onClick={() => track("cta_signup_click", { location: "report_embed_foot" })}
                >
                  {t("product.panelCta")}
                </Link>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ---- Differentiators ---- */}
      <section
        className={`mkt-section${diffAnim.visible ? " visible" : ""}`}
        id="different"
        ref={diffAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("diff.eyebrow")}</span>
            <h2>{t("diff.title")}</h2>
          </div>
          <div className="mkt-diff-grid">
            {diffItems.map((item) => (
              <div key={item.title} className="mkt-diff">
                <h3>{item.title}</h3>
                <p>{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Pricing ---- */}
      <section
        className={`mkt-section mkt-section-tight${pricingAnim.visible ? " visible" : ""}`}
        id="pricing"
        ref={pricingAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("pricing.eyebrow")}</span>
            <h2>{t("pricing.title")}</h2>
            <p>{t("pricing.subtitle")}</p>
          </div>

          <div className="mkt-billing-toggle" role="group" aria-label={t("pricing.billingToggleLabel")}>
            <button
              type="button"
              aria-pressed={billingInterval === "monthly"}
              className={billingInterval === "monthly" ? "active" : ""}
              onClick={() => { track("pricing_interval_toggled", { location: "monthly" }); setBillingInterval("monthly"); }}
            >
              {t("pricing.billingMonthly")}
            </button>
            <button
              type="button"
              aria-pressed={billingInterval === "annual"}
              className={billingInterval === "annual" ? "active" : ""}
              onClick={() => { track("pricing_interval_toggled", { location: "annual" }); setBillingInterval("annual"); }}
            >
              {t("pricing.billingAnnual")}{" "}
              <span className="mkt-billing-save">{t("pricing.billingAnnualSave")}</span>
            </button>
          </div>

          <div className="mkt-plans">
            {/* Trial */}
            <div className="mkt-plan">
              <h3>{t("pricing.trial.name")}</h3>
              <p className="mkt-plan-for">{t("pricing.trial.desc")}</p>
              <div className="mkt-plan-price">{formatEur(0)}</div>
              <div className="mkt-plan-credits">{t("pricing.trial.credits")}</div>
              <ul className="mkt-plan-features">
                {trialFeatures.map((f) => <li key={f}>{f}</li>)}
              </ul>
              <Link to="/signup" className="mkt-btn mkt-btn-outline mkt-plan-cta" onClick={() => track("cta_signup_click", { location: "plan_trial" })}>{t("pricing.trial.cta")}</Link>
            </div>
            {/* Paid plans */}
            {MARKETING_PLANS.map((p) => {
              const features = t(`pricing.plans.${p.id}.features`, { returnObjects: true }) as string[];
              const isAnnual = billingInterval === "annual";
              // floor, not round: 7990/12 would round to €666/mo, a number
              // with the wrong connotations on a pricing page
              const display = isAnnual ? Math.floor(p.annualEur / 12) : p.monthlyEur;
              return (
                <div key={p.id} className={`mkt-plan${p.highlight ? " mkt-plan-highlight" : ""}`}>
                  {p.highlight && <span className="mkt-plan-flag">{t("pricing.recommended")}</span>}
                  <h3>{t(`pricing.plans.${p.id}.name`)}</h3>
                  <p className="mkt-plan-for">{t(`pricing.plans.${p.id}.desc`)}</p>
                  <div className="mkt-plan-price">
                    {formatEur(display)}
                    <small>{t("pricing.perMonth")}</small>
                  </div>
                  {isAnnual && (
                    <div className="mkt-plan-billed-as">
                      {t("pricing.billedAnnuallyAs", { amount: p.annualEur })}
                    </div>
                  )}
                  <div className="mkt-plan-credits">
                    <strong>{p.credits}</strong> {t("pricing.creditsPerMonth")}
                    <span className="mkt-plan-survey">
                      <strong>{p.surveyResponses.toLocaleString(i18n.language)}</strong> {t("pricing.surveyResponsesPerMonth")}
                    </span>
                  </div>
                  <ul className="mkt-plan-features">
                    {features.map((f) => <li key={f}>{f}</li>)}
                  </ul>
                  <Link
                    to={`/signup?plan=${p.id}&interval=${billingInterval}`}
                    className={`mkt-btn ${p.highlight ? "mkt-btn-primary" : "mkt-btn-outline"} mkt-plan-cta`}
                    onClick={() => track("cta_signup_click", { location: `plan_${p.id}` })}
                  >
                    {t(`pricing.plans.${p.id}.cta`)}
                  </Link>
                </div>
              );
            })}
          </div>
          <p className="mkt-credit-note">
            {t("pricing.vatNoteLong")}{" "}
            {t("pricing.creditNote", {
              p25: formatEur(MARKETING_PACKS[0].eur),
              p50: formatEur(MARKETING_PACKS[1].eur),
              p100: formatEur(MARKETING_PACKS[2].eur),
            })}{" "}
            {t("pricing.enterprise")}{" "}
            <a href="mailto:hello@qualipulse.com">{t("pricing.enterpriseCta")}</a>
          </p>
        </div>
      </section>

      {/* ---- Founding customers (proof, honestly) ---- */}
      <section
        className={`mkt-section mkt-section-tight${foundingAnim.visible ? " visible" : ""}`}
        id="founding"
        ref={foundingAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap">
          <div className="mkt-founding">
            <div>
              <span className="mkt-eyebrow">{t("founding.eyebrow")}</span>
              <h2>{t("founding.title")}</h2>
              <p className="mkt-founding-intro">{t("founding.subtitle")}</p>
            </div>
            <div>
              <ul className="mkt-founding-list">
                {foundingItems.map((item) => (
                  <li key={item.title}>
                    <strong>{item.title}</strong>
                    <span>{item.desc}</span>
                  </li>
                ))}
              </ul>
              <a
                href={`mailto:hello@qualipulse.com?subject=${encodeURIComponent(t("founding.mailSubject"))}`}
                className="mkt-btn mkt-btn-outline"
                onClick={() => track("cta_signup_click", { location: "founding" })}
              >
                {t("founding.cta")}
              </a>
              <p className="mkt-founding-note">{t("founding.note")}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---- FAQ ---- */}
      <section
        className={`mkt-section mkt-section-tight${faqAnim.visible ? " visible" : ""}`}
        id="faq"
        ref={faqAnim.ref as React.RefObject<HTMLElement>}
      >
        <div className="mkt-wrap">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("faq.eyebrow")}</span>
            <h2>{t("faq.title")}</h2>
          </div>
          <div className="mkt-faq-list">
            {faqs.map((item) => (
              <details key={item.question} className="mkt-faq">
                <summary>{item.question}</summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Final CTA ---- */}
      <section className="mkt-final mkt-dark" id="start">
        <div className="mkt-wrap">
          <span className="mkt-eyebrow">{t("finalCta.eyebrow")}</span>
          <h2>{t("finalCta.title")}</h2>
          <p>{t("finalCta.subtitle")}</p>
          <div className="mkt-hero-ctas mkt-final-ctas">
            <Link to="/signup" className="mkt-btn mkt-btn-primary mkt-btn-lg" onClick={() => track("cta_signup_click", { location: "final" })}>{t("finalCta.cta")}</Link>
            <a href="#evidence" className="mkt-btn mkt-btn-ghost">{t("finalCta.secondaryCta")}</a>
          </div>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="mkt-footer">
        <div className="mkt-wrap">
          <div className="mkt-footer-grid">
            <div className="mkt-footer-col mkt-footer-brand">
              <span className="mkt-logo">QualiPulse <span className="mkt-logo-dot" aria-hidden="true" /></span>
              <p className="mkt-footer-tagline">{t("footer.tagline")}</p>
            </div>
            <div className="mkt-footer-col">
              <h4>{t("footer.productTitle")}</h4>
              <a href="#use-cases">{t("footer.useCases")}</a>
              <a href="#evidence">{t("footer.copilotLink")}</a>
              <a href="#pricing">{t("footer.pricingLink")}</a>
              <Link to="/blog">{t("footer.blog")}</Link>
            </div>
            <div className="mkt-footer-col">
              <h4>{t("footer.companyTitle")}</h4>
              <Link to="/login">{t("footer.login")}</Link>
              <Link to="/signup" onClick={() => track("cta_signup_click", { location: "footer" })}>{t("footer.signup")}</Link>
              <Link to="/participants">{t("footer.becomeParticipant")}</Link>
              <Link to="/affiliate">{t("footer.affiliate")}</Link>
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
        </div>
      </footer>
    </div>
  );
}
