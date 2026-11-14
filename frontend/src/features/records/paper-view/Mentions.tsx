/**
 * @mentions in the review discussion (ADR-032 §7 Conveniences, IR-877).
 *
 * A person is **picked beside the text**, never typed into it: the server
 * offers only people who may read this review, so a mention never grants
 * access. The list is fetched when the picker is first opened. Whoever is
 * picked is notified once; a reviewer's draft notifies them when the review
 * is finished.
 */
import { useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui";
import type { MentionedPerson } from "@/types/records";

type Loaded = { state: "idle" | "loading" | "failed" } | { state: "ready"; people: MentionedPerson[] };

/** Is `p` a person as we read one (F1)? */
function isPerson(p: unknown): p is MentionedPerson {
  return !!p && typeof p === "object" && typeof (p as MentionedPerson).id === "number"
    && typeof (p as MentionedPerson).name === "string";
}

/** The people in a value, dropping anything that isn't one (F1). */
export function peopleIn(value: unknown): MentionedPerson[] {
  return Array.isArray(value) ? value.filter(isPerson) : [];
}

export function MentionPicker({ recordId, value, onChange }: {
  recordId: number;
  value: MentionedPerson[];
  onChange: (people: MentionedPerson[]) => void;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<Loaded>({ state: "idle" });

  const load = async () => {
    setLoaded({ state: "loading" });
    try {
      const { data } = await recordsApi.reviewMentionable(recordId);
      const results = (data as { results?: unknown } | null)?.results;
      setLoaded(Array.isArray(results) ? { state: "ready", people: peopleIn(results) } : { state: "failed" });
    } catch {
      setLoaded({ state: "failed" });
    }
  };

  const toggle = () => {
    if (!open && loaded.state !== "ready") void load();
    setOpen(!open);
  };

  const picked = new Set(value.map((p) => p.id));
  const flip = (person: MentionedPerson) =>
    onChange(picked.has(person.id) ? value.filter((p) => p.id !== person.id) : [...value, person]);

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Button type="button" size="sm" variant="ghost" onClick={toggle}
          aria-expanded={open} aria-controls={open ? listId : undefined}>
          <i className="fas fa-at mr-1.5" aria-hidden />Mention someone
        </Button>
        {value.length > 0 && (
          <ul aria-label="Mentioning" className="flex flex-wrap gap-1.5">
            {value.map((p) => (
              <li key={p.id} className="inline-flex items-center gap-1 rounded-lg bg-stone-100 pl-2 text-small text-stone-800">
                @{p.name}
                <Button type="button" size="sm" variant="ghost" onClick={() => flip(p)}
                  aria-label={`Stop mentioning ${p.name}`}>
                  <i className="fas fa-xmark" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {open && (
        <div id={listId} className="rounded-lg border border-stone-200 bg-white p-2 space-y-1.5">
          {loaded.state === "loading" && <p className="text-2xs text-stone-600">Loading who you can mention…</p>}
          {loaded.state === "failed" && <p className="text-2xs text-stone-600">The people you can mention couldn&rsquo;t be loaded.</p>}
          {loaded.state === "ready" && loaded.people.length === 0 && (
            <p className="text-2xs text-stone-600">Nobody else takes part in this review yet.</p>
          )}
          {loaded.state === "ready" && loaded.people.length > 0 && (
            <fieldset>
              <legend className="text-2xs text-stone-600">
                Only people who take part in this review. Each is notified once.
              </legend>
              <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                {loaded.people.map((p) => (
                  <li key={p.id}>
                    <label className="inline-flex items-center gap-1.5 text-small text-stone-800 min-h-11 reading-split:min-h-9">
                      <input type="checkbox" checked={picked.has(p.id)} onChange={() => flip(p)}
                        className="accent-brand" />
                      {p.name}
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )}
        </div>
      )}
    </div>
  );
}

/** Whom a comment mentions, under its text. */
export function MentionedPeople({ people }: { people: unknown }) {
  const named = peopleIn(people);
  if (named.length === 0) return null;
  return (
    <p className="text-2xs text-stone-600">
      Mentioned: {named.map((p) => p.name).join(", ")}
    </p>
  );
}
