#!/usr/bin/env node
// Scan the BUILT frontend (dist/) for secrets (IR-918).
//
// Why this exists: CI's secret scan reads the repository and `npm audit` reads
// the lockfile, but neither reads what the browser is actually handed. Vite
// inlines every `VITE_*` variable and every imported file into the bundle, so a
// key can reach every visitor without ever appearing in a committed file.
//
// Three checks, all on the output of `npm run build`:
//   1. high-confidence secret patterns (cloud keys, tokens, private keys, JWTs,
//      passwords inside URLs);
//   2. the VALUES of environment variables whose names look secret (from the
//      process environment and the `.env*` files Vite also loads), wherever
//      they appear, in whatever shape;
//   3. any `VITE_` variable named like a secret -- Vite would inline it.
//
// Zero dependencies on purpose: a scanner nobody has to install cannot drift.
// A finding names the file and the rule and shows only the first characters of
// what it matched, so the CI log does not become a second leak.
//
// Usage:  node scripts/bundle-scan.mjs [dist-dir]      (default: dist)
// Exit:   0 clean · 1 finding · 2 nothing to scan / bad input
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Text a browser build is made of. Fonts, images and the like are skipped. */
const TEXT_EXTENSIONS = new Set([
  ".js", ".mjs", ".cjs", ".css", ".html", ".htm", ".json", ".map", ".txt",
  ".svg", ".xml", ".webmanifest", ".md", ".yml", ".yaml", ".env",
]);

/** A variable whose NAME says it holds a credential. */
const SECRET_NAME = /(SECRET|PASSWORD|PASSWD|PASSPHRASE|TOKEN|PRIVATE|CREDENTIAL|API_?KEY|ACCESS_?KEY|AUTH_?KEY|(^|_)KEY$)/i;
/** Shorter values are flags, ports and words ("true", "5432"): too common to search for. */
const MIN_SECRET_VALUE_LENGTH = 12;

export const SECRET_PATTERNS = [
  { rule: "private-key", regex: /-----BEGIN (?:[A-Z]+ )?PRIVATE KEY(?: BLOCK)?-----/ },
  { rule: "aws-access-key-id", regex: /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/ },
  { rule: "github-token", regex: /\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b/ },
  { rule: "slack-token", regex: /\bxox[abprs]-[A-Za-z0-9-]{10,}/ },
  { rule: "google-api-key", regex: /\bAIza[0-9A-Za-z_-]{35}\b/ },
  { rule: "secret-key-sk", regex: /\bsk-(?:ant-|proj-|live-)?[A-Za-z0-9_-]{20,}/ },
  { rule: "stripe-key", regex: /\b[rsp]k_(?:live|test)_[A-Za-z0-9]{16,}\b/ },
  { rule: "voyage-key", regex: /\bpa-[A-Za-z0-9_-]{32,}\b/ },
  { rule: "jwt", regex: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/ },
  { rule: "password-in-url", regex: /\b[a-z][a-z0-9+.-]{1,20}:\/\/[^\s/:@"'`<>]{1,64}:[^\s/@"'`<>]{3,}@[^\s/"'`<>]+/i },
];

/** `abcd…` -- enough to find it, not enough to use it. */
const redact = (text) => `${text.slice(0, 4)}… (${text.length} chars)`;

/** Environment variables whose names look secret and whose values are long enough to search for. */
export function secretEnvValues(env) {
  return Object.entries(env)
    .filter(([name, value]) => SECRET_NAME.test(name) && typeof value === "string" && value.length >= MIN_SECRET_VALUE_LENGTH)
    .map(([name, value]) => ({ name, value }));
}

/** `VITE_` names that look secret. Vite puts every `VITE_` variable into the bundle. */
export function secretLookingPublicVariables(env) {
  return Object.keys(env).filter((name) => name.startsWith("VITE_") && SECRET_NAME.test(name));
}

/** Findings in one file's text. `secrets` comes from `secretEnvValues`. */
export function scanText(text, { file, secrets }) {
  const findings = [];
  for (const { rule, regex } of SECRET_PATTERNS) {
    const match = regex.exec(text);
    if (match) findings.push({ file, rule, sample: redact(match[0]) });
  }
  for (const { name, value } of secrets) {
    if (text.includes(value)) findings.push({ file, rule: `env:${name}`, sample: redact(value) });
  }
  return findings;
}

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(full);
    else if (entry.isFile()) yield full;
  }
}

/** Scan every text file under `dir`. Throws when there is nothing to scan: a skipped build must not pass. */
export function scanDirectory(dir, { env }) {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) throw new Error(`Build directory not found: ${dir}`);
  const secrets = secretEnvValues(env);
  const findings = [];
  let filesScanned = 0;
  for (const full of walk(dir)) {
    if (!TEXT_EXTENSIONS.has(path.extname(full).toLowerCase())) continue;
    const file = path.relative(dir, full).split(path.sep).join("/");
    findings.push(...scanText(readFileSync(full, "utf8"), { file, secrets }));
    filesScanned += 1;
  }
  if (filesScanned === 0) throw new Error(`Nothing to scan in ${dir}: no text files. Did the build run?`);
  return { findings, filesScanned };
}

/**
 * KEY=value pairs from the `.env*` files in `dir` (not `.env.example`).
 * Vite inlines `VITE_` values from these files, and they are not in
 * `process.env`, so a scan of the environment alone would never see them.
 */
export function readEnvFiles(dir) {
  const values = {};
  for (const name of readdirSync(dir).filter((n) => /^\.env(\..+)?$/.test(n) && n !== ".env.example").sort()) {
    for (const line of readFileSync(path.join(dir, name), "utf8").split(/\r?\n/)) {
      const match = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
      if (match) values[match[1]] = match[2].replace(/^(["'])(.*)\1$/, "$2");
    }
  }
  return values;
}

/**
 * The command CI runs. Returns the exit code. `envDir`, when given, is a
 * directory whose `.env*` files are read as well as `env` (the CLI passes the
 * working directory; the tests leave it off so a developer's own files cannot
 * change their outcome).
 */
export function main(argv, env, io = console, envDir = null) {
  const dir = argv[0] ?? "dist";
  if (envDir) env = { ...readEnvFiles(envDir), ...env };
  let result;
  try {
    result = scanDirectory(dir, { env });
  } catch (error) {
    io.error(`bundle-scan: ${error.message}`);
    return 2;
  }
  const publicNames = secretLookingPublicVariables(env);
  for (const name of publicNames) {
    io.error(`bundle-scan: ${name} is a VITE_ variable named like a secret; Vite inlines it into the bundle. Rename it or keep it server-side.`);
  }
  for (const { file, rule, sample } of result.findings) {
    io.error(`bundle-scan: ${file}: ${rule}: ${sample}`);
  }
  const failures = result.findings.length + publicNames.length;
  if (failures > 0) {
    io.error(`bundle-scan: ${failures} finding(s) in ${result.filesScanned} file(s) under ${dir}.`);
    return 1;
  }
  io.log(`bundle-scan: clean. ${result.filesScanned} file(s) under ${dir}, ${secretEnvValues(env).length} sensitive variable value(s) checked.`);
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2), process.env, console, process.cwd());
}
