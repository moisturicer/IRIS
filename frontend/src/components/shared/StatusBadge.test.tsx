/**
 * The workflow state badge (IR-259).
 *
 * It shows the label the API wrote (`workflow_state_label`) and takes only its
 * colour from `workflow_state`. The `status` form survives for one caller --
 * the Evaluation screen, which IR-268 moves over -- and IR-274 deletes it.
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("shows the API's label for a workflow state, not a client-side one", () => {
    renderScreen(<StatusBadge state="final_review" label="Final review" />);

    expect(screen.getByText("Final review")).toBeInTheDocument();
  });

  it("still labels a raw pipeline status for the Evaluation screen until IR-268", () => {
    renderScreen(<StatusBadge status="published" />);

    expect(screen.getByText("Published")).toBeInTheDocument();
  });
});
