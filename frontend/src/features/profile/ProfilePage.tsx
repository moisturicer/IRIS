import { useAuth } from "@/hooks/useAuth";

import { PersonProfileView, type ProfileSubject } from "./PersonProfileView";
import { useOwnProfileLists } from "./usePersonProfile";

/**
 * Your own Profile (IR-933): the page other signed-in people see for you. It is
 * only a preview: editing it, like the password, consent and role, is in
 * Settings (IR-1304), which the note says and Settings links back from.
 *
 * The Profile itself is the shared view other people's Profiles use (IR-948),
 * so there is one design for everyone. It reads the signed-in user, so it shows
 * nothing the person has not put on their Profile: empty optional fields are
 * left out rather than shown as placeholders, and the account's email address
 * is never printed. Research, Advised and Collaborators use the same paged
 * endpoints and presentation as another person's Profile (IR-949).
 */
export default function ProfilePage() {
  const { user } = useAuth();
  const lists = useOwnProfileLists(user?.id ?? null);
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
      <p
        role="note"
        className="flex flex-wrap items-center gap-2 rounded-card border border-stone-200 bg-stone-100 px-4 py-2 text-small text-stone-700"
      >
        <i className="fas fa-eye" aria-hidden />
        <span>This is how other IRIS accounts see your profile. Change it in Settings.</span>
      </p>

      <PersonProfileView profile={profile} lists={lists} self />
    </div>
  );
}
