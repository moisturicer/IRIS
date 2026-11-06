import { Link, useLocation } from "react-router-dom";

import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { FOCUS_RING } from "@/components/ui/interaction";
import { useAuth } from "@/hooks/useAuth";
import { pathFor } from "@/lib/access";
import { cn } from "@/lib/utils";

import { displayName, initialsOf, affiliationOf } from "./names";
import { useAuthedImage } from "./useAuthedImage";

/**
 * Your own Profile (IR-933): the page other signed-in people see for you,
 * with the way to edit it. Account matters (password, consent, role) are in
 * Settings, a separate page.
 *
 * It reads the signed-in user, so it shows nothing the person has not put on
 * their Profile: empty optional fields are left out rather than shown as
 * placeholders, and the account's email address is never printed. Another
 * person's profile page is IR-700, which needs a read endpoint for other users.
 */
export default function ProfilePage() {
  const { user } = useAuth();
  // Edit profile sends the person back here after a save and says so.
  const saved = (useLocation().state as { saved?: boolean } | null)?.saved === true;
  const photoSrc = useAuthedImage(user?.photo_url ?? null);
  if (!user) return null;

  const name = displayName(user);
  const affiliation = affiliationOf(user);
  const interests = user.research_interests ?? [];

  return (
    <div className="max-w-3xl space-y-6">
      {saved && (
        <p role="status" className="flex items-center gap-1.5 text-small text-stone-700">
          <i className="fas fa-check" aria-hidden />
          Profile saved.
        </p>
      )}
      <p
        role="note"
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-stone-200 bg-stone-100 py-2 pl-4 pr-2 text-small text-stone-700"
      >
        This is how other people signed in to IRIS see you.
        <Link to={pathFor("profileEdit")} className={cn(PILL_PRIMARY, FOCUS_RING)}>Edit profile</Link>
      </p>

      <header className="flex flex-wrap items-start gap-6">
        {photoSrc ? (
          <img src={photoSrc} alt={name} className="h-28 w-28 shrink-0 rounded-full object-cover ring-1 ring-stone-200" />
        ) : (
          <span
            aria-hidden
            className="grid h-28 w-28 shrink-0 place-items-center rounded-full bg-brand-50 font-display text-display font-semibold text-brand"
          >
            {initialsOf(user)}
          </span>
        )}
        <div className="min-w-0 flex-1 basis-60">
          <h1 className="font-display text-title font-semibold text-stone-900 sm:text-display">{name}</h1>
          {user.role_name && <p className="mt-1 text-body text-stone-700">{user.role_name}</p>}
          {affiliation && <p className="text-body text-stone-600">{affiliation}</p>}
        </div>
      </header>

      {user.bio && (
        <section aria-labelledby="profile-about" className="border-t border-stone-200 pt-6">
          <h2 id="profile-about" className="font-display text-title font-semibold text-stone-900">About</h2>
          <p className="mt-2 max-w-prose whitespace-pre-line text-body text-stone-700">{user.bio}</p>
        </section>
      )}

      {interests.length > 0 && (
        <section aria-labelledby="profile-interests" className="border-t border-stone-200 pt-6">
          <h2 id="profile-interests" className="font-display text-title font-semibold text-stone-900">Research interests</h2>
          <ul aria-label="Research interests" className="mt-3 flex flex-wrap gap-1.5">
            {interests.map((tag) => (
              <li key={tag} className="rounded-full px-3 py-0.5 text-small font-semibold text-stone-800 ring-1 ring-stone-300">
                {tag}
              </li>
            ))}
          </ul>
        </section>
      )}

      {user.orcid && (
        <section aria-labelledby="profile-orcid" className="border-t border-stone-200 pt-6">
          <h2 id="profile-orcid" className="font-display text-title font-semibold text-stone-900">ORCID iD</h2>
          <p className="mt-2 text-body">
            <a
              href={`https://orcid.org/${user.orcid}`}
              target="_blank"
              rel="noopener noreferrer"
              className={cn("rounded font-mono text-brand underline underline-offset-2", FOCUS_RING)}
            >
              {user.orcid}
            </a>
          </p>
        </section>
      )}
    </div>
  );
}
