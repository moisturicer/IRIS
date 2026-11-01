/**
 * Access denied (IR-745). The gate runs in the browser and writes nothing,
 * so the screen no longer claims the attempt was logged.
 */
import { describe, expect, it } from "vitest";

import { ROLES } from "@/lib/constants";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import { ForbiddenScreen } from "./ForbiddenScreen";

describe("ForbiddenScreen", () => {
  it("names both roles and the way out, and claims no audit entry", async () => {
    const { container } = renderScreen(
      <ForbiddenScreen authenticatedRole={ROLES.STUDENT} requiredRoles={[ROLES.RDCO, ROLES.KTTO]} />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Access denied" })).toBeInTheDocument();
    expect(screen.getByText("Student")).toBeInTheDocument();
    expect(screen.getByText("RDCO or KTTO")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Discover" })).toHaveAttribute("href", "/");
    expect(screen.queryByText(/audit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dashboard/i)).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });
});
