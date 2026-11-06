import { useEffect, useId, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  BIO_MAX_LENGTH, INTEREST_MAX_LENGTH, MAX_INTERESTS, profileApi,
} from "@/api/profile";
import { authApi } from "@/api/auth";
import { PageHeader } from "@/components/layout/PageHeader";
import { FieldError } from "@/components/ui/FieldError";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { fieldClasses, LOAD_ERROR } from "@/components/ui/fieldClasses";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { useAuth } from "@/hooks/useAuth";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { ORCID_EXAMPLE, orcidProblem } from "@/lib/orcid";
import { cn } from "@/lib/utils";

import { affiliationOf } from "./names";
import { PhotoField } from "./PhotoField";

/**
 * Edit profile (IR-933): the name and the optional Profile fields (IR-699:
 * photo, bio, research interests, ORCID iD), on a page of their own, apart
 * from Settings.
 *
 * Every optional field may be left empty, which is how a person keeps it off
 * their Profile: there is no privacy switch. The photo saves as soon as it is
 * cropped. The name and the text fields save together with Save, as the two
 * requests the API takes, and Save and Cancel both return to the Profile.
 */

const HINT = "text-small text-stone-600 mt-1";

const sameInterest = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase();

export default function EditProfilePage() {
  const { user, updateUser } = useAuth();
  const navigate = useNavigate();

  const [firstName, setFirstName] = useState(user?.first_name ?? "");
  const [middle, setMiddle] = useState(user?.middle_initial ?? "");
  const [lastName, setLastName] = useState(user?.last_name ?? "");
  const [bio, setBio] = useState(user?.bio ?? "");
  const [interests, setInterests] = useState<string[]>(user?.research_interests ?? []);
  const [orcid, setOrcid] = useState(user?.orcid ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const firstId = useId();
  const middleId = useId();
  const lastId = useId();
  const affiliationId = useId();
  const bioId = useId();
  const bioCountId = useId();
  const orcidId = useId();
  const orcidHintId = useId();
  const aboutId = useId();
  const nameSectionId = useId();

  const orcidIssue = orcidProblem(orcid);

  const stored = user?.research_interests ?? [];
  const nameDirty = !!user && (
    firstName !== user.first_name ||
    middle !== (user.middle_initial ?? "") ||
    lastName !== user.last_name
  );
  const fieldsDirty = !!user && (
    bio !== (user.bio ?? "") ||
    orcid.trim() !== (user.orcid ?? "") ||
    interests.length !== stored.length ||
    interests.some((tag, i) => tag !== stored[i])
  );

  if (!user) return null;
  const dirty = nameDirty || fieldsDirty;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (orcidIssue) return;
    setError(null);
    if (!firstName.trim() || !lastName.trim()) {
      setError("First and last name are required.");
      return;
    }
    setSaving(true);
    try {
      if (nameDirty) {
        const { data } = await authApi.updateMe({
          first_name: firstName.trim(),
          middle_initial: middle.trim(),
          last_name: lastName.trim(),
        });
        updateUser(data);
      }
      if (fieldsDirty) {
        const { data } = await profileApi.updateFields({
          bio,
          research_interests: interests,
          orcid: orcid.trim() || null,
        });
        updateUser(data);
      }
      navigate("/profile", { state: { saved: true } });
    } catch (err) {
      setError(
        fieldError(err, "bio", "research_interests", "orcid") ??
          errorDetail(err, "Could not save your profile. Please try again."),
      );
    } finally {
      setSaving(false);
    }
  };

  const affiliation = affiliationOf(user);

  return (
    <form onSubmit={save} className="max-w-3xl">
      <PageHeader
        title="Edit profile"
        description="What you add here appears on your Profile, which anyone signed in to IRIS can open. Leave an optional field empty to keep it off."
      />

      <Section id={nameSectionId} title="Photo and name" caption="Your name is attached to disclosures, paper citations and clearances.">
        <PhotoField user={user} onSaved={updateUser} />

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-[1fr_7rem_1fr]">
          <div className="space-y-1">
            <FieldLabel htmlFor={firstId} label="First name" />
            <input id={firstId} className={fieldClasses(false)} value={firstName} onChange={(e) => setFirstName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <FieldLabel htmlFor={middleId} label="M.I." />
            <input id={middleId} className={fieldClasses(false)} value={middle} maxLength={20} onChange={(e) => setMiddle(e.target.value)} />
          </div>
          <div className="space-y-1">
            <FieldLabel htmlFor={lastId} label="Last name" />
            <input id={lastId} className={fieldClasses(false)} value={lastName} onChange={(e) => setLastName(e.target.value)} />
          </div>
        </div>

        <div className="mt-4 space-y-1">
          <FieldLabel htmlFor={affiliationId} label="Affiliation" />
          <input
            id={affiliationId}
            className={cn(fieldClasses(false), "bg-stone-50 text-stone-600")}
            value={affiliation || "Not recorded for this account"}
            readOnly
            aria-readonly
          />
          <p className={HINT}>
            Recorded by the university. Ask RDCO if this is wrong; it decides how your disclosures are routed.
          </p>
        </div>
      </Section>

      <Section id={aboutId} title="About you" caption="Optional.">
        <div className="space-y-1">
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
      </Section>

      {error && <p role="alert" className={cn(LOAD_ERROR, "mt-6")}>{error}</p>}

      <div className="mt-6 flex flex-wrap items-center justify-end gap-2 border-t border-stone-200 pt-4">
        <Link to="/profile" className={cn(PILL_SECONDARY, FOCUS_RING)}>Cancel</Link>
        <button
          type="submit"
          disabled={!dirty || saving || !!orcidIssue}
          className={cn(PILL_PRIMARY, FOCUS_RING)}
        >
          {saving ? "Saving..." : "Save"}
        </button>
      </div>
    </form>
  );
}

/** A titled group on the edit page, divided from the next by one hairline. */
function Section({
  id, title, caption, children,
}: { id: string; title: string; caption: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="border-t border-stone-200 py-6">
      <h2 id={id} className="font-display text-title font-semibold text-stone-900">{title}</h2>
      <p className="mt-1 text-small text-stone-600">{caption}</p>
      <div className="mt-5">{children}</div>
    </section>
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
