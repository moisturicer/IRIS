/**
 * The arithmetic behind Settings' circular photo crop (IR-699).
 *
 * The crop tool shows the photo inside a square "stage" with a circle drawn
 * over it. The person zooms and drags; what the server needs back is the
 * square they framed, in pixels of the original file: `crop_x`, `crop_y` and
 * `crop_size` (IR-695 contract). Kept apart from the component so the numbers
 * can be checked against worked examples without a DOM.
 *
 * A view is the photo's zoom (1 = its short side just fills the stage) and the
 * position of its top-left corner relative to the stage, in screen pixels.
 * Offsets are always zero or negative: the photo always covers the stage.
 */

export interface ImageSize { width: number; height: number; }
export interface CropView { zoom: number; offsetX: number; offsetY: number; }
export interface CropRect { x: number; y: number; size: number; }

export const MIN_ZOOM = 1;
export const MAX_ZOOM = 3;

/** `zoom` kept within what the slider offers. */
export function clampZoom(zoom: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
}

/** Screen pixels per photo pixel at `zoom`. */
export function scaleFor(image: ImageSize, stage: number, zoom: number): number {
  return (stage / Math.min(image.width, image.height)) * zoom;
}

/** Keep `view` inside the photo, so no part of the stage is ever left empty. */
export function clampView(image: ImageSize, stage: number, view: CropView): CropView {
  const zoom = clampZoom(view.zoom);
  const scale = scaleFor(image, stage, zoom);
  const minX = stage - image.width * scale;
  const minY = stage - image.height * scale;
  return {
    zoom,
    offsetX: Math.min(0, Math.max(minX, view.offsetX)),
    offsetY: Math.min(0, Math.max(minY, view.offsetY)),
  };
}

/** The photo centred in the stage at `zoom`. */
export function centredView(image: ImageSize, stage: number, zoom: number): CropView {
  const scale = scaleFor(image, stage, zoom);
  return clampView(image, stage, {
    zoom,
    offsetX: (stage - image.width * scale) / 2,
    offsetY: (stage - image.height * scale) / 2,
  });
}

/** Move the photo by `dx`, `dy` screen pixels, stopping at its edges. */
export function panView(image: ImageSize, stage: number, view: CropView, dx: number, dy: number): CropView {
  return clampView(image, stage, { ...view, offsetX: view.offsetX + dx, offsetY: view.offsetY + dy });
}

/**
 * Change the zoom while keeping the stage's centre on the same point of the
 * photo, so zooming feels like moving closer rather than sliding sideways.
 */
export function zoomView(image: ImageSize, stage: number, view: CropView, zoom: number): CropView {
  const from = scaleFor(image, stage, view.zoom);
  const to = scaleFor(image, stage, clampZoom(zoom));
  const centreX = (stage / 2 - view.offsetX) / from;
  const centreY = (stage / 2 - view.offsetY) / from;
  return clampView(image, stage, {
    zoom,
    offsetX: stage / 2 - centreX * to,
    offsetY: stage / 2 - centreY * to,
  });
}

/** The square the person framed, in whole pixels of the original photo. */
export function cropFromView(image: ImageSize, stage: number, view: CropView): CropRect {
  const v = clampView(image, stage, view);
  const scale = scaleFor(image, stage, v.zoom);
  const size = Math.min(Math.round(stage / scale), image.width, image.height);
  const x = Math.min(Math.max(0, Math.round(-v.offsetX / scale)), image.width - size);
  const y = Math.min(Math.max(0, Math.round(-v.offsetY / scale)), image.height - size);
  return { x, y, size };
}
