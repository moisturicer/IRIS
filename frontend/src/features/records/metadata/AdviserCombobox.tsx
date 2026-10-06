/**
 * Choose an adviser by typing part of their name (IR-408; spec §4.4 step 2).
 *
 * A native `<select>` lists every adviser at CIT-U in one column with no way
 * to search, so this is the ARIA 1.2 combobox pattern instead: a text input
 * owning a listbox, arrow keys to move, Enter to choose, Escape to close.
 *
 * **The signed-in user is listed but cannot be chosen** when they are an
 * adviser themselves (ADR-032 §1: nobody reviews their own submission). The
 * option says why, rather than silently leaving them out, so a faculty author
 * looking for their own name learns the rule instead of thinking the list is
 * broken.
 */
import { useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { fieldClasses } from "@/components/ui/fieldClasses";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

import { personName } from "./personName";

interface AdviserComboboxProps {
  id:          string;
  advisers:    User[];
  value:       number | undefined;
  onChange:    (id: number | undefined) => void;
  onBlur?:     () => void;
  selfId:      number | null;
  loading?:    boolean;
  invalid?:    boolean;
  describedBy?: string;
}

export function AdviserCombobox({
  id,
  advisers,
  value,
  onChange,
  onBlur,
  selfId,
  loading = false,
  invalid = false,
  describedBy,
}: AdviserComboboxProps) {
  const listId = useId();
  const optionId = (adviserId: number) => `${listId}-option-${adviserId}`;
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = advisers.find((a) => a.id === value);
  // null while the user is not typing, so the input shows the chosen name.
  const [query, setQuery] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<number | null>(null);

  const shown = query ?? (selected ? personName(selected) : "");

  const options = useMemo(() => {
    const needle = (query ?? "").trim().toLowerCase();
    if (!needle) return advisers;
    return advisers.filter((a) =>
      `${personName(a)} ${a.email} ${a.department_name}`.toLowerCase().includes(needle),
    );
  }, [advisers, query]);

  const choosable = options.filter((a) => a.id !== selfId);

  function choose(adviser: User) {
    if (adviser.id === selfId) return;
    onChange(adviser.id);
    setQuery(null);
    setOpen(false);
    setActive(null);
  }

  function move(step: 1 | -1) {
    if (choosable.length === 0) return;
    setOpen(true);
    const at = choosable.findIndex((a) => a.id === active);
    const next = at === -1 ? (step === 1 ? 0 : choosable.length - 1) : (at + step + choosable.length) % choosable.length;
    setActive(choosable[next].id);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      move(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      move(-1);
    } else if (e.key === "Enter" && open) {
      // Enter chooses; it must not submit the step behind the list.
      e.preventDefault();
      const adviser = choosable.find((a) => a.id === active);
      if (adviser) choose(adviser);
    } else if (e.key === "Escape" && open) {
      // Close the list only. Without this the same key closes the dialog too.
      e.preventDefault();
      e.stopPropagation();
      setOpen(false);
      setActive(null);
      setQuery(null);
    }
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        id={id}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active != null ? optionId(active) : undefined}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        disabled={loading}
        placeholder={loading ? "Loading advisers…" : "Type a name to search"}
        value={shown}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(null);
          // Typing over a chosen name un-chooses it, so the form never holds an
          // adviser the input no longer shows.
          if (value != null) onChange(undefined);
        }}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onBlur={() => {
          setOpen(false);
          setActive(null);
          setQuery(null);
          onBlur?.();
        }}
        onKeyDown={handleKeyDown}
        className={fieldClasses(invalid)}
      />

      {/* Rendered while closed too, so aria-controls always names something. */}
      <ul
        id={listId}
        role="listbox"
        aria-label="Advisers"
        hidden={!open || options.length === 0}
        className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
      >
        {options.map((adviser) => {
          const isSelf = adviser.id === selfId;
          return (
            <li
              key={adviser.id}
              id={optionId(adviser.id)}
              role="option"
              aria-selected={adviser.id === value}
              aria-disabled={isSelf || undefined}
              // mousedown, not click: a click would blur the input first and close the list.
              onMouseDown={(e) => {
                e.preventDefault();
                choose(adviser);
              }}
              className={cn(
                "px-3 py-2 text-sm",
                isSelf ? "cursor-not-allowed text-stone-500" : "cursor-pointer text-stone-800",
                adviser.id === active && "bg-stone-100",
                adviser.id === value && "font-semibold",
              )}
            >
              {personName(adviser)}
              {isSelf ? (
                <span className="block text-small">That's you. You can't be your own adviser.</span>
              ) : (
                adviser.department_name && (
                  <span className="block text-small text-stone-600">{adviser.department_name}</span>
                )
              )}
            </li>
          );
        })}
      </ul>
      {open && !loading && options.length === 0 && (
        <p className="absolute z-10 mt-1 w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-small text-stone-600 shadow-lg">
          {advisers.length === 0 ? "No advisers are registered yet. Contact RDCO." : "No adviser matches that name."}
        </p>
      )}
    </div>
  );
}
