/**
 * How MetadataForm marks its fields (IR-585): the optional ones in their label,
 * the required ones as `aria-required` and nothing visible.
 */
import { FormProvider, useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";

import { renderScreen, screen, within } from "@/test/render";
import type { AdviserOption } from "@/types/auth";

import { MetadataForm } from "./MetadataForm";
import { emptyMetadata, type MetadataValues } from "./metadataSchema";

const ADVISERS = [{ id: 7, first_name: "Ada", last_name: "Lovelace" }] as unknown as AdviserOption[];

function Harness({ submitted = false }: { submitted?: boolean }) {
  const form = useForm<MetadataValues>({ defaultValues: emptyMetadata("Grace Hopper") });
  return (
    <FormProvider {...form}>
      <MetadataForm
        advisers={ADVISERS}
        classifications={[{ id: 1, name: "Computing" }] as never}
        psceds={[{ id: 1, name: "Information Technology" }] as never}
        selfId={null}
        moreOpen
        onMoreOpenChange={() => {}}
        submitted={submitted}
      />
    </FormProvider>
  );
}

describe("MetadataForm markers", () => {
  it("announces Title, Abstract, Year, Adviser and the author entry as required, and writes nothing", () => {
    renderScreen(<Harness />);

    for (const name of [/^Title/, /^Abstract/, /^Authors/]) {
      expect(screen.getByRole("textbox", { name })).toBeRequired();
    }
    expect(screen.getByRole("spinbutton", { name: /^Year \(completed\)/ })).toBeRequired();
    expect(screen.getByRole("combobox", { name: /^Adviser/ })).toBeRequired();
    expect(screen.queryByText(/\(required\)/)).not.toBeInTheDocument();
    expect(screen.queryByText("*")).not.toBeInTheDocument();
  });

  it("puts (optional) in the name of Field of research and PSCED only", () => {
    renderScreen(<Harness />);

    expect(screen.getByRole("combobox", { name: "Field of research (optional)" })).not.toBeRequired();
    expect(screen.getByRole("combobox", { name: "PSCED classification (optional)" })).not.toBeRequired();
    // The flag checkboxes stay unmarked.
    const flags = screen.getByRole("group", { name: "Flag for your adviser" });
    expect(within(flags).queryByText(/optional/i)).not.toBeInTheDocument();
  });

  it("gives a submitted record's fixed Adviser no required state", () => {
    renderScreen(<Harness submitted />);

    expect(screen.queryByRole("combobox", { name: /^Adviser/ })).not.toBeInTheDocument();
    expect(screen.getByText("Adviser")).toBeInTheDocument();
  });
});
