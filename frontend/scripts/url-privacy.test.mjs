// No personal data in an address (IR-918). Run with `npm run test:security`.
//
// An address ends up in browser history, proxy and server logs, the Referer
// header and anything a user pastes into a chat. Every query-string key the UI
// builds or reads must be named in query-keys.json with the reason it is safe;
// a key that is not named fails here until someone has decided it carries
// nothing personal. This reads the source on every run (it is not a crawler),
// so it cannot go stale the way a bundler-expanded glob can. The two builders
// that take structured input are exercised in src/lib/urlPrivacy.test.ts.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(here, "..", "src");
const ALLOWED = JSON.parse(readFileSync(path.join(here, "query-keys.json"), "utf8")).keys;

/** Words that mean a value is about a person. None may be an allowed key. */
const PERSONAL = /(e-?mail|name|phone|mobile|password|passwd|token|jwt|secret|orcid|student|username|user|author|owner|adviser|advisor|reviewer|surname|birth|dob|address|ssn)/i;

/** Every query-string key one file's text writes into, or reads out of, an address. */
function queryKeysIn(text) {
  const keys = new Set();
  // `/records/1?page=2&turn=3`. A `&key=` that follows a `#` in the same unbroken
  // run is a URL fragment parameter (`/activate#uid=..&token=..`, IR-928): the
  // browser never sends a fragment to the server, a log or a Referer, which is
  // why that secret lives there. Only `&` is skipped; a `?key=` always counts.
  for (const m of text.matchAll(/([?&])([a-z][a-zA-Z_]*)=/g)) {
    const before = text.slice(0, m.index);
    const inFragment = m[1] === "&" && /#[^\s"'`?]*$/.test(before);
    if (!inFragment) keys.add(m[2]);
  }
  // params.set("page", ...), searchParams.get("q"), next.delete("section")
  for (const m of text.matchAll(/\b(?:params|searchParams|next|prev|query)\.(?:set|get|getAll|has|delete|append)\(\s*["'`]([A-Za-z_]+)["'`]/g)) keys.add(m[1]);
  // const PUBLISH_PARAM = "publish"
  for (const m of text.matchAll(/\b[A-Z_]*PARAM[A-Z_]*\s*=\s*["']([A-Za-z_]+)["']/g)) keys.add(m[1]);
  // new URLSearchParams({ reason: "..." })
  for (const block of text.matchAll(/new URLSearchParams\(\{([^}]*)\}\)/g)) {
    for (const m of block[1].matchAll(/([A-Za-z_]+)\s*:/g)) keys.add(m[1]);
  }
  return keys;
}

function* sourceFiles(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== "test") yield* sourceFiles(full);
    } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.(test|spec|d)\.(ts|tsx)$/.test(entry.name)) {
      yield full;
    }
  }
}

describe("the key finder", () => {
  it("finds keys written in a link, a params call, a constant and a params object", () => {
    const text = [
      "const a = `/records/${id}?page=2&turn=3`;",
      'params.set("section", "x"); searchParams.get("q"); next.delete("tab");',
      'const PUBLISH_PARAM = "publish";',
      'new URLSearchParams({ reason: "session_expired", other: 1 });',
    ].join("\n");
    assert.deepEqual([...queryKeysIn(text)].sort(), ["other", "page", "publish", "q", "reason", "section", "tab", "turn"]);
  });

  it("does not take FormData fields for address keys", () => {
    assert.deepEqual([...queryKeysIn('fd.append("record", String(id)); body.append("photo", p);')], []);
  });

  it("finds a personal key written into a link", () => {
    assert.deepEqual([...queryKeysIn("`/records/1?email=${e}`")], ["email"]);
  });

  it("does not count a parameter in the URL fragment, which is never sent to the server (IR-928)", () => {
    assert.deepEqual([...queryKeysIn("`/activate#uid=${u}&token=${t}`")], []);
    assert.deepEqual([...queryKeysIn("const m = /^#uid=([A-Za-z0-9_-]+)&token=([A-Za-z0-9_-]+)$/.exec(hash);")], []);
  });

  it("still counts a token in a real query string, and a key after the fragment has ended", () => {
    assert.deepEqual([...queryKeysIn("`/activate?uid=${u}&token=${t}`")].sort(), ["token", "uid"]);
    assert.deepEqual([...queryKeysIn('a = "/x#top"; b = "/y?email=1"')], ["email"]);
  });
});

describe("query-string keys the UI builds or reads", () => {
  const found = new Map();
  let files = 0;
  for (const file of sourceFiles(SRC)) {
    files += 1;
    for (const key of queryKeysIn(readFileSync(file, "utf8"))) {
      found.set(key, [...(found.get(key) ?? []), path.relative(SRC, file).split(path.sep).join("/")]);
    }
  }

  it("finds the keys at all, so a broken pattern cannot pass silently", () => {
    assert.ok(files > 100, `only ${files} source files read`);
    for (const key of ["page", "turn", "publish", "next", "section", "q"]) assert.ok(found.has(key), key);
  });

  it("every key is one a person has decided carries nothing personal", () => {
    const unknown = [...found].filter(([key]) => !(key in ALLOWED)).map(([key, where]) => `${key} (${where.join(", ")})`);
    assert.deepEqual(unknown, [], "Name each new key in scripts/query-keys.json with why it is safe");
  });

  it("no allowed key is named after personal data", () => {
    assert.deepEqual(Object.keys(ALLOWED).filter((key) => PERSONAL.test(key)), []);
  });

  it("the list does not keep keys the UI no longer uses", () => {
    assert.deepEqual(Object.keys(ALLOWED).filter((key) => !found.has(key)), []);
  });
});
