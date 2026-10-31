import { useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  BIO_MAX_LENGTH, INTEREST_MAX_LENGTH, MAX_INTERESTS, profileApi, profilePath,
} from "@/api/profile";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { ORCID_EXAMPLE, orcidProblem } from "@/lib/orcid";
import { cn } from "@/lib/utils";
import type { User } from "@/types/auth";

import { PhotoField } from "./PhotoField";
import { inputClass, Notice, Panel, primaryButtonClass, secondaryButtonClass } from "./settingsParts";

/**
 * The optional Profile fields (IR-699): photo, bio, research interests and
 * ORCID iD, as the IR-694 spec decided and IR-695's contract carries them.
 *
 * Every one is optional, and leaving one empty is how a person keeps it off
 * their Profile: there is no privacy switch. The photo saves as soon as it is
 * cropped; the text fields save together with Save.
 */

const labelClass = "block text-[12px] font-bold uppercase tracking-wider text-stone-500 mb-1.5";
const hintClass = "block text-[12px] text-stone-500 mt-1.5";

const sameInterest = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase();

export function AboutYouPanel({ user, onSaved }: { user: User; onSaved: (u: User) => void }) {
  const [bio, setBio] = useState(user.bio ?? "");
  const [interests, setInterests] = useState<string[]>(user.research_interests ?? []);
  const [orcid, setOrcid] = useState(user.orcid ?? "");
  const [orcidTouched, setOrcidTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ids = { bio: useId(), bioCount: useId(), interests: useId(), interestHint: useId(), orcid: useId(), orcidHint: useId() };

  const orcidIssue = orcidProblem(orcid);
  // Say so once the iD could be complete, or as soon as a character that can
  // never belong in one is typed: not on every keystroke of a half-typed iD.
  const showOrcidIssue = !!orcidIssue && (orcidTouched || orcid.trim().length >= ORCID_EXAMPLE.length || /[^\d\-Xx\s]/.test(orcid));

  const dirty = useMemo(() => {
    const saved = user.research_interests ?? [];
    return (
      bio !== (user.bio ?? "") ||
      orcid.trim() !== (user.orcid ?? "") ||
      interests.length !== saved.length ||
      interests.some((tag, i) => tag !== saved[i])
    );
  }, [bio, orcid, interests, user]);

  const resetTo = (u: User) => {
    setBio(u.bio ?? "");
    setInterests(u.research_interests ?? []);
    setOrcid(u.orcid ?? "");
    setOrcidTouched(false);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (orcidIssue) return;
    setError(null);
    setOk(false);
    setSaving(true);
    try {
      const { data } = await profileApi.updateFields({
        bio,
        research_interests: interests,
        orcid: orcid.trim() || null,
      });
      onSaved(data);
      resetTo(data);
      setOk(true);
    } catch (err) {
      setError(
        fieldError(err, "bio") ??
          fieldError(err, "research_interests") ??
          fieldError(err, "orcid") ??
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

        <div className="mt-6">
          <label htmlFor={ids.bio} className={labelClass}>Bio</label>
          <textarea
            id={ids.bio}
            className={cn(inputClass, "min-h-[96px] resize-y")}
            value={bio}
            maxLength={BIO_MAX_LENGTH}
            onChange={(e) => setBio(e.target.value)}
            aria-describedby={ids.bioCount}
          />
          <span id={ids.bioCount} className={hintClass} aria-live="polite">
            {bio.length} / {BIO_MAX_LENGTH} characters
          </span>
        </div>

        <InterestsField
          inputId={ids.interests}
          hintId={ids.interestHint}
          interests={interests}
          onChange={setInterests}
        />

        <div className="mt-6 max-w-sm">
          <label htmlFor={ids.orcid} className={labelClass}>ORCID iD</label>
          <input
            id={ids.orcid}
            className={cn(inputClass, "font-mono", showOrcidIssue && "border-red-300 focus:border-red-400 focus:ring-red-200")}
            value={orcid}
            onChange={(e) => setOrcid(e.target.value)}
            onBlur={() => setOrcidTouched(true)}
            placeholder={ORCID_EXAMPLE}
            inputMode="text"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={showOrcidIssue || undefined}
            aria-describedby={ids.orcidHint}
          />
          <span id={ids.orcidHint} className={cn(hintClass, showOrcidIssue && "text-red-700")}>
            {showOrcidIssue ? orcidIssue : "Your own iD from orcid.org. IRIS shows it as you enter it and doesn't verify it with ORCID."}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2 mt-6 pt-4 border-t border-stone-100">
          <Link
            to={profilePath(user.id)}
            className="text-[13px] font-semibold text-brand hover:underline underline-offset-2"
          >
            View my profile
          </Link>
          {ok && <Notice tone="ok">Profile saved.</Notice>}
          {error && <Notice tone="error">{error}</Notice>}
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => { resetTo(user); setError(null); setOk(false); }}
              disabled={!dirty || saving}
              className={secondaryButtonClass}
            >
              Discard
            </button>
            <button type="submit" disabled={!dirty || saving || !!orcidIssue} className={primaryButtonClass}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </Panel>
    </form>
  );
}

/* -------------------------------------------------------------------------- */

function InterestsField({
  inputId, hintId, interests, onChange,
}: { inputId: string; hintId: string; interests: string[]; onChange: (next: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const full = interests.length >= MAX_INTERESTS;

  // Suggestions follow what is typed, a moment after typing stops, so a word
  // typed quickly asks the server once rather than once per letter.
  useEffect(() => {
    const q = draft.trim();
    if (!q || full) { setSuggestions([]); return; }
    let live = true;
    const timer = window.setTimeout(() => {
      profileApi.suggestInterests(q)
        .then(({ data }) => { if (live) setSuggestions(data); })
        .catch(() => { if (live) setSuggestions([]); });
    }, 250);
    return () => { live = false; window.clearTimeout(timer); };
  }, [draft, full]);

  const add = (raw: string) => {
    const tag = raw.trim().replace(/\s+/g, " ");
    if (!tag || full) return;
    if (!interests.some((t) => sameInterest(t, tag))) onChange([...interests, tag]);
    setDraft("");
    setSuggestions([]);
  };

  const offered = suggestions.filter((s) => !interests.some((t) => sameInterest(t, s))).slice(0, 5);

  return (
    <div className="mt-6">
      <label htmlFor={inputId} className={labelClass}>Research interests</label>

      {interests.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 mb-2" aria-label="Your research interests">
          {interests.map((tag) => (
            <li
              key={tag}
              className="inline-flex items-center gap-1 rounded-full bg-brand-50 text-brand pl-3 pr-1 py-1 text-[13px] font-medium"
            >
              {tag}
              <button
                type="button"
                onClick={() => onChange(interests.filter((t) => t !== tag))}
                aria-label={`Remove ${tag}`}
                className="w-6 h-6 rounded-full grid place-items-center hover:bg-brand/10
                  focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
              >
                <i className="fas fa-xmark text-[11px]" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex gap-2 max-w-md">
        <input
          id={inputId}
          className={inputClass}
          value={draft}
          maxLength={INTEREST_MAX_LENGTH}
          disabled={full}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(draft); }
          }}
          placeholder={full ? undefined : "e.g. Machine learning"}
          autoComplete="off"
          aria-describedby={hintId}
        />
        <button
          type="button"
          onClick={() => add(draft)}
          disabled={full || !draft.trim()}
          className={secondaryButtonClass}
        >
          Add
        </button>
      </div>

      {offered.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] text-stone-500" id={`${inputId}-suggested`}>Others use:</span>
          <ul className="contents" aria-labelledby={`${inputId}-suggested`}>
            {offered.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => add(s)}
                  aria-label={`Add ${s}`}
                  className="rounded-full border border-stone-200 px-2.5 py-1 text-[12px] text-stone-700 hover:bg-stone-50"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <span id={hintId} className={hintClass}>
        {full
          ? `You've added the ${MAX_INTERESTS} interests allowed.`
          : `Up to ${MAX_INTERESTS}, each up to ${INTEREST_MAX_LENGTH} characters. Press Enter to add one.`}
      </span>
    </div>
  );
}
