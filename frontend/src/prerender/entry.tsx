import type { ComponentType } from "react";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server";
import i18n from "../i18n";
import { ToastProvider } from "../components/Toast";
import type { HeadCollector, HeadSpec } from "../hooks/useHead";
import Marketing from "../pages/Marketing";
import Login from "../pages/Login";
import Signup from "../pages/Signup";
import Terms from "../pages/Terms";
import Privacy from "../pages/Privacy";
import LegalDocument from "../pages/LegalDocument";

/**
 * Build-time prerender entry (see scripts/prerender.mjs).
 *
 * Renders the genuinely public routes (the ones in public/sitemap.xml) to
 * static HTML so crawlers and AI search tools get real content, prices and
 * JSON-LD without executing JavaScript. The client bundle still mounts on
 * top and replaces the markup, so runtime behaviour is unchanged.
 *
 * Pages are rendered directly (not through App.tsx) to avoid the lazy() +
 * auth-redirect machinery, which is meaningless without a browser.
 */
const ROUTES: Record<string, ComponentType> = {
  "/": Marketing,
  "/login": Login,
  "/signup": Signup,
  "/terms": Terms,
  "/privacy": Privacy,
  "/dpa": LegalDocument,
  "/subprocessors": LegalDocument,
  "/participant-notice": LegalDocument,
  "/ai-use-policy": LegalDocument,
  "/retention-policy": LegalDocument,
  // /blog and /blog/:slug are NOT prerendered here: nginx proxies direct hits
  // to the backend's server-rendered pages (services/blog_render.py), which
  // can include per-post content and meta that a build-time snapshot cannot.
};

export const PRERENDER_PATHS = Object.keys(ROUTES);

export interface RenderedRoute {
  html: string;
  /** useHead specs collected during the render pass, in mount order. */
  heads: HeadSpec[];
}

export async function renderRoute(path: string, lang: string): Promise<RenderedRoute> {
  const Page = ROUTES[path];
  if (!Page) throw new Error(`No prerender route registered for ${path}`);

  await i18n.changeLanguage(lang);

  const heads: HeadCollector = [];
  const g = globalThis as { __qpHeadCollector__?: HeadCollector };
  g.__qpHeadCollector__ = heads;
  try {
    const html = renderToString(
      <StaticRouter location={path}>
        <ToastProvider>
          <Page />
        </ToastProvider>
      </StaticRouter>
    );
    return { html, heads };
  } finally {
    delete g.__qpHeadCollector__;
  }
}
