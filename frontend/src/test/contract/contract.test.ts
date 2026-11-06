// @vitest-environment node
/**
 * Do the backend's recorded responses fit the types the screens use? (IR-915)
 *
 * `contracts/<name>.json` at the repository root holds a sample of each
 * covered endpoint's real answer, recorded by the backend's own test
 * (`backend/apps/tests/contract/`), which also fails when an endpoint stops
 * answering with that structure. This is the other half: each sample is
 * validated against a JSON Schema generated from the hand-written type the
 * screen declares for that call (`responses.ts`). A field the type requires
 * and the backend no longer sends, or a field whose kind differs from the type
 * (a `null` where the type says `string`), fails and names the field.
 *
 * A field the backend sends and the type does not declare is allowed: the
 * screen ignores it, and the backend test reports it so the type gets updated.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv from "ajv";
import { createGenerator } from "ts-json-schema-generator";
import { beforeAll, describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(here, "../../..");
const CONTRACTS = path.resolve(FRONTEND, "..", "contracts");

/** Fixture name -> the exported type in `responses.ts` the screen reads it as. */
const TYPE_OF: Record<string, string> = {
  "record-list":              "RecordListResponse",
  "record-detail":            "RecordDetailResponse",
  "record-detail-published":  "RecordDetailResponse",
  "record-tracker":           "RecordTrackerResponse",
  "record-facets":            "RecordFacetsResponse",
  "classifications":          "ClassificationsResponse",
  "record-document-requests": "DocumentRequestsResponse",
  "record-mine":              "RecordMineResponse",
  "library-saves":            "LibrarySavesResponse",
  "reviews-mine":             "ReviewsMineResponse",
  "auth-login":               "LoginResponseBody",
  "user-me":                  "UserMeResponse",
};

interface Fixture {
  route: string;
  method: string;
  as: string;
  sample: unknown;
}

function readFixture(name: string): Fixture {
  return JSON.parse(fs.readFileSync(path.join(CONTRACTS, `${name}.json`), "utf-8")) as Fixture;
}

function onDisk(): string[] {
  return fs.readdirSync(CONTRACTS).filter((f) => f.endsWith(".json")).map((f) => f.slice(0, -5)).sort();
}

describe("recorded backend responses fit the frontend's types", () => {
  const ajv = new Ajv({ allErrors: true, strict: false });
  const validators = new Map<string, ReturnType<typeof ajv.compile>>();

  beforeAll(() => {
    const generator = createGenerator({
      path: path.join(here, "responses.ts"),
      tsconfig: path.join(FRONTEND, "tsconfig.json"),
      type: "*",
      expose: "export",
      skipTypeCheck: true,          // `npm run build` type-checks; this only reads the types
      additionalProperties: true,   // a field the type does not name is the backend's to add
    });
    for (const typeName of new Set(Object.values(TYPE_OF))) {
      validators.set(typeName, ajv.compile(generator.createSchema(typeName)));
    }
    // About 3 s on its own; measured at 70 s when the machine was saturated by other work,
    // and the whole suite's workers share a CI runner, so allow for that.
  }, 180_000);

  function problems(typeName: string, sample: unknown): string[] {
    const validate = validators.get(typeName)!;
    validate(sample);
    return (validate.errors ?? []).map((e) => `${e.instancePath || "(response)"} ${e.message}`);
  }

  it("has a fixture for every mapped type and a type for every fixture", () => {
    expect(onDisk()).toEqual(Object.keys(TYPE_OF).sort());
  });

  for (const [name, typeName] of Object.entries(TYPE_OF)) {
    it(`${name} fits ${typeName}`, () => {
      expect(problems(typeName, readFixture(name).sample)).toEqual([]);
    });
  }

  it("is not vacuous: a sample missing a required field, or with the wrong kind, is refused", () => {
    const detail = readFixture("record-detail").sample as Record<string, unknown>;
    const withoutTitle = { ...detail };
    delete withoutTitle.title;
    expect(problems("RecordDetailResponse", withoutTitle).join("\n")).toContain("title");
    expect(problems("RecordDetailResponse", { ...detail, title: 42 }).join("\n")).toContain("/title");
    expect(problems("RecordDetailResponse", detail)).toEqual([]);
  });
});
