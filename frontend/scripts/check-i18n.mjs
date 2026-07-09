#!/usr/bin/env node
/**
 * i18n key-parity guard.
 *
 * The researcher UI ships in English + French. Every namespace present in
 * BOTH `en` and `fr` must have the exact same key set — a missing/renamed key
 * otherwise degrades to a raw key string or silent English fallback at runtime,
 * caught by nobody. This script fails CI on any divergence.
 *
 * Locales that intentionally ship only the participant `interview.json`
 * (de/es/it/pt) are exempt: we only compare namespaces that exist in a locale.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const localesDir = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "locales");

// The two full-UI locales that must stay in lockstep.
const PRIMARY = ["en", "fr"];

function flatten(obj, prefix = "", out = new Set()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) flatten(v, key, out);
    else out.add(key);
  }
  return out;
}

function loadNamespaces(locale) {
  const dir = join(localesDir, locale);
  const result = {};
  for (const file of readdirSync(dir)) {
    if (!file.endsWith(".json")) continue;
    result[file] = flatten(JSON.parse(readFileSync(join(dir, file), "utf8")));
  }
  return result;
}

const data = Object.fromEntries(PRIMARY.map((l) => [l, loadNamespaces(l)]));
const problems = [];

const namespaces = new Set(PRIMARY.flatMap((l) => Object.keys(data[l])));
for (const ns of [...namespaces].sort()) {
  const en = data.en[ns];
  const fr = data.fr[ns];
  if (!en || !fr) {
    problems.push(`namespace "${ns}" exists in only one of en/fr`);
    continue;
  }
  const missingInFr = [...en].filter((k) => !fr.has(k));
  const missingInEn = [...fr].filter((k) => !en.has(k));
  if (missingInFr.length) problems.push(`${ns}: missing in FR → ${missingInFr.join(", ")}`);
  if (missingInEn.length) problems.push(`${ns}: missing in EN → ${missingInEn.join(", ")}`);
}

if (problems.length) {
  console.error("i18n parity check FAILED:\n" + problems.map((p) => "  - " + p).join("\n"));
  process.exit(1);
}
console.log("i18n parity check passed (en ↔ fr).");
