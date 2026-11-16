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
import { EntryFrame } from "@/components/auth/EntryFrame";

vi.mock("@/config/institution", () => ({
  INSTITUTION: { name: "Example Research University", shortName: "ERU", logo: "example.png", seal: "example-seal.png", emailDomain: "example.edu" },
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

// Audit RES-05 (IR-1098): the full logo's words are about 10 px tall on a
// phone, so below 480 px the masthead shows the seal alone. jsdom has no media
// queries, so what is checked is what the markup commits to.
it("shows the configured seal below 480 px and the full logo from there up", () => {
  renderScreen(<EntryFrame tabs={null}><p>Sheet</p></EntryFrame>);
  const logo = screen.getByRole("img", { name: "Example Research University" });
  expect(logo).toHaveAttribute("src", "example-seal.png");
  const wide = logo.closest("picture")?.querySelector("source");
  expect(wide).toHaveAttribute("media", "(min-width: 480px)");
  expect(wide).toHaveAttribute("srcset", "example.png");
});
