import { useEffect, useRef, useState } from "react";

import { profileApi } from "@/api/profile";
import { Modal } from "@/components/ui/Modal";
import { fieldError, errorDetail } from "@/lib/errorDetail";
import {
  centredView, cropFromView, MAX_ZOOM, MIN_ZOOM, panView, zoomView,
  type CropView, type ImageSize,
} from "@/lib/photoCrop";

import { primaryButtonClass, secondaryButtonClass } from "./settingsParts";

/** The square the photo is framed in, in screen pixels. */
const STAGE = 256;
/** How far one arrow-key press moves the framing, in screen pixels. */
const STEP = 10;

/**
 * Frame a chosen photo inside a circle, then upload it (IR-699).
 *
 * The circle is the preview: what shows inside it is what the Profile will
 * show. The person drags the photo or moves it with the arrow keys, and zooms
 * with the slider. What is uploaded is the original file plus the framed
 * square in its own pixels; the server does the cutting (IR-695).
 */
export function PhotoCropDialog({
  file, onClose, onUploaded,
}: { file: File; onClose: () => void; onUploaded: (photoUrl: string) => void }) {
  const [src, setSrc] = useState<string | null>(null);
  const [image, setImage] = useState<ImageSize | null>(null);
  const [view, setView] = useState<CropView>({ zoom: 1, offsetX: 0, offsetY: 0 });
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const scale = image ? (STAGE / Math.min(image.width, image.height)) * view.zoom : 1;

  const pan = (dx: number, dy: number) => {
    if (image) setView((v) => panView(image, STAGE, v, dx, dy));
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    // Arrows move the framing, so the photo moves the other way.
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [STEP, 0], ArrowRight: [-STEP, 0], ArrowUp: [0, STEP], ArrowDown: [0, -STEP],
    };
    const move = moves[e.key];
    if (!move) return;
    e.preventDefault();
    pan(...move);
  };

  const upload = async () => {
    if (!image) return;
    setError(null);
    setUploading(true);
    try {
      const { data } = await profileApi.uploadPhoto(file, cropFromView(image, STAGE, view));
      onUploaded(data.photo_url);
    } catch (err) {
      setError(
        fieldError(err, "photo") ??
          fieldError(err, "crop_size") ??
          errorDetail(err, "Could not upload your photo. Please try again."),
      );
      setUploading(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Crop your photo"
      size="max-w-sm"
      footer={
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={secondaryButtonClass}>Cancel</button>
          <button type="button" onClick={upload} disabled={!image || uploading} className={primaryButtonClass}>
            {uploading ? "Uploading..." : "Use photo"}
          </button>
        </div>
      }
    >
      <div className="flex flex-col items-center gap-4">
        <div
          role="group"
          aria-label="Photo framing. Drag or use the arrow keys to move it."
          tabIndex={0}
          onKeyDown={onKeyDown}
          onPointerDown={(e) => {
            drag.current = { x: e.clientX, y: e.clientY };
            e.currentTarget.setPointerCapture?.(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (!drag.current) return;
            pan(e.clientX - drag.current.x, e.clientY - drag.current.y);
            drag.current = { x: e.clientX, y: e.clientY };
          }}
          onPointerUp={() => { drag.current = null; }}
          onPointerCancel={() => { drag.current = null; }}
          className="relative overflow-hidden rounded-lg bg-stone-900 cursor-grab active:cursor-grabbing
            touch-none select-none focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
          style={{ width: STAGE, height: STAGE }}
        >
          {src && (
            <img
              src={src}
              alt="Your photo, as it will appear"
              draggable={false}
              onLoad={(e) => {
                const loaded = { width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight };
                if (!loaded.width || !loaded.height) return;
                setImage(loaded);
                setView(centredView(loaded, STAGE, MIN_ZOOM));
              }}
              className="absolute left-0 top-0 max-w-none pointer-events-none"
              style={image ? {
                width: image.width * scale,
                height: image.height * scale,
                transform: `translate(${view.offsetX}px, ${view.offsetY}px)`,
              } : { opacity: 0 }}
            />
          )}
          {/* Everything outside the circle is dimmed: the circle is the preview. */}
          <span
            aria-hidden
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{ boxShadow: "0 0 0 9999px rgba(28, 25, 23, 0.6)" }}
          />
        </div>

        <label className="w-full flex items-center gap-3 text-[13px] text-stone-600">
          <i className="fas fa-magnifying-glass-minus text-[12px]" aria-hidden />
          <span className="sr-only">Zoom</span>
          <input
            type="range"
            min={MIN_ZOOM}
            max={MAX_ZOOM}
            step={0.01}
            value={view.zoom}
            disabled={!image}
            onChange={(e) => { if (image) setView((v) => zoomView(image, STAGE, v, Number(e.target.value))); }}
            className="flex-1 accent-brand"
          />
          <i className="fas fa-magnifying-glass-plus text-[12px]" aria-hidden />
        </label>

        {error && <p role="alert" className="text-[13px] text-red-700 self-start">{error}</p>}
      </div>
    </Modal>
  );
}
