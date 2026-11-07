import { Link, Navigate, useParams } from "react-router-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { useAuth } from "@/hooks/useAuth";
import { pathFor } from "@/lib/access";
import { cn } from "@/lib/utils";
import { NotFoundScreen } from "@/features/errors/NotFoundScreen";

import { PersonProfileView } from "./PersonProfileView";
import { SAMPLE_LINKS, personPath, resolveSample } from "./publicProfile";

/**
 * `/people/:id`: another person's Profile (IR-700).
 *
 * PROTOTYPE. It reads sample people from `publicProfile.ts`, not the API,
 * because IR-696 is not in code yet. Three rules are already the real ones:
 * your own id goes to your own Profile, where Edit profile lives; and a person
 * the server would hide (suspended, a System Admin, missing) gets the same
 * not-found screen as an address that matches nothing, so the page never
 * confirms that a hidden account exists.
 *
 * When IR-696 ships: fetch the profile here, fetch each photo with
 * `useAuthedImage`, and delete `PrototypeStrip`.
 */
export default function PersonProfilePage() {
  const { user } = useAuth();
  const id = Number(useParams().id);

  if (user && user.id === id) return <Navigate to={pathFor("profile")} replace />;

  const profile = Number.isInteger(id) ? resolveSample(id) : null;

  return (
    <div className="space-y-8">
      <PrototypeStrip current={id} />
      {profile ? (
        <PersonProfileView key={profile.id} profile={profile} photoSrc={profile.photo_url} />
      ) : (
        <NotFoundScreen subject="Profile" />
      )}
    </div>
  );
}

/** Prototype only: a way to reach each sample state. Not part of the design. */
function PrototypeStrip({ current }: { current: number }) {
  return (
    <nav
      aria-label="Sample profiles"
      className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-stone-200 bg-stone-100 px-4 py-2 text-small text-stone-700"
    >
      <span className="font-semibold text-stone-900">Prototype, sample people</span>
      {SAMPLE_LINKS.map((link) => (
        <Link
          key={link.id}
          to={personPath(link.id)}
          aria-current={link.id === current ? "page" : undefined}
          className={cn(
            "rounded-sm underline-offset-2 hover:underline",
            link.id === current ? "font-semibold text-brand" : "text-stone-700",
            FOCUS_RING,
          )}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
