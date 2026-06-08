import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

// EN namespaces
import enCommon from "./locales/en/common.json";
import enAuth from "./locales/en/auth.json";
import enDashboard from "./locales/en/dashboard.json";
import enProject from "./locales/en/project.json";
import enInterview from "./locales/en/interview.json";
import enAnalysis from "./locales/en/analysis.json";
import enMarketing from "./locales/en/marketing.json";
import enSettings from "./locales/en/settings.json";
import enAffiliate from "./locales/en/affiliate.json";
import enOnboarding from "./locales/en/onboarding.json";
import enPaywall from "./locales/en/paywall.json";
import enWelcomeSetup from "./locales/en/welcome_setup.json";
import enSurvey from "./locales/en/survey.json";
import enStudy from "./locales/en/study.json";
import enBlog from "./locales/en/blog.json";
import enAdmin from "./locales/en/admin.json";
import enShell from "./locales/en/shell.json";
import enQuantiDemo from "./locales/en/quantiDemo.json";

// FR namespaces
import frCommon from "./locales/fr/common.json";
import frAuth from "./locales/fr/auth.json";
import frDashboard from "./locales/fr/dashboard.json";
import frProject from "./locales/fr/project.json";
import frInterview from "./locales/fr/interview.json";
import frAnalysis from "./locales/fr/analysis.json";
import frMarketing from "./locales/fr/marketing.json";
import frSettings from "./locales/fr/settings.json";
import frAffiliate from "./locales/fr/affiliate.json";
import frOnboarding from "./locales/fr/onboarding.json";
import frPaywall from "./locales/fr/paywall.json";
import frWelcomeSetup from "./locales/fr/welcome_setup.json";
import frSurvey from "./locales/fr/survey.json";
import frStudy from "./locales/fr/study.json";
import frBlog from "./locales/fr/blog.json";
import frAdmin from "./locales/fr/admin.json";
import frShell from "./locales/fr/shell.json";
import frQuantiDemo from "./locales/fr/quantiDemo.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: {
        common: enCommon,
        auth: enAuth,
        dashboard: enDashboard,
        project: enProject,
        interview: enInterview,
        analysis: enAnalysis,
        marketing: enMarketing,
        settings: enSettings,
        affiliate: enAffiliate,
        onboarding: enOnboarding,
        paywall: enPaywall,
        welcome_setup: enWelcomeSetup,
        survey: enSurvey,
        study: enStudy,
        blog: enBlog,
        admin: enAdmin,
        shell: enShell,
        quantiDemo: enQuantiDemo,
      },
      fr: {
        common: frCommon,
        auth: frAuth,
        dashboard: frDashboard,
        project: frProject,
        interview: frInterview,
        analysis: frAnalysis,
        marketing: frMarketing,
        settings: frSettings,
        affiliate: frAffiliate,
        onboarding: frOnboarding,
        paywall: frPaywall,
        welcome_setup: frWelcomeSetup,
        survey: frSurvey,
        study: frStudy,
        blog: frBlog,
        admin: frAdmin,
        shell: frShell,
        quantiDemo: frQuantiDemo,
      },
    },
    lng: undefined, // rely on detector
    fallbackLng: "en",
    defaultNS: "common",
    ns: ["common", "auth", "dashboard", "project", "interview", "analysis", "marketing", "settings", "affiliate", "onboarding", "paywall", "welcome_setup", "survey", "study", "blog", "admin", "shell", "quantiDemo"],
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "qp_language",
      caches: ["localStorage"],
    },
    interpolation: {
      escapeValue: false, // React already escapes
    },
  });

// If the detected locale is neither EN nor FR, fall back to English (the
// declared `fallbackLng`). Previously this block defaulted everyone to French
// and the second branch was dead code.
if (!i18n.language || (!i18n.language.startsWith("fr") && !i18n.language.startsWith("en"))) {
  i18n.changeLanguage("en");
}

export default i18n;
