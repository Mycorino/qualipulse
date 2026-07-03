import { useEffect } from "react";

/**
 * Minimal SPA head manager — replaces react-helmet-async, which silently
 * stopped applying tags in this app (both v2 and v3; the dispatcher never
 * fired). Direct DOM management in an effect is deterministic and
 * StrictMode-safe.
 *
 * Behaviour:
 * - `title` is set on mount/update and restored to the static default on
 *   unmount (route changes unmount the old page before the new one mounts,
 *   so the incoming page's own useHead wins).
 * - For each meta/link: if a static tag with the same identity (name /
 *   property / rel) already exists in <head>, its attributes are overridden
 *   and restored on cleanup — so we never emit duplicate descriptions or
 *   og: tags next to the index.html defaults. Otherwise a new tag is
 *   created (marked data-qp-head) and removed on cleanup.
 * - `jsonLd` renders one <script type="application/ld+json">.
 */
export interface HeadSpec {
  title?: string;
  metas?: Array<Record<string, string>>;
  links?: Array<Record<string, string>>;
  jsonLd?: object;
}

const DEFAULT_TITLE = typeof document !== "undefined" ? document.title : "";

function identitySelector(tag: "meta" | "link", attrs: Record<string, string>): string | null {
  if (tag === "meta" && attrs.name) return `meta[name="${attrs.name}"]`;
  if (tag === "meta" && attrs.property) return `meta[property="${attrs.property}"]`;
  if (tag === "link" && attrs.rel) return `link[rel="${attrs.rel}"]`;
  return null;
}

export function useHead(spec: HeadSpec): void {
  const serialized = JSON.stringify(spec);

  useEffect(() => {
    const { title, metas = [], links = [], jsonLd } = JSON.parse(serialized) as HeadSpec;
    const cleanups: Array<() => void> = [];

    if (title) {
      document.title = title;
      cleanups.push(() => {
        document.title = DEFAULT_TITLE;
      });
    }

    const applyTag = (tag: "meta" | "link", attrs: Record<string, string>) => {
      const selector = identitySelector(tag, attrs);
      const existing = selector
        ? document.head.querySelector<HTMLElement>(`${selector}:not([data-qp-head])`)
        : null;
      if (existing) {
        const previous: Record<string, string | null> = {};
        for (const [k, v] of Object.entries(attrs)) {
          previous[k] = existing.getAttribute(k);
          existing.setAttribute(k, v);
        }
        cleanups.push(() => {
          for (const [k, old] of Object.entries(previous)) {
            if (old === null) existing.removeAttribute(k);
            else existing.setAttribute(k, old);
          }
        });
      } else {
        const el = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
        el.setAttribute("data-qp-head", "true");
        document.head.appendChild(el);
        cleanups.push(() => el.remove());
      }
    };

    metas.forEach((m) => applyTag("meta", m));
    links.forEach((l) => applyTag("link", l));

    if (jsonLd) {
      const script = document.createElement("script");
      script.type = "application/ld+json";
      script.setAttribute("data-qp-head", "true");
      script.textContent = JSON.stringify(jsonLd);
      document.head.appendChild(script);
      cleanups.push(() => script.remove());
    }

    return () => {
      cleanups.forEach((fn) => fn());
    };
  }, [serialized]);
}
