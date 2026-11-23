import { useEffect, useId, useState } from "react";

import { FieldError } from "@/components/ui/FieldError";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import type { CropRect, ImageSize } from "@/lib/photoCrop";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

import { PhotoCropDialog } from "./PhotoCropDialog";
import { useAuthedImage } from "./useAuthedImage";

const PHOTO_MAX_BYTES = 2 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png"];
const AVATAR = 80;

/**
 * A photo change not yet saved: a newly framed photo, or taking the photo off.
 * The Edit profile page holds it and sends it with Save, so Cancel drops it.
 */
export type PhotoChange =
  | { kind: "upload"; file: File; crop: CropRect; image: ImageSize }
  | { kind: "remove" };

/**
 * The profile photo on Edit profile (IR-699): shown as a circle, or the
 * person's initials when there is none. Choosing a file opens the crop dialog;
 * the framed photo, or Remove photo, is shown here at once but saved only
 * with the page's Save.
 */
export function PhotoField({
  user, change, onChange,
}: { user: User; change: PhotoChange | null; onChange: (next: PhotoChange | null) => void }) {
  const inputId = useId();
  const [chosen, setChosen] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const savedSrc = useAuthedImage(user.photo_url ?? null);

  const choose = (file: File | undefined) => {
    setError(null);
    if (!file) return;
    // The server checks the file's content too (IR-695); this only saves a
    // round trip for the obvious mistakes.
    if (!PHOTO_TYPES.includes(file.type)) return setError("Upload a JPEG or PNG image.");
    if (file.size > PHOTO_MAX_BYTES) return setError("The photo must be 2 MB or smaller.");
    setChosen(file);
  };

  // Removing a photo framed but not saved just drops it, back to the saved one;
  // removing the saved photo is a change of its own.
  const remove = () => {
    setError(null);
    onChange(change?.kind === "upload" || !user.photo_url ? null : { kind: "remove" });
  };

  const showsPhoto = change?.kind === "upload" || (!change && !!user.photo_url);
  const initials = `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase();

  return (
    <div className="flex items-center gap-4 flex-wrap">
      {change?.kind === "upload" ? (
        <FramedPreview change={change} />
      ) : !change && savedSrc ? (
        <img
          src={savedSrc}
          alt="Your profile photo"
          className="w-20 h-20 rounded-full object-cover ring-1 ring-stone-200"
        />
      ) : (
        <span
          aria-hidden
          className="w-20 h-20 rounded-full grid place-items-center bg-brand text-white text-title font-semibold"
        >
          {initials}
        </span>
      )}

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          {/* A real file input, visually replaced by its label, so it keeps
              its keyboard and screen-reader behaviour. */}
          <input
            id={inputId}
            type="file"
            accept={PHOTO_TYPES.join(",")}
            className="peer sr-only"
            onChange={(e) => { choose(e.target.files?.[0]); e.target.value = ""; }}
          />
          <label
            htmlFor={inputId}
            className={cn(
              PILL_SECONDARY, "cursor-pointer",
              "peer-focus-visible:ring-2 peer-focus-visible:ring-brand peer-focus-visible:ring-offset-2",
            )}
          >
            {showsPhoto ? "Change photo" : "Upload photo"}
          </label>
          {showsPhoto && (
            <button type="button" onClick={remove} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              Remove photo
            </button>
          )}
        </div>
        <p className="text-small text-stone-600">JPEG or PNG, up to 2 MB. Saved when you press Save.</p>
        {error && <div role="alert"><FieldError>{error}</FieldError></div>}
      </div>

      {chosen && (
        <PhotoCropDialog
          file={chosen}
          onClose={() => setChosen(null)}
          onCropped={(crop, image) => {
            onChange({ kind: "upload", file: chosen, crop, image });
            setChosen(null);
          }}
        />
      )}
    </div>
  );
}

/** The framed photo, before it is saved: the same square the server will cut. */
function FramedPreview({ change }: { change: Extract<PhotoChange, { kind: "upload" }> }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(change.file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [change.file]);

  const scale = AVATAR / change.crop.size;
  return (
    <span className="relative w-20 h-20 rounded-full overflow-hidden ring-1 ring-stone-200 shrink-0">
      {src && (
        <img
          src={src}
          alt="Your profile photo"
          draggable={false}
          className="absolute left-0 top-0 max-w-none"
          style={{
            width: change.image.width * scale,
            height: change.image.height * scale,
            transform: `translate(${-change.crop.x * scale}px, ${-change.crop.y * scale}px)`,
          }}
        />
      )}
    </span>
  );
}
