import { Link, useParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { useHead } from "../hooks/useHead";
import "./Marketing.css";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { track } from "../utils/analytics";
import { USE_CASES, findUseCase, signupPathForTemplate } from "../marketing/useCases";
import NotFound from "./NotFound";

const ORIGIN = "https://app.qualipulse.com";

interface DesignRows {
  participants: string;
  duration: string;
  field: string;
  deliverable: string;
}

interface Finding {
  theme: string;
  stat: string;
  quote: string;
}

/**
 * /use-cases/<slug>: one problem-led landing page per marketing entry point
 * (churn, message testing, NPS deep dive). Prerendered at build time, so it
 * is rendered fully visible with no scroll-reveal state and touches no
 * browser APIs during render. `slug` is passed explicitly by the prerender
 * entry, which renders outside <Routes>; the router path supplies it at
 * runtime.
 */
export default function UseCasePage() {
  const params = useParams<{ slug: string }>();
  return <UseCaseStatic slug={params.slug} />;
}

/** Slug-driven variant used by the build-time prerender (no router params). */
export function UseCaseStatic({ slug }: { slug?: string }) {
  const useCase = findUseCase(slug);
  if (!useCase) return <NotFound />;
  return <UseCaseContent slug={useCase.slug} k={useCase.key} templateId={useCase.templateId} />;
}

function UseCaseContent({ slug, k, templateId }: { slug: string; k: string; templateId: string }) {
  const { t, i18n } = useTranslation("marketing");
  const isFr = i18n.language?.startsWith("fr");
  const page = `useCases.pages.${k}`;
  const item = `useCases.items.${k}`;
  const url = `${ORIGIN}/use-cases/${slug}`;

  const when = t(`${page}.when`, { returnObjects: true }) as string[];
  const design = t(`${page}.design`, { returnObjects: true }) as DesignRows;
  const questions = t(`${page}.questions`, { returnObjects: true }) as string[];
  const finding = t(`${page}.output`, { returnObjects: true }) as Finding;
  const whatYouGet = t(`${page}.whatYouGet`, { returnObjects: true }) as string[];
  const facts = t("hero.facts", { returnObjects: true }) as string[];
  const signupPath = signupPathForTemplate(templateId);
  const others = USE_CASES.filter((u) => u.slug !== slug);

  useHead({
    title: t(`${page}.metaTitle`),
    metas: [
      { name: "description", content: t(`${page}.metaDescription`) },
      { property: "og:title", content: t(`${page}.metaTitle`) },
      { property: "og:description", content: t(`${page}.metaDescription`) },
      { property: "og:url", content: url },
      { property: "og:image", content: `${ORIGIN}/og-image.png` },
      { property: "og:locale", content: isFr ? "fr_FR" : "en_US" },
    ],
    links: [{ rel: "canonical", href: url }],
    jsonLd: {
      "@context": "https://schema.org",
      "@graph": [
        {
          "@type": "WebPage",
          name: t(`${page}.metaTitle`),
          description: t(`${page}.metaDescription`),
          url,
          isPartOf: { "@type": "WebSite", name: "QualiPulse", url: ORIGIN },
        },
        {
          "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "QualiPulse", item: `${ORIGIN}/` },
            { "@type": "ListItem", position: 2, name: t(`${item}.title`), item: url },
          ],
        },
      ],
    },
  });

  const trackStart = (location: string) => () =>
    track("cta_signup_click", { location: `usecase_page_${slug}_${location}` });

  return (
    <div className="mkt mkt-uc">
      <nav className="mkt-nav mkt-nav--simple">
        <Link to="/" className="mkt-logo" aria-label="QualiPulse">
          QualiPulse <span className="mkt-logo-dot" aria-hidden="true" />
        </Link>
        <div className="mkt-nav-links mkt-nav-links--always">
          <LanguageSwitcher variant="dark" />
          <Link to="/login" className="mkt-nav-login">{t("nav.login")}</Link>
          <Link to={signupPath} className="mkt-btn mkt-btn-primary mkt-nav-cta" onClick={trackStart("nav")}>
            {t("nav.startTrial")}
          </Link>
        </div>
      </nav>

      <header className="mkt-hero mkt-uc-hero">
        <div className="mkt-wrap">
          <nav className="mkt-uc-crumbs" aria-label="Breadcrumb">
            <Link to="/">{t("useCases.pages.common.backHome")}</Link>
            <span aria-hidden="true">/</span>
            <span>{t(`${item}.persona`)}</span>
          </nav>
          <h1 className="mkt-h1">{t(`${page}.h1`)}</h1>
          <p className="mkt-hero-sub">{t(`${page}.sub`)}</p>
          <div className="mkt-hero-ctas">
            <Link to={signupPath} className="mkt-btn mkt-btn-primary mkt-btn-lg" onClick={trackStart("hero")}>
              {t("useCases.pages.common.ctaPrimary")}
            </Link>
            <a href="#design" className="mkt-btn mkt-btn-ghost">{t("useCases.learnMore")}</a>
          </div>
          <div className="mkt-hero-facts">
            {facts.map((fact) => (
              <span key={fact}><span className="mkt-fact-tick" aria-hidden="true">●</span>{fact}</span>
            ))}
          </div>
        </div>
      </header>

      <section className="mkt-section visible" id="design">
        <div className="mkt-wrap mkt-uc-two">
          <div>
            <span className="mkt-eyebrow">{t("useCases.pages.common.whenTitle")}</span>
            <ul className="mkt-uc-when">
              {when.map((line) => <li key={line}>{line}</li>)}
            </ul>
          </div>
          <div className="mkt-uc-design">
            <span className="mkt-eyebrow">{t("useCases.pages.common.designTitle")}</span>
            <dl>
              <dt>{t("useCases.pages.common.rows.participants")}</dt><dd>{design.participants}</dd>
              <dt>{t("useCases.pages.common.rows.duration")}</dt><dd>{design.duration}</dd>
              <dt>{t("useCases.pages.common.rows.field")}</dt><dd>{design.field}</dd>
              <dt>{t("useCases.pages.common.rows.deliverable")}</dt><dd>{design.deliverable}</dd>
            </dl>
          </div>
        </div>
      </section>

      <section className="mkt-section mkt-dark visible">
        <div className="mkt-wrap">
          <div className="mkt-section-head">
            <span className="mkt-eyebrow">{t("useCases.sampleLabel")}</span>
            <h2>{t("useCases.pages.common.questionsTitle")}</h2>
            <p>{t("useCases.pages.common.questionsNote")}</p>
          </div>
          <ol className="mkt-uc-questions">
            {questions.map((q, i) => (
              <li key={q}>
                <span className="mkt-guide-num">{i + 1}</span>
                <span>{q}</span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mkt-section visible">
        <div className="mkt-wrap mkt-uc-two">
          <div>
            <span className="mkt-eyebrow">{t("useCases.pages.common.outputTitle")}</span>
            <div className="mkt-uc-finding">
              <div className="mkt-uc-finding-theme">{finding.theme}</div>
              <p className="mkt-uc-finding-stat">{finding.stat}</p>
              <blockquote>
                <Trans t={t} i18nKey={`${page}.output.quote`} components={{ m: <mark /> }} />
              </blockquote>
              <p className="mkt-uc-finding-note">{t("useCases.pages.common.outputNote")}</p>
            </div>
          </div>
          <div>
            <span className="mkt-eyebrow">{t("useCases.pages.common.whatYouGetTitle")}</span>
            <ul className="mkt-uc-when">
              {whatYouGet.map((line) => <li key={line}>{line}</li>)}
            </ul>
          </div>
        </div>
      </section>

      <section className="mkt-final mkt-dark">
        <div className="mkt-wrap">
          <span className="mkt-eyebrow">{t("finalCta.eyebrow")}</span>
          <h2>{t("useCases.pages.common.ctaTitle")}</h2>
          <p>{t("useCases.pages.common.ctaSub")}</p>
          <div className="mkt-hero-ctas mkt-final-ctas">
            <Link to={signupPath} className="mkt-btn mkt-btn-primary mkt-btn-lg" onClick={trackStart("final")}>
              {t("useCases.pages.common.ctaPrimary")}
            </Link>
            <Link to="/#pricing" className="mkt-btn mkt-btn-ghost">{t("useCases.pages.common.ctaSecondary")}</Link>
          </div>
        </div>
      </section>

      <section className="mkt-section mkt-section-tight visible">
        <div className="mkt-wrap">
          <span className="mkt-eyebrow">{t("useCases.pages.common.otherTitle")}</span>
          <div className="mkt-uc-other">
            {others.map((u) => (
              <Link key={u.slug} to={`/use-cases/${u.slug}`} className="mkt-uc-other-link">
                <span className="mkt-uc-persona">{t(`useCases.items.${u.key}.persona`)}</span>
                <strong>{t(`useCases.items.${u.key}.title`)}</strong>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <footer className="mkt-footer mkt-footer--compact">
        <div className="mkt-wrap mkt-footer-bottom">
          <span>{t("footer.copy")}</span>
          <span className="mkt-uc-footer-links">
            <Link to="/#pricing">{t("footer.pricingLink")}</Link>
            <Link to="/privacy">{t("footer.privacy")}</Link>
            <Link to="/subprocessors">{t("footer.subprocessors")}</Link>
          </span>
        </div>
      </footer>
    </div>
  );
}
