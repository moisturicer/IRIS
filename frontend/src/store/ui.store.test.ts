/**
 * Paper mode's temporary rail (IR-569): collapsed while reading, without
 * touching the reader's saved preference.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { selectSidebarCollapsed, useUIStore } from "./ui.store";

const KEY = "iris_sidebar_collapsed";

function collapsed() {
  return selectSidebarCollapsed(useUIStore.getState());
}

describe("the reading rail", () => {
  beforeEach(() => {
    localStorage.removeItem(KEY);
    useUIStore.setState({ sidebarCollapsed: false, sidebarOpen: false, readingRail: null });
  });

  it("collapses the rail and closes the phone drawer, saving nothing", () => {
    useUIStore.setState({ sidebarOpen: true });

    useUIStore.getState().enterReadingRail();

    expect(collapsed()).toBe(true);
    expect(useUIStore.getState().sidebarOpen).toBe(false);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("restores the saved preference on leaving", () => {
    useUIStore.getState().enterReadingRail();
    useUIStore.getState().leaveReadingRail();

    expect(collapsed()).toBe(false);
  });

  it("lets the reader expand it while reading, still saving nothing", () => {
    useUIStore.getState().enterReadingRail();
    useUIStore.getState().toggleSidebarCollapsed();

    expect(collapsed()).toBe(false);
    expect(localStorage.getItem(KEY)).toBeNull();

    useUIStore.getState().leaveReadingRail();
    expect(collapsed()).toBe(false);
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("keeps a saved collapsed preference collapsed after leaving", () => {
    useUIStore.setState({ sidebarCollapsed: true });
    useUIStore.getState().enterReadingRail();
    useUIStore.getState().toggleSidebarCollapsed();
    useUIStore.getState().leaveReadingRail();

    expect(collapsed()).toBe(true);
  });

  it("still saves a toggle made outside reading", () => {
    useUIStore.getState().toggleSidebarCollapsed();

    expect(collapsed()).toBe(true);
    expect(localStorage.getItem(KEY)).toBe("1");
  });
});
