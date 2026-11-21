import DiscoverPage from "@/features/discover/DiscoverPage";

/**
 * The home route: Discover, for every role (IR-534, spec §4.1).
 *
 * There was a role split here -- students saw Discover, everyone else a
 * stats dashboard -- which F1 removes. Where a user lands after signing in is
 * a separate decision, `lib/landing.ts`: a reviewer with work goes to My
 * Reviews, but `/` is Discover for them too.
 *
 * The Publish dialog lived here until IR-1258. It is the app shell's now, so
 * `?publish=` opens it over any page, not only over Discover.
 */
export default function HomePage() {
  return <DiscoverPage />;
}
