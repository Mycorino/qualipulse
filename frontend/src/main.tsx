import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { HelmetProvider } from "react-helmet-async";
import App from "./App";
import "./index.css";
import "./i18n"; // initialise i18next before rendering
import i18n from "./i18n";
import { ErrorBoundary } from "./components/ErrorBoundary";

// Sync HTML lang attribute with i18n language (WCAG / SEO)
function syncLang(lng: string) {
  document.documentElement.lang = lng.startsWith("fr") ? "fr" : "en";
}
syncLang(i18n.language ?? "en");
i18n.on("languageChanged", syncLang);

// Warm up the backend on app init so Cloud Run has a live instance ready
// by the time the user reaches login or any authenticated page.
// Fire-and-forget — never blocks rendering.
fetch("/api/").catch(() => {});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <HelmetProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </HelmetProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
