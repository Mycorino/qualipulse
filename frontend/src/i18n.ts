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
      },
    },
    lng: undefined, // rely on detector
    fallbackLng: "en",
    defaultNS: "common",
    ns: ["common", "auth", "dashboard", "project", "interview", "analysis", "marketing", "settings", "affiliate"],
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "qp_language",
      caches: ["localStorage"],
    },
    interpolation: {
      escapeValue: false, // React already escapes
    },
  });

// Default to French if no language detected
if (!i18n.language || (!i18n.language.startsWith("fr") && !i18n.language.startsWith("en"))) {
  i18n.changeLanguage("fr");
} else if (!i18n.language.startsWith("fr") && !i18n.language.startsWith("en")) {
  i18n.changeLanguage("fr");
}

export default i18n;
