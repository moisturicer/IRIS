// Self-test for the built-bundle scan (IR-918). Run with `npm run test:security`.
//
// Every fake secret below is assembled at run time from two halves. A literal
// would be a real-looking secret in the repository, and the CI secret scan
// (gitleaks) would rightly report it.
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, it } from "node:test";

import {
  main,
  readEnvFiles,
  scanDirectory,
  scanText,
  secretEnvValues,
  secretLookingPublicVariables,
} from "./bundle-scan.mjs";

const FAKE = {
  awsKey: "AKIA" + "QWERTYUIOP123456",
  githubToken: "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
  googleKey: "AIza" + "SyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q",
  openAiKey: "sk-" + "proj-Abcdefghijklmnopqrstuvwx1234",
  slackToken: "xoxb-" + "123456789012-abcdefghijkl",
  jwt: "eyJhbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "dBjftJeZ4CVPmB92K27uhbUJU1p1r",
  pem: "-----BEGIN " + "RSA PRIVATE KEY-----",
  urlPassword: "postgres://iris:" + "hunter2hunter2" + "@db.internal:5432/iris",
};

let dist;
beforeEach(() => {
  dist = mkdtempSync(path.join(tmpdir(), "bundle-scan-"));
  mkdirSync(path.join(dist, "assets"));
});
afterEach(() => rmSync(dist, { recursive: true, force: true }));

const plant = (file, text) => writeFileSync(path.join(dist, file), text);
const newLog = () => ({ out: [], err: [] });
const logTo = (log) => ({ log: (s) => log.out.push(s), error: (s) => log.err.push(s) });

describe("secret patterns", () => {
  for (const [name, secret] of Object.entries(FAKE)) {
    it(`finds ${name}`, () => {
      const findings = scanText(`var x="${secret}";`, { file: "assets/app.js", secrets: [] });
      assert.equal(findings.length, 1, JSON.stringify(findings));
      assert.equal(findings[0].file, "assets/app.js");
    });
  }

  it("never puts the whole secret in a finding", () => {
    const [finding] = scanText(`k="${FAKE.githubToken}"`, { file: "a.js", secrets: [] });
    assert.ok(!JSON.stringify(finding).includes(FAKE.githubToken));
  });

  it("leaves ordinary minified code alone", () => {
    const code = 'function a(b){return b.map(c=>c+1)}const task="sk-learn is a library";export{a as default};';
    assert.deepEqual(scanText(code, { file: "a.js", secrets: [] }), []);
  });

  it("does not take a short URL fragment or an id for a secret", () => {
    assert.deepEqual(scanText('href="https://iris.example.edu/records/12?page=3"', { file: "a.html", secrets: [] }), []);
  });
});

describe("values of sensitive environment variables", () => {
  const env = {
    SECRET_KEY: "dj-" + "s3cr3t-value-for-test",
    LLM_API_KEY: "llm-" + "0123456789abcdef",
    EMAIL_HOST_PASSWORD: "pw-" + "correct-horse-battery",
    DB_PASSWORD: "short",
    NODE_ENV: "production",
    PATH: "/usr/bin:/bin",
    DEBUG: "False",
    VITE_API_BASE_URL: "http://localhost:8000/api/v1",
  };

  it("takes names that look secret and values long enough to be one", () => {
    const names = secretEnvValues(env).map((e) => e.name).sort();
    assert.deepEqual(names, ["EMAIL_HOST_PASSWORD", "LLM_API_KEY", "SECRET_KEY"]);
  });

  it("finds such a value anywhere in a file, whatever surrounds it", () => {
    const secrets = secretEnvValues(env);
    const [finding] = scanText(`xx${env.LLM_API_KEY}yy`, { file: "assets/app.js", secrets });
    assert.equal(finding.rule, "env:LLM_API_KEY");
  });

  it("does not name the value, only the variable", () => {
    const secrets = secretEnvValues(env);
    const [finding] = scanText(`"${env.SECRET_KEY}"`, { file: "a.js", secrets });
    assert.ok(!JSON.stringify(finding).includes(env.SECRET_KEY));
  });

  it("flags a public VITE_ variable named like a secret, because Vite inlines every one", () => {
    const names = secretLookingPublicVariables({
      VITE_API_BASE_URL: "x",
      VITE_LLM_API_KEY: "x",
      VITE_ADMIN_PASSWORD: "x",
      VITE_USE_POLLING: "1",
      LLM_API_KEY: "x",
    });
    assert.deepEqual(names.sort(), ["VITE_ADMIN_PASSWORD", "VITE_LLM_API_KEY"]);
  });
});

describe("env files, which Vite inlines but process.env does not show", () => {
  it("reads KEY=value lines from the .env files Vite loads, ignoring comments and quotes", () => {
    const dir = mkdtempSync(path.join(tmpdir(), "bundle-scan-env-"));
    try {
      writeFileSync(path.join(dir, ".env"), '# a comment\nVITE_API_BASE_URL=/api/v1\nSERVICE_TOKEN="tok-0123456789abcdef"\n\nexport OTHER=1\n');
      writeFileSync(path.join(dir, ".env.production.local"), "VITE_VOYAGE_API_KEY=pa-whatever\n");
      assert.deepEqual(readEnvFiles(dir), {
        VITE_API_BASE_URL: "/api/v1",
        SERVICE_TOKEN: "tok-0123456789abcdef",
        OTHER: "1",
        VITE_VOYAGE_API_KEY: "pa-whatever",
      });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("reads nothing when there are none", () => {
    assert.deepEqual(readEnvFiles(dist), {});
  });

  it("a secret value kept only in an env file is found in the build, and a secret-named VITE_ key there fails", () => {
    const envDir = mkdtempSync(path.join(tmpdir(), "bundle-scan-env-"));
    try {
      writeFileSync(path.join(envDir, ".env"), "SERVICE_TOKEN=tok-0123456789abcdef\nVITE_ADMIN_PASSWORD=x\n");
      plant("assets/app.js", 'const t="tok-0123456789abcdef";');
      const log = newLog();
      assert.equal(main([dist], {}, logTo(log), envDir), 1);
      const text = log.err.join("\n");
      assert.match(text, /env:SERVICE_TOKEN/);
      assert.match(text, /VITE_ADMIN_PASSWORD/);
    } finally {
      rmSync(envDir, { recursive: true, force: true });
    }
  });
});

describe("scanDirectory", () => {
  it("reports file and rule for a planted secret in a built asset (the self-test)", () => {
    plant("index.html", "<!doctype html><title>IRIS</title>");
    plant("assets/index-abc123.js", `const k="${FAKE.awsKey}";`);
    const { findings, filesScanned } = scanDirectory(dist, { env: {} });
    assert.equal(filesScanned, 2);
    assert.equal(findings.length, 1);
    assert.equal(findings[0].file, "assets/index-abc123.js");
  });

  it("finds a secret in a source map and a text file, not only in .js", () => {
    plant("assets/app.js.map", `{"sourcesContent":["${FAKE.githubToken}"]}`);
    plant("robots.txt", FAKE.googleKey);
    assert.equal(scanDirectory(dist, { env: {} }).findings.length, 2);
  });

  it("is clean for a build with nothing in it", () => {
    plant("index.html", "<!doctype html>");
    plant("assets/app.js", "console.log(1)");
    assert.deepEqual(scanDirectory(dist, { env: {} }).findings, []);
  });

  it("skips binary assets without reading them as text", () => {
    writeFileSync(path.join(dist, "assets/font.woff2"), Buffer.from([0, 1, 2, 0xff, 0xfe]));
    plant("index.html", "<!doctype html>");
    assert.equal(scanDirectory(dist, { env: {} }).filesScanned, 1);
  });

  it("throws on a directory that is missing or empty, so a skipped build cannot pass", () => {
    assert.throws(() => scanDirectory(path.join(dist, "nope"), { env: {} }), /not found/i);
    assert.throws(() => scanDirectory(dist, { env: {} }), /nothing to scan/i);
  });
});

describe("main (the command CI runs)", () => {
  it("exits 0 for a clean build and says how much it scanned", () => {
    plant("index.html", "<!doctype html>");
    const log = newLog();
    assert.equal(main([dist], {}, logTo(log)), 0);
    assert.match(log.out.join("\n"), /1 file/);
  });

  it("exits 1 for a planted secret and names the file", () => {
    plant("assets/app.js", `x="${FAKE.slackToken}"`);
    const log = newLog();
    assert.equal(main([dist], {}, logTo(log)), 1);
    assert.match(log.err.join("\n"), /assets\/app\.js/);
  });

  it("exits 1 when the build holds the value of a sensitive environment variable", () => {
    plant("assets/app.js", 'const a="llm-0123456789abcdef";');
    assert.equal(main([dist], { LLM_API_KEY: "llm-0123456789abcdef" }, logTo(newLog())), 1);
  });

  it("exits 1 for a secret-named VITE_ variable even when the build text is clean", () => {
    plant("index.html", "<!doctype html>");
    const log = newLog();
    assert.equal(main([dist], { VITE_VOYAGE_API_KEY: "whatever" }, logTo(log)), 1);
    assert.match(log.err.join("\n"), /VITE_VOYAGE_API_KEY/);
  });

  it("exits 2 when there is no build to scan", () => {
    assert.equal(main([path.join(dist, "nope")], {}, logTo(newLog())), 2);
  });
});
