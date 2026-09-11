/**
 * The one rendering helper (IR-210).
 *
 * Screens go through this rather than calling `render` directly, so that the
 * providers a screen needs live in one place. Today that is only the router --
 * auth and UI state are Zustand stores, which need no provider -- but the point
 * is that when a second provider appears it is added here and every existing
 * test picks it up.
 */
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import { MemoryRouter, parsePath } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";

export interface RenderScreenOptions extends Omit<RenderOptions, "wrapper"> {
  /**
   * The entry the router starts on. `LoginPage` reads `?reason=session_expired`
   * off the query string, so a test that wants that banner asks for it here
   * rather than reaching into the component.
   */
  route?: string;
  /**
   * Router state on that entry — what a `<Navigate state={...}>` would have
   * left behind. The route guard hands the login screen the page the visitor
   * asked for this way (IR-236), so a test of that hand-off has to be able to
   * set it up the same way the guard does, rather than by stubbing a hook.
   */
  state?: unknown;
}

export function renderScreen(
  ui: ReactElement,
  { route = "/", state, ...options }: RenderScreenOptions = {},
): RenderResult {
  function Providers({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[{ ...parsePath(route), state }]}>{children}</MemoryRouter>
    );
  }

  return render(ui, { wrapper: Providers, ...options });
}

export * from "@testing-library/react";
export { default as userEvent } from "@testing-library/user-event";
