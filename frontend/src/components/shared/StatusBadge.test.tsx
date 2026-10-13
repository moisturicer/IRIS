/**
 * The workflow state badge (IR-259).
 *
 * It shows the label the API wrote (`workflow_state_label`) and takes only its
 * colour from `workflow_state`. Its stored-status form went with the
 * Evaluation screen (IR-274), and with it the test that pinned it.
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("shows the API's label for a workflow state, not a client-side one", () => {
    renderScreen(<StatusBadge state="final_review" label="Final review" />);

    expect(screen.getByText("Final review")).toBeInTheDocument();
  });
});
