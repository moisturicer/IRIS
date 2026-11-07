import { useEffect, useId, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ResearchCard } from "@/components/shared/ResearchCard";
import { Spinner } from "@/components/ui/Spinner";
import { FOCUS_RING, COLOUR_TRANSITION } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { INSTITUTION } from "@/config/institution";
import { personPath } from "@/lib/access";
import { cn } from "@/lib/utils";
import type { Collaborator, ProfilePaper, PublicProfile } from "@/types/people";

import { PersonAvatar } from "./PersonAvatar";
import { affiliationOf, displayName, initialsOf } from "./names";
import type { ListKey, ListState, PersonProfileModel } from "./usePersonProfile";

/**
 * What the header, About and Research interests need. Another person's
 * `PublicProfile` fits, and so does the signed-in user once their optional
 * fields are filled in (IR-948), which is what lets both Profiles be this one
 * view. `role_label` is a string here because an account with no role yet has
 * none to show.
 */
export type ProfileSubject = Omit<PublicProfile, "id" | "role_label"> & { role_label: string };

/** The paged lists, with the one way to ask for more of any of them. */
export type ProfileLists = Omit<PersonProfileModel, "profile"> & { onMore: (key: ListKey) => void };

interface PersonProfileViewProps {
  profile: ProfileSubject;
  /**
   * Left out, the page has no Research, Advised or Collaborators and does not
   * say there are no papers: saying so would be wrong for someone whose papers
   * simply have not been loaded. Your own Profile leaves it out until IR-949.
   */
  lists?: ProfileLists;
}

/**
 * A Profile (IR-700): who they are, what they wrote and advised, and who they
 * worked with. It is the one design for everyone, including yourself (IR-948):
 * `/people/:id` and your own `/profile` both mount it. Presentation only; the
 * page that mounts it decides what a reader may see, and the server never sends
 * what they may not.
 *
 * A Garamond name, then sections each under one hairline, and a field left
 * empty is left out. Collaborators sit beside the sections once the page's own
 * width allows it, read from the container and never the window (DESIGN.md,
 * Container Rule), and fall under them otherwise.
 *
 * Nothing here is a total: no counts in a heading, no summed views, no
 * citations. A paper shows its own views, because that figure is the paper's.
 */
export function PersonProfileView({ profile, lists }: PersonProfileViewProps) {
  const name = displayName(profile);
  const affiliation = affiliationOf(profile);
  const interests = profile.research_interests;
  // A list that failed is not an empty one: it keeps its place and says so.
  const showsRail = lists !== undefined
    && (lists.collaborators.items.length > 0 || lists.collaborators.error !== null);
  const noPapers = lists !== undefined
    && lists.research.items.length === 0 && lists.advised.items.length === 0
    && lists.research.error === null && lists.advised.error === null;

  return (
    <div className="[container-type:inline-size] [container-name:profile]">
      <div className="max-w-4xl">
        <header className="flex flex-wrap items-start gap-6">
          <PersonAvatar photoUrl={profile.photo_url} initials={initialsOf(profile)} alt={name} size="lg" />
          <div className="min-w-0 flex-1 basis-48">
            <h1 className="font-display text-title font-semibold text-stone-900 sm:text-display">{name}</h1>
            {profile.role_label && <p className="mt-1 text-body text-stone-700">{profile.role_label}</p>}
            {affiliation && <p className="text-body text-stone-600">{affiliation}</p>}
            <p className="text-small text-stone-600">{INSTITUTION.name}</p>
          </div>
        </header>

        <div
          className={cn(
            "mt-8 border-t border-stone-200 pt-8",
            showsRail && "grid gap-y-8 [@container_profile_(min-width:48rem)]:grid-cols-[minmax(0,1fr)_16rem] [@container_profile_(min-width:48rem)]:gap-x-10",
          )}
        >
          <div className="min-w-0 divide-y divide-stone-200">
            {profile.bio && (
              <Section title="About">
                <p className="max-w-prose whitespace-pre-line text-body text-stone-700">{profile.bio}</p>
              </Section>
            )}

            {interests.length > 0 && (
              <Section title="Research interests">
                <ul aria-label="Research interests" className="flex flex-wrap gap-1.5">
                  {interests.map((tag) => (
                    <li key={tag} className="rounded-full px-3 py-0.5 text-small font-semibold text-stone-800 ring-1 ring-stone-300">
                      {tag}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {lists && (
              <>
                <PaperSection title="Research" list={lists.research} onMore={() => lists.onMore("research")} />
                <PaperSection title="Advised" list={lists.advised} onMore={() => lists.onMore("advised")} />
              </>
            )}

            {noPapers && (
              <p className="py-6 text-body text-stone-600 first:pt-0">No published papers yet.</p>
            )}
          </div>

          {lists && showsRail && (
            <CollaboratorRail list={lists.collaborators} onMore={() => lists.onMore("collaborators")} />
          )}
        </div>
      </div>
    </div>
  );
}

/** One section under its hairline; the first one has nothing above it to divide from. */
function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="py-6 first:pt-0 last:pb-0">
      <h2 id={id} className="font-display text-title font-semibold text-stone-900">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/**
 * After Show more, focus goes to the first row that arrived, so a keyboard
 * reader lands where the new rows begin and not on a button that has just gone.
 */
function useFocusFirstNewRow(count: number) {
  const list = useRef<HTMLUListElement>(null);
  const focusAt = useRef<number | null>(null);
  useEffect(() => {
    if (focusAt.current === null || count <= focusAt.current) return;
    list.current?.querySelectorAll(":scope > li")[focusAt.current]?.querySelector<HTMLElement>("a")?.focus();
    focusAt.current = null;
  }, [count]);
  return { list, mark: () => { focusAt.current = count; } };
}

/** What sits under a list: its failure, with a retry, or Show more while there is more. */
function ListFooter({ list, label, onMore }: { list: ListState<unknown>; label: string; onMore: () => void }) {
  if (list.loadingMore) {
    return (
      <p role="status" className="mt-4 inline-flex items-center gap-2 text-small text-stone-700">
        <Spinner size="sm" /> Loading…
      </p>
    );
  }
  if (list.error) {
    return (
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <p role="alert" className="text-small text-stone-700">{list.error}</p>
        <button type="button" onClick={onMore} className={cn(PILL_SECONDARY, FOCUS_RING)}>Try again</button>
      </div>
    );
  }
  if (!list.hasMore) return null;
  return (
    <button
      type="button"
      onClick={onMore}
      aria-label={`Show more ${label}`}
      className={cn(PILL_SECONDARY, FOCUS_RING, "mt-4")}
    >
      Show more
    </button>
  );
}

function PaperSection({ title, list, onMore }: { title: string; list: ListState<ProfilePaper>; onMore: () => void }) {
  const { list: rows, mark } = useFocusFirstNewRow(list.items.length);
  // A first page that is being retried keeps its place: the section does not vanish and come back.
  if (list.items.length === 0 && !list.error && !list.loadingMore) return null;
  return (
    <Section title={title}>
      {list.items.length > 0 && (
        <ul ref={rows} aria-label={title} className="space-y-3">
          {list.items.map((paper) => (
            <li key={paper.id}>
              <ResearchCard
                layout="list"
                compact
                headingLevel={3}
                href={`/records/${paper.id}`}
                title={paper.title}
                eyebrow={[paper.classification_name, paper.record_type_name].filter(Boolean).join(" · ")}
                meta={paper.publication_year ? `Published ${paper.publication_year}` : undefined}
                byline={paper.authors.join(", ")}
                footer={
                  <span className="inline-flex items-center gap-1.5 text-stone-700" title="Accounts that have opened this paper">
                    <i className="fas fa-eye text-[12px] text-brand" aria-hidden />
                    {paper.views} {paper.views === 1 ? "view" : "views"}
                  </span>
                }
              />
            </li>
          ))}
        </ul>
      )}
      <ListFooter list={list} label={`${title.toLowerCase()} papers`} onMore={() => { mark(); onMore(); }} />
    </Section>
  );
}

/**
 * Collaborators: other accounts that shared a published paper with this person.
 * Beside the sections it is divided from them by one vertical hairline; under
 * them, by the same hairline laid flat.
 */
function CollaboratorRail({ list, onMore }: { list: ListState<Collaborator>; onMore: () => void }) {
  const id = useId();
  const { list: rows, mark } = useFocusFirstNewRow(list.items.length);
  return (
    <aside
      aria-labelledby={id}
      className="border-t border-stone-200 pt-6 [@container_profile_(min-width:48rem)]:border-l [@container_profile_(min-width:48rem)]:border-t-0 [@container_profile_(min-width:48rem)]:pl-8 [@container_profile_(min-width:48rem)]:pt-0"
    >
      <h2 id={id} className="font-display text-title font-semibold text-stone-900">Collaborators</h2>
      {list.items.length > 0 && (
        <ul ref={rows} className="-mx-2 mt-3">
          {list.items.map((person) => (
            <li
              key={person.id}
              className={cn(
                "relative flex min-h-11 items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-stone-100 focus-within:bg-stone-100",
                COLOUR_TRANSITION,
              )}
            >
              <PersonAvatar photoUrl={person.photo_url} initials={initialsOf(person)} size="sm" />
              <div className="min-w-0">
                <Link
                  to={personPath(person.id)}
                  className={cn(
                    "block truncate rounded-sm text-body font-semibold text-stone-900 hover:text-brand",
                    COLOUR_TRANSITION,
                    FOCUS_RING,
                    "after:absolute after:inset-0 after:content-['']",
                  )}
                >
                  {displayName(person)}
                </Link>
                <p className="text-small text-stone-600">
                  {person.shared_papers} shared {person.shared_papers === 1 ? "paper" : "papers"}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      <ListFooter list={list} label="collaborators" onMore={() => { mark(); onMore(); }} />
    </aside>
  );
}
