import { describe, expect, it } from "vitest";

import { centredView, clampView, cropFromView, panView, zoomView } from "./photoCrop";

// A 1000 × 500 photo shown in a 200 px square: at zoom 1 its short side fills
// the square, so one screen pixel is 2.5 image pixels.
const wide = { width: 1000, height: 500 };
const STAGE = 200;

describe("cropFromView", () => {
  it("takes the centred square at zoom 1", () => {
    const view = centredView(wide, STAGE, 1);
    expect(cropFromView(wide, STAGE, view)).toEqual({ x: 250, y: 0, size: 500 });
  });

  it("takes a smaller centred square when zoomed in", () => {
    const view = centredView(wide, STAGE, 2);
    expect(cropFromView(wide, STAGE, view)).toEqual({ x: 375, y: 125, size: 250 });
  });

  it("follows the image when it is dragged to its left edge", () => {
    expect(cropFromView(wide, STAGE, { zoom: 1, offsetX: 0, offsetY: 0 })).toEqual({ x: 0, y: 0, size: 500 });
  });

  it("never reaches outside the image, however far it was dragged", () => {
    expect(cropFromView(wide, STAGE, { zoom: 1, offsetX: 80, offsetY: -40 })).toEqual({ x: 0, y: 0, size: 500 });
    expect(cropFromView(wide, STAGE, { zoom: 1, offsetX: -9999, offsetY: 0 })).toEqual({ x: 500, y: 0, size: 500 });
  });
});

describe("clampView", () => {
  it("keeps the square covered, so the circle never shows an empty corner", () => {
    expect(clampView(wide, STAGE, { zoom: 1, offsetX: 50, offsetY: 30 })).toEqual({ zoom: 1, offsetX: 0, offsetY: 0 });
    expect(clampView(wide, STAGE, { zoom: 1, offsetX: -500, offsetY: 0 })).toEqual({ zoom: 1, offsetX: -200, offsetY: 0 });
  });
});

describe("panView", () => {
  it("moves the image by the given screen pixels and stops at its edge", () => {
    const start = centredView(wide, STAGE, 1); // offsetX -100
    expect(panView(wide, STAGE, start, 40, 0).offsetX).toBe(-60);
    expect(panView(wide, STAGE, start, 400, 0).offsetX).toBe(0);
  });
});

describe("zoomView", () => {
  it("zooms about the middle of the circle", () => {
    const zoomed = zoomView(wide, STAGE, centredView(wide, STAGE, 1), 2);
    expect(cropFromView(wide, STAGE, zoomed)).toEqual({ x: 375, y: 125, size: 250 });
  });
});
