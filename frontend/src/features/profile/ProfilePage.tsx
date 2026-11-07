import { Link, useLocation } from "react-router-dom";

import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { FOCUS_RING } from "@/components/ui/interaction";
import { useAuth } from "@/hooks/useAuth";
import { pathFor } from "@/lib/access";
import { cn } from "@/lib/utils";

import { PersonProfileView, type ProfileSubject } from "./PersonProfileView";

/**
 * Your own Profile (IR-933): the page other signed-in people see for you, with
 * the way to edit it. Account matters (password, consent, role) are in
 * Settings, a separate page.
 *
 * The Profile itself is the shared view other people's Profiles use (IR-948),
 * so there is one design for everyone. It reads the signed-in user, so it shows
 * nothing the person has not put on their Profile: empty optional fields are
 * left out rather than shown as placeholders, and the account's email address
 * is never printed. Research, Advised and Collaborators are left out until
 * IR-949 reads them; the view does not say "No published papers yet." for a
 * person whose papers have simply not been loaded.
 */
export default function ProfilePage() {
  const { user } = useAuth();
  // Edit profile sends the person back here after a save and says so.
  const saved = (useLocation().state as { saved?: boolean } | null)?.saved === true;
  if (!user) return null;

  // bio, interests and photo are optional on `User`, so an absent one reads as empty.
  const profile: ProfileSubject = {
    first_name:         user.first_name,
    middle_initial:     user.middle_initial,
    last_name:          user.last_name,
    role_label:         user.role_name ?? "",
    college_name:       user.college_name,
    department_name:    user.department_name,
    course_name:        user.course_name,
    bio:                user.bio ?? "",
    research_interests: user.research_interests ?? [],
    photo_url:          user.photo_url ?? null,
  };

  return (
    <div className="max-w-4xl space-y-6">
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

      <PersonProfileView profile={profile} />
    </div>
  );
}
