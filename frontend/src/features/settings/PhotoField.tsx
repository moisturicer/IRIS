import { useEffect, useId, useState } from "react";

import { profileApi } from "@/api/profile";
import { errorDetail } from "@/lib/errorDetail";
import type { User } from "@/types/auth";

import { PhotoCropDialog } from "./PhotoCropDialog";
import { secondaryButtonClass } from "./settingsParts";

export const PHOTO_MAX_BYTES = 2 * 1024 * 1024;
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
  const shown = useAuthedImage(user.photo_url ?? null);

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
      {shown ? (
        <img
          src={shown}
          alt="Your profile photo"
          className="w-20 h-20 rounded-full object-cover border border-stone-200"
        />
      ) : (
        <span
          aria-hidden
          className="w-20 h-20 rounded-full grid place-items-center bg-brand-50 text-brand text-[22px] font-bold"
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
            className={`${secondaryButtonClass} cursor-pointer peer-focus-visible:ring-2 peer-focus-visible:ring-brand/40`}
          >
            {user.photo_url ? "Change photo" : "Upload photo"}
          </label>
          {user.photo_url && (
            <button type="button" onClick={remove} disabled={removing} className={secondaryButtonClass}>
              {removing ? "Removing..." : "Remove photo"}
            </button>
          )}
        </div>
        <span className="text-[12px] text-stone-500">JPEG or PNG, up to 2 MB. Saved as soon as you crop it.</span>
        {error && <span role="alert" className="text-[12px] text-red-700">{error}</span>}
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
    let live = true;
    profileApi.photo(photoUrl)
      .then(({ data }) => {
        if (!live) return;
        objectUrl = URL.createObjectURL(data);
        setSrc(objectUrl);
      })
      .catch(() => { if (live) setSrc(null); });
    return () => {
      live = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photoUrl]);
  return src;
}
