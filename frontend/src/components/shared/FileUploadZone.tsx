/**
 * Drag-and-drop + click-to-browse file upload zone.
 * TODO: add preview thumbnails for image files.
 */
import { useCallback, useRef, useState, type DragEvent } from "react";

interface FileUploadZoneProps {
  onFiles:    (files: File[]) => void;
  accept?:    string;          // e.g. ".pdf,.docx"
  multiple?:  boolean;
  disabled?:  boolean;
  hint?:      string;          // e.g. "PDF, DOCX up to 50 MB"
  /** The zone's accessible name, when a screen shows more than one zone. */
  label?:     string;
}

export function FileUploadZone({
  onFiles,
  accept,
  multiple = false,
  disabled,
  hint,
  label,
}: FileUploadZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      if (disabled) return;
      const files = Array.from(e.dataTransfer.files);
      if (files.length) onFiles(files);
    },
    [disabled, onFiles]
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length) onFiles(files);
    // Reset so the same file can be re-selected
    e.target.value = "";
  };

  return (
    <div
      role="button"
      aria-label={label}
      tabIndex={disabled ? -1 : 0}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed
        px-6 py-10 cursor-pointer transition-colors select-none
        ${dragging ? "border-brand bg-brand-50" : "border-stone-300 hover:border-stone-400 bg-stone-50"}
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
      `}
    >
      <i className="fa fa-cloud-upload-alt text-3xl text-stone-500" aria-hidden />
      <p className="text-[14px] text-stone-600 font-medium">
        Drag and drop here, or <span className="text-brand">browse</span>
      </p>
      {hint && <p className="text-[13px] text-stone-500">{hint}</p>}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        // The attribute, not Tailwind's class: the zone is the control, and the
        // input must stay out of the accessibility tree wherever styles are absent.
        hidden
        onChange={handleChange}
        disabled={disabled}
      />
    </div>
  );
}
