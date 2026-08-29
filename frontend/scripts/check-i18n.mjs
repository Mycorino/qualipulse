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
 *
 * Parity alone is not enough. A key that is missing from BOTH locales looks
 * perfectly in parity, and `t("x", { defaultValue: "..." })` then renders the
 * English default to every language, so the gap is invisible in EN and shows
 * up only as stray English in the FR UI. That is exactly how the
 * "Ask profile questions before the interview" toggle shipped untranslated.
 * So we also check that every key referenced in the source actually exists.
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

// ── Referenced-but-undefined keys ───────────────────────────────────────────
// Walks the source for t("...") style calls and checks the key resolves
// somewhere in EN. `defaultValue` is deliberately NOT treated as an excuse:
// it is the mechanism that hides the problem.
//
// Resolution is intentionally permissive about WHICH namespace a key lives
// in. A component does useTranslation("survey") and then t("dashboard.x"),
// so the leading segment is usually a key inside the bound namespace, not a
// filename. Requiring the right namespace produced a wall of false
// positives, so we only assert the key exists somewhere; the goal is to
// catch keys that exist nowhere at all.
const srcDir = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== "locales") walk(full, files);
    } else if (/\.(tsx|ts)$/.test(entry)) files.push(full);
  }
  return files;
}

// Every key path defined anywhere in EN, plus each path with its namespace
// prefixed, so both t("setup.x") against project.json and a fully qualified
// "project.setup.x" resolve.
const definedEn = new Set();
for (const [file, keys] of Object.entries(data.en)) {
  const ns = file.replace(/\.json$/, "");
  for (const k of keys) {
    definedEn.add(k);
    definedEn.add(`${ns}.${k}`);
  }
}

// Pre-existing gaps are frozen in a baseline so the guard can block NEW ones
// without demanding all of them be translated at once. Shrink it, never grow.
const baselinePath = join(dirname(fileURLToPath(import.meta.url)), "i18n-untranslated-baseline.json");
const baseline = new Set(JSON.parse(readFileSync(baselinePath, "utf8")).keys);

const undefinedKeys = [];
const fixedSinceBaseline = [];
const seen = new Set();
for (const file of walk(srcDir)) {
  const src = readFileSync(file, "utf8");
  for (const m of src.matchAll(/\bt[A-Za-z]*\(\s*"([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)"/g)) {
    const id = m[1];
    // i18next resolves a plural key to `id_one` / `id_other` at runtime, so
    // source only ever references the base. Treat the base as defined when
    // either plural form exists, otherwise every plural key looks missing.
    const defined =
      definedEn.has(id) || definedEn.has(`${id}_one`) || definedEn.has(`${id}_other`);
    if (seen.has(id) || defined) continue;
    seen.add(id);
    if (baseline.has(id)) continue; // known debt, tracked in the baseline
    undefinedKeys.push(`${id}  (${file.replace(srcDir, "src")})`);
  }
}
if (undefinedKeys.length) {
  problems.push(
    "NEW keys referenced in source but defined nowhere in EN (a defaultValue " +
      "leaks English into every other language). Add them to en+fr, or to " +
      `${"scripts/i18n-untranslated-baseline.json"} if genuinely English-only:\n      ` +
      undefinedKeys.sort().join("\n      ")
  );
}

// Keep the baseline honest: once a key is translated it must leave the file,
// otherwise the debt looks permanent and the list stops meaning anything.
for (const id of baseline) {
  if (definedEn.has(id)) fixedSinceBaseline.push(id);
}
if (fixedSinceBaseline.length) {
  problems.push(
    "these keys are now defined and must be REMOVED from " +
      "scripts/i18n-untranslated-baseline.json:\n      " +
      fixedSinceBaseline.sort().join("\n      ")
  );
}

if (problems.length) {
  console.error("i18n parity check FAILED:\n" + problems.map((p) => "  - " + p).join("\n"));
  process.exit(1);
}
console.log("i18n parity check passed (en ↔ fr).");
