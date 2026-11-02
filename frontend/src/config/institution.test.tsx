import { it, expect, vi } from "vitest";
import { FormProvider, useForm } from "react-hook-form";
import { MetadataForm } from "@/features/records/metadata/MetadataForm";
import type { MetadataValues } from "@/features/records/metadata/metadataSchema";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import type { RecordListItem } from "@/types/records";
import { useAuthStore } from "@/store/auth.store";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent } from "@/test/render";
import SettingsPage from "@/features/settings/SettingsPage";

vi.mock("@/config/institution", () => ({
  INSTITUTION: { name: "Example Research University", shortName: "ERU", logo: "example.png", emailDomain: "example.edu" },
}));

it("identifies the configured institution managing account details", () => {
  useAuthStore.setState({ user: makeUser(), isAuthenticated: true, authReady: true });
  renderScreen(<SettingsPage />, { route: "/settings" });
  expect(screen.getByText(/Managed by Example Research University/)).toBeVisible();
});

function MetadataEditor() {
  const form = useForm<MetadataValues>();
  return <FormProvider {...form}>
    <MetadataForm advisers={[]} classifications={[]} psceds={[]} selfId={null}
      moreOpen={false} onMoreOpenChange={() => {}} />
  </FormProvider>;
}

it("labels institutional research with the configured short name", () => {
  renderScreen(<MetadataEditor />);
  expect(screen.getByRole("option", { name: "Institutional (ERU research)" })).toBeInTheDocument();
});

it("attributes institutional citations to the configured university in every style", async () => {
  renderScreen(<PaperCiteModal record={{ id: 7, title: "Flood resilience", origin: "institutional", authors: [] } as unknown as RecordListItem}
    isOpen onClose={() => {}} />);
  expect(screen.getByRole("dialog")).toHaveTextContent("Example Research University");
  for (const style of ["MLA", "BibTeX"]) {
    await userEvent.click(screen.getByRole("button", { name: style }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Example Research University");
  }
});
