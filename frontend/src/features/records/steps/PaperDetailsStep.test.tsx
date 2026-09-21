/**
 * The wizard's office request for ITSO (IR-266).
 *
 * ADR-021 §5 reversed ADR-018's rule that ITSO reviews Projects only, so the
 * "Which offices should review this?" group offers ITSO for Thesis/Research
 * too, and the IP answer pre-checks it for both types. The backend half of the
 * rule is `backend/apps/reviews/test_itso_for_thesis.py`.
 *
 * The step is rendered inside a real `react-hook-form` provider rather than
 * the whole wizard: the record type is chosen on step 1, and driving three
 * steps to reach one checkbox would test the stepper, not the rule.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FormProvider, useForm } from "react-hook-form";
import type { ReactNode } from "react";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent } from "@/test/render";
import type { RecordFormValues } from "../recordFormSchema";

import { PaperDetailsStep } from "./PaperDetailsStep";

const RECORD_TYPES = [
  { id: 1, name: "Proposal" },
  { id: 2, name: "Thesis / Research" },
  { id: 3, name: "Project" },
];

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
  vi.mocked(recordsApi.recordTypes).mockResolvedValue(page(RECORD_TYPES) as never);
  vi.mocked(recordsApi.classifications).mockResolvedValue(page([]) as never);
  vi.mocked(recordsApi.pscedList).mockResolvedValue(page([]) as never);
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue(page([]) as never);
});

function Form({ typeName, children }: { typeName: string; children: ReactNode }) {
  const typeId = String(RECORD_TYPES.find((t) => t.name === typeName)!.id);
  const methods = useForm<RecordFormValues>({
    defaultValues: {
      record_type: typeId,
      authors: [],
      is_ip: false,
      for_commercialization: false,
      community_extension: false,
      requires_ethics_review: false,
      requested_itso: false,
      requested_ierc: false,
      requested_ktto: false,
    } as Partial<RecordFormValues>,
  });
  return <FormProvider {...methods}>{children}</FormProvider>;
}

function renderStep(typeName: string) {
  return renderScreen(
    <Form typeName={typeName}>
      <PaperDetailsStep />
    </Form>,
  );
}

const ITSO = /^ITSO\b/;
const IP_SIGNAL = "This work involves intellectual property worth protecting";

describe("PaperDetailsStep — the ITSO request", () => {
  it.each(["Thesis / Research", "Project"])("offers ITSO for %s", async (typeName) => {
    const { container } = renderStep(typeName);

    const itso = await screen.findByRole("checkbox", { name: ITSO });
    expect(itso).not.toBeChecked();

    await expectNoBlockingA11yViolations(container);
  });

  it.each(["Thesis / Research", "Project"])(
    "pre-checks ITSO from the IP answer for %s, and the student can still uncheck it",
    async (typeName) => {
      const user = userEvent.setup();
      renderStep(typeName);
      const itso = await screen.findByRole("checkbox", { name: ITSO });

      await user.click(screen.getByRole("checkbox", { name: IP_SIGNAL }));
      expect(itso).toBeChecked();

      await user.click(itso);
      expect(itso).not.toBeChecked();
    },
  );

  it("does not offer ITSO for a Proposal, which has no office routing", async () => {
    renderStep("Proposal");

    // Wait for the record types to load, so the absence below is not just an
    // early render before the step knows the type.
    await screen.findByRole("option", { name: "Select a field" });
    expect(screen.queryByRole("checkbox", { name: ITSO })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("group", { name: "Which offices should review this?" }),
    ).not.toBeInTheDocument();
  });
});
