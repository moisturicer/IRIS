import { useEffect, useId, useState } from "react";

import { profileApi } from "@/api/profile";
import { FieldError } from "@/components/ui/FieldError";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { errorDetail } from "@/lib/errorDetail";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

import { PhotoCropDialog } from "./PhotoCropDialog";

const PHOTO_MAX_BYTES = 2 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png"];

/**
 * The profile photo in Settings (IR-699): shown as a circle, or the person's
 * initials when there is none. Choosing a file opens the crop dialog; the
 * photo saves when the crop is confirmed, and Remove photo takes it off.
 */
export function PhotoField({ user, onSaved }: { user: User; onSaved: (u: User) => void }) {
  const inputId = useId();
  const [chosen, setChosen] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const photoSrc = useAuthedImage(user.photo_url ?? null);

  const choose = (file: File | undefined) => {
    setError(null);
    if (!file) return;
    // The server checks the file's content too (IR-695); this only saves a
    // round trip for the obvious mistakes.
    if (!PHOTO_TYPES.includes(file.type)) return setError("Upload a JPEG or PNG image.");
    if (file.size > PHOTO_MAX_BYTES) return setError("The photo must be 2 MB or smaller.");
    setChosen(file);
  };

  const remove = async () => {
    setError(null);
    setRemoving(true);
    try {
      await profileApi.removePhoto();
      onSaved({ ...user, photo_url: null });
    } catch (err) {
      setError(errorDetail(err, "Could not remove your photo. Please try again."));
    } finally {
      setRemoving(false);
    }
  };

  const initials = `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toUpperCase();

  return (
    <div className="flex items-center gap-4 flex-wrap">
      {photoSrc ? (
        <img
          src={photoSrc}
          alt="Your profile photo"
          className="w-20 h-20 rounded-full object-cover ring-1 ring-stone-200"
        />
      ) : (
        <span
          aria-hidden
          className="w-20 h-20 rounded-full grid place-items-center bg-brand-50 text-brand text-title font-semibold"
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
            {user.photo_url ? "Change photo" : "Upload photo"}
          </label>
          {user.photo_url && (
            <button type="button" onClick={remove} disabled={removing} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              {removing ? "Removing..." : "Remove photo"}
            </button>
          )}
        </div>
        <p className="text-small text-stone-600">JPEG or PNG, up to 2 MB. Saved as soon as you crop it.</p>
        {error && <div role="alert"><FieldError>{error}</FieldError></div>}
      </div>

      {chosen && (
        <PhotoCropDialog
          file={chosen}
          onClose={() => setChosen(null)}
          onUploaded={(photoUrl) => { onSaved({ ...user, photo_url: photoUrl }); setChosen(null); }}
        />
      )}
    </div>
  );
}

/**
 * An object URL for a photo served behind auth, or `null` while it loads,
 * when there is none, or when it cannot be fetched.
 */
function useAuthedImage(photoUrl: string | null): string | null {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    setSrc(null);
    if (!photoUrl) return;
    let objectUrl: string | null = null;
    let current = true;
    profileApi.photo(photoUrl)
      .then(({ data }) => {
        if (!current) return;
        objectUrl = URL.createObjectURL(data);
        setSrc(objectUrl);
      })
      .catch(() => { if (current) setSrc(null); });
    return () => {
      current = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photoUrl]);
  return src;
}
