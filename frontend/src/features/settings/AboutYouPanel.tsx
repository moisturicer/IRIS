import { useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  BIO_MAX_LENGTH, INTEREST_MAX_LENGTH, MAX_INTERESTS, profileApi, profilePath,
} from "@/api/profile";
import { FieldError } from "@/components/ui/FieldError";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { fieldClasses, LOAD_ERROR } from "@/components/ui/fieldClasses";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { ORCID_EXAMPLE, orcidProblem } from "@/lib/orcid";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

import { PhotoField } from "./PhotoField";
import { Panel } from "./settingsParts";

/**
 * The optional Profile fields (IR-699): photo, bio, research interests and
 * ORCID iD, as the IR-694 spec decided and IR-695's contract carries them.
 *
 * Every one is optional, and leaving one empty is how a person keeps it off
 * their Profile: there is no privacy switch. The photo saves as soon as it is
 * cropped; the text fields save together with Save.
 */

const HINT = "text-small text-stone-600 mt-1";

const sameInterest = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase();

export function AboutYouPanel({ user, onSaved }: { user: User; onSaved: (u: User) => void }) {
  const [bio, setBio] = useState(user.bio ?? "");
  const [interests, setInterests] = useState<string[]>(user.research_interests ?? []);
  const [orcid, setOrcid] = useState(user.orcid ?? "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bioId = useId();
  const bioCountId = useId();
  const orcidId = useId();
  const orcidHintId = useId();

  const orcidIssue = orcidProblem(orcid);

  const dirty = useMemo(() => {
    const stored = user.research_interests ?? [];
    return (
      bio !== (user.bio ?? "") ||
      orcid.trim() !== (user.orcid ?? "") ||
      interests.length !== stored.length ||
      interests.some((tag, i) => tag !== stored[i])
    );
  }, [bio, orcid, interests, user]);

  const resetTo = (u: User) => {
    setBio(u.bio ?? "");
    setInterests(u.research_interests ?? []);
    setOrcid(u.orcid ?? "");
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (orcidIssue) return;
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      const { data } = await profileApi.updateFields({
        bio,
        research_interests: interests,
        orcid: orcid.trim() || null,
      });
      onSaved(data);
      // The server may have matched an interest to an existing tag's casing.
      resetTo(data);
      setSaved(true);
    } catch (err) {
      setError(
        fieldError(err, "bio", "research_interests", "orcid") ??
          errorDetail(err, "Could not save your profile. Please try again."),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save}>
      <Panel
        title="About you"
        caption="Optional. What you add here appears on your Profile, which anyone signed in to IRIS can open. Leave a field empty to keep it off."
      >
        <PhotoField user={user} onSaved={onSaved} />

        <div className="mt-6 space-y-1">
          <FieldLabel htmlFor={bioId} label="Bio" />
          <textarea
            id={bioId}
            className={cn(fieldClasses(false), "min-h-24 resize-y")}
            value={bio}
            maxLength={BIO_MAX_LENGTH}
            onChange={(e) => setBio(e.target.value)}
            aria-describedby={bioCountId}
          />
          <p id={bioCountId} className={HINT}>
            {bio.length} / {BIO_MAX_LENGTH} characters
          </p>
        </div>

        <InterestsField interests={interests} onChange={setInterests} />

        <div className="mt-6 max-w-sm space-y-1">
          <FieldLabel htmlFor={orcidId} label="ORCID iD" />
          <input
            id={orcidId}
            className={cn(fieldClasses(!!orcidIssue), "font-mono")}
            value={orcid}
            onChange={(e) => setOrcid(e.target.value)}
            placeholder={ORCID_EXAMPLE}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={orcidIssue ? true : undefined}
            aria-describedby={orcidHintId}
          />
          {orcidIssue ? (
            <FieldError id={orcidHintId}>{orcidIssue}</FieldError>
          ) : (
            <p id={orcidHintId} className={HINT}>
              Your own iD from orcid.org. IRIS shows it as you enter it and doesn't verify it with ORCID.
            </p>
          )}
        </div>

        {error && <p role="alert" className={cn(LOAD_ERROR, "mt-6")}>{error}</p>}

        <div className="flex flex-wrap items-center gap-3 mt-6 pt-4 border-t border-stone-100">
          <Link
            to={profilePath(user.id)}
            className={cn("text-small font-semibold text-brand hover:underline underline-offset-2 rounded", FOCUS_RING)}
          >
            View my profile
          </Link>
          {saved && (
            <p role="status" className="flex items-center gap-1.5 text-small text-stone-700">
              <i className="fas fa-check" aria-hidden />
              Profile saved.
            </p>
          )}
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => { resetTo(user); setError(null); setSaved(false); }}
              disabled={!dirty || saving}
              className={cn(PILL_SECONDARY, FOCUS_RING)}
            >
              Discard
            </button>
            <button
              type="submit"
              disabled={!dirty || saving || !!orcidIssue}
              className={cn(PILL_PRIMARY, FOCUS_RING)}
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </Panel>
    </form>
  );
}

/* -------------------------------------------------------------------------- */

function InterestsField({ interests, onChange }: { interests: string[]; onChange: (next: string[]) => void }) {
  const inputId = useId();
  const hintId = useId();
  const suggestedId = useId();
  const [draft, setDraft] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const atLimit = interests.length >= MAX_INTERESTS;

  // Suggestions follow what is typed, a moment after typing stops, so a word
  // typed quickly asks the server once rather than once per letter.
  useEffect(() => {
    const q = draft.trim();
    if (!q || atLimit) { setSuggestions([]); return; }
    let current = true;
    const timer = window.setTimeout(() => {
      profileApi.suggestInterests(q)
        .then(({ data }) => { if (current) setSuggestions(data); })
        .catch(() => { if (current) setSuggestions([]); });
    }, 250);
    return () => { current = false; window.clearTimeout(timer); };
  }, [draft, atLimit]);

  const add = (raw: string) => {
    const tag = raw.trim().replace(/\s+/g, " ");
    if (!tag || atLimit) return;
    if (!interests.some((t) => sameInterest(t, tag))) onChange([...interests, tag]);
    setDraft("");
    setSuggestions([]);
  };

  // The server sends up to ten; five beside a text box is enough to choose from.
  const offered = suggestions.filter((s) => !interests.some((t) => sameInterest(t, s))).slice(0, 5);

  return (
    <div className="mt-6 space-y-1">
      <FieldLabel htmlFor={inputId} label="Research interests" />

      {interests.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 pb-1" aria-label="Your research interests">
          {interests.map((tag) => (
            <li
              key={tag}
              className="inline-flex items-center gap-1 rounded-full ring-1 ring-stone-300 pl-3 pr-1 py-0.5 text-small font-semibold text-stone-800"
            >
              {tag}
              <button
                type="button"
                onClick={() => onChange(interests.filter((t) => t !== tag))}
                aria-label={`Remove ${tag}`}
                className={cn("w-7 h-7 rounded-full grid place-items-center text-stone-600 hover:bg-stone-100 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
              >
                <i className="fas fa-xmark text-label" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex gap-2 max-w-md">
        <input
          id={inputId}
          className={fieldClasses(false)}
          value={draft}
          maxLength={INTEREST_MAX_LENGTH}
          disabled={atLimit}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(draft); }
          }}
          placeholder={atLimit ? undefined : "e.g. Machine learning"}
          autoComplete="off"
          aria-describedby={hintId}
        />
        <button
          type="button"
          onClick={() => add(draft)}
          disabled={atLimit || !draft.trim()}
          className={cn(PILL_SECONDARY, FOCUS_RING)}
        >
          Add
        </button>
      </div>

      {offered.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <span id={suggestedId} className="text-small text-stone-600">Others use:</span>
          <ul className="contents" aria-labelledby={suggestedId}>
            {offered.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => add(s)}
                  aria-label={`Add ${s}`}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full ring-1 ring-stone-300 px-2.5 py-1 text-small text-stone-700 hover:ring-brand/40 hover:text-brand",
                    COLOUR_TRANSITION, FOCUS_RING,
                  )}
                >
                  <i className="fas fa-plus text-label" aria-hidden />
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p id={hintId} className={HINT}>
        {atLimit
          ? `You've added the ${MAX_INTERESTS} interests allowed.`
          : `Up to ${MAX_INTERESTS}, each up to ${INTEREST_MAX_LENGTH} characters. Press Enter to add one.`}
      </p>
    </div>
  );
}
