/**
 * Build-time prerender of the public routes (run by `npm run build` after
 * `vite build` + the SSR bundle build; see package.json).
 *
 * For each route in src/prerender/entry.tsx it renders the page to HTML,
 * merges the useHead() specs the page declared during render (title, metas,
 * canonical, JSON-LD), and writes a static file into dist/:
 *
 *   /            -> dist/home.html          (nginx `location = /` serves it;
 *                                            dist/index.html stays the empty
 *                                            SPA shell for app routes)
 *   /terms  etc. -> dist/terms/index.html   (served by try_files $uri/)
 *
 * The client bundle mounts over the prerendered markup and re-renders, so
 * this only changes what non-JS clients (crawlers, AI search, link
 * unfurlers) see.
 *
 * Prerender language is French: the product's default audience and the SEO
 * content strategy are FR-first, and URLs are not language-split so each
 * URL gets exactly one snapshot.
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const LANG = "fr";
const ORIGIN = "https://app.qualipulse.com";

// Storage stubs: a few modules (useAuth, referral capture) read
// localStorage during render. window/document stay undefined on purpose so
// `typeof window !== "undefined"` guards keep taking their server path.
const storageStub = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.localStorage = storageStub;
globalThis.sessionStorage = storageStub;

const { renderRoute, PRERENDER_PATHS } = await import("../dist-ssr/entry.js");

const distDir = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const template = readFileSync(join(distDir, "index.html"), "utf8");

const escapeHtml = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Merge head specs in mount order: later values win per identity. */
function mergeHeads(heads) {
  const merged = { title: undefined, metas: new Map(), links: new Map(), jsonLd: [] };
  for (const spec of heads) {
    if (spec.title) merged.title = spec.title;
    for (const m of spec.metas ?? []) {
      merged.metas.set(m.name ?? m.property ?? JSON.stringify(m), m);
    }
    for (const l of spec.links ?? []) {
      merged.links.set(l.rel ?? JSON.stringify(l), l);
    }
    if (spec.jsonLd) merged.jsonLd.push(spec.jsonLd);
  }
  return merged;
}

function attrsToTag(tag, attrs) {
  const a = Object.entries(attrs)
    .map(([k, v]) => `${k}="${escapeHtml(String(v))}"`)
    .join(" ");
  return `<${tag} ${a} />`;
}

function buildPage(path, html, heads) {
  const head = mergeHeads(heads);
  let page = template;

  page = page.replace('<html lang="en">', `<html lang="${LANG}">`);
  page = page.replace('<div id="root"></div>', `<div id="root">${html}</div>`);

  if (head.title) {
    page = page.replace(/<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(head.title)}</title>`);
    head.metas.set("og:title", { property: "og:title", content: head.title });
  }

  // Per-route URL identity, overridable by the page's own spec.
  const url = ORIGIN + (path === "/" ? "/" : path);
  if (!head.links.has("canonical")) head.links.set("canonical", { rel: "canonical", href: url });
  if (!head.metas.has("og:url")) head.metas.set("og:url", { property: "og:url", content: url });

  const extraTags = [];
  for (const m of head.metas.values()) {
    const identity = m.name
      ? new RegExp(`<meta\\s+name="${m.name}"[^>]*/?>`)
      : new RegExp(`<meta\\s+property="${m.property}"[^>]*/?>`);
    const tag = attrsToTag("meta", m);
    if (identity.test(page)) page = page.replace(identity, tag);
    else extraTags.push(tag);
  }
  for (const l of head.links.values()) {
    extraTags.push(attrsToTag("link", l));
  }
  for (const j of head.jsonLd) {
    // JSON-LD data blocks are not executed, so the CSP script-src policy
    // does not apply to them.
    extraTags.push(`<script type="application/ld+json">${JSON.stringify(j)}</script>`);
  }
  if (extraTags.length) {
    page = page.replace("</head>", `    ${extraTags.join("\n    ")}\n  </head>`);
  }
  return page;
}

let failures = 0;
for (const path of PRERENDER_PATHS) {
  const { html, heads } = await renderRoute(path, LANG);
  if (html.length < 500) {
    console.error(`prerender: ${path} rendered only ${html.length} chars — refusing to ship it`);
    failures += 1;
    continue;
  }
  const page = buildPage(path, html, heads);
  const outFile =
    path === "/" ? join(distDir, "home.html") : join(distDir, path.slice(1), "index.html");
  mkdirSync(dirname(outFile), { recursive: true });
  writeFileSync(outFile, page);
  console.log(`prerender: ${path} -> ${outFile.slice(distDir.length + 1)} (${page.length} bytes)`);
}

if (failures > 0) {
  console.error(`prerender: ${failures} route(s) failed`);
  process.exit(1);
}
