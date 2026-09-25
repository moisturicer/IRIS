/**
 * Wizard validation errors without colour (IR-360).
 *
 * Once the palette is white, black, grey and maroon, an error is maroon and so
 * is the brand, so the tone alone no longer says "error". Every message a step
 * shows beside a field carries a glyph as well. The glyph is aria-hidden, so
 * what a screen reader announces is the sentence, exactly as before.
 *
 * Errors are set on the form directly: this tests how a step shows an error,
 * not the schema that raises it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FormProvider, useForm, type FieldPath } from "react-hook-form";
import { useEffect, type ReactNode } from "react";

import { renderScreen, screen } from "@/test/render";
import type { RecordFormValues } from "../recordFormSchema";

import { PaperDetailsStep } from "./PaperDetailsStep";
import { RecordDetailsStep } from "./RecordDetailsStep";
import { TitleAbstractStep } from "./TitleAbstractStep";
import { TypeRouteStep } from "./TypeRouteStep";

vi.mock("@/api/records", () => ({
  recordsApi: {
    recordTypes: vi.fn(),
    classifications: vi.fn(),
    pscedList: vi.fn(),
  },
}));

vi.mock("@/api/accounts", () => ({
  accountsApi: { listAdvisers: vi.fn() },
}));

const { recordsApi } = await import("@/api/records");
const { accountsApi } = await import("@/api/accounts");

function page<T>(results: T[]) {
  return { data: { count: results.length, next: null, previous: null, results } };
}

beforeEach(() => {
  vi.mocked(recordsApi.recordTypes).mockResolvedValue(page([{ id: 1, name: "Proposal" }]) as never);
  vi.mocked(recordsApi.classifications).mockResolvedValue(page([]) as never);
  vi.mocked(recordsApi.pscedList).mockResolvedValue(page([]) as never);
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue(page([]) as never);
});

type Errors = Partial<Record<FieldPath<RecordFormValues>, string>>;

function WithErrors({ errors, children }: { errors: Errors; children: ReactNode }) {
  const methods = useForm<RecordFormValues>({
    defaultValues: { record_type: "1", authors: [], title: "", abstract: "" },
  });
  useEffect(() => {
    for (const [name, message] of Object.entries(errors)) {
      methods.setError(name as FieldPath<RecordFormValues>, { message });
    }
  }, [methods, errors]);
  return <FormProvider {...methods}>{children}</FormProvider>;
}

/** The element holding `message`, which must also hold an aria-hidden glyph. */
async function expectGlyphBeside(message: string) {
  const error = await screen.findByText(message);
  const glyph = error.querySelector("i.fa-circle-exclamation");
  expect(glyph, `"${message}" has no error glyph`).not.toBeNull();
  expect(glyph).toHaveAttribute("aria-hidden");
}

const TITLE = "Title must be at least 5 characters.";
const ABSTRACT = "Abstract must be at least 30 characters.";
const RECORD_TYPE = "Record type is required.";
const ADVISER = "An adviser must be assigned before a Proposal can be submitted.";
const AUTHORS = "At least one author is required.";

describe("wizard field errors carry a glyph as well as a tone", () => {
  it("in Submit Disclosure's Details step", async () => {
    renderScreen(
      <WithErrors errors={{ title: TITLE, abstract: ABSTRACT, adviser: ADVISER, authors: AUTHORS }}>
        <PaperDetailsStep />
      </WithErrors>,
    );

    for (const message of [TITLE, ABSTRACT, ADVISER, AUTHORS]) await expectGlyphBeside(message);
  });

  it("in Submit Disclosure's type step", async () => {
    renderScreen(
      <WithErrors errors={{ record_type: RECORD_TYPE }}>
        <TypeRouteStep />
      </WithErrors>,
    );

    await expectGlyphBeside(RECORD_TYPE);
  });

  it("in Edit Record's title and details steps", async () => {
    renderScreen(
      <WithErrors
        errors={{ title: TITLE, abstract: ABSTRACT, record_type: RECORD_TYPE, adviser: ADVISER, authors: AUTHORS }}
      >
        <TitleAbstractStep />
        <RecordDetailsStep />
      </WithErrors>,
    );

    for (const message of [TITLE, ABSTRACT, RECORD_TYPE, ADVISER, AUTHORS]) await expectGlyphBeside(message);
  });

  it("keeps the error as the field's description, announced as the sentence alone", async () => {
    renderScreen(
      <WithErrors errors={{ title: TITLE, abstract: ABSTRACT }}>
        <PaperDetailsStep />
      </WithErrors>,
    );

    const title = await screen.findByRole("textbox", { name: /^Title/ });
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(title).toHaveAccessibleDescription(TITLE);
    expect(screen.getByRole("textbox", { name: /^Abstract/ })).toHaveAccessibleDescription(ABSTRACT);
  });
});
