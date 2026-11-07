import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ResearchCard } from "@/components/shared/ResearchCard";
import { FOCUS_RING, COLOUR_TRANSITION } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";

import { PersonAvatar } from "./PersonAvatar";
import { affiliationOf, displayName, initialsOf } from "./names";
import {
  PAGE_SIZE,
  UNIVERSITY,
  personPath,
  type Collaborator,
  type ProfilePaper,
  type PublicProfile,
} from "./publicProfile";

/**
 * Another person's Profile (IR-700): who they are, what they wrote and advised,
 * and who they worked with. Presentation only; the page that mounts it decides
 * what a reader may see, and the server never sends what they may not.
 *
 * It follows the typeset entry of your own Profile (IR-933): a Garamond name,
 * then sections each under one hairline, and a field left empty is left out.
 * What is new is a second column. Collaborators sit beside the sections once
 * the page's own width allows it, read from the container and never the window
 * (DESIGN.md, Container Rule), and fall under them otherwise.
 *
 * Nothing here is a total: no counts in a heading, no summed views, no
 * citations. A paper shows its own views, because that figure is the paper's.
 */
interface PersonProfileViewProps {
  profile: PublicProfile;
  /** The large photo, already fetched; the page owns how (IR-699's blob fetch). */
  photoSrc: string | null;
}

export function PersonProfileView({ profile, photoSrc }: PersonProfileViewProps) {
  const name = displayName(profile);
  const affiliation = affiliationOf(profile);
  const interests = profile.research_interests;
  const hasPapers = profile.research.length > 0 || profile.advised.length > 0;
  const hasRail = profile.collaborators.length > 0;

  return (
    <div className="[container-type:inline-size] [container-name:profile]">
      <div className="max-w-5xl">
        <header className="flex flex-wrap items-start gap-6">
          <PersonAvatar src={photoSrc} initials={initialsOf(profile)} alt={name} size="lg" />
          <div className="min-w-0 flex-1 basis-48">
            <h1 className="font-display text-title font-semibold text-stone-900 sm:text-display">{name}</h1>
            <p className="mt-1 text-body text-stone-700">{profile.role_label}</p>
            {affiliation && <p className="text-body text-stone-600">{affiliation}</p>}
            <p className="text-small text-stone-600">{UNIVERSITY}</p>
          </div>
        </header>

        <div
          className={cn(
            "mt-8 border-t border-stone-200 pt-8",
            hasRail && "grid gap-y-8 [@container_profile_(min-width:48rem)]:grid-cols-[minmax(0,1fr)_16rem] [@container_profile_(min-width:48rem)]:gap-x-10",
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

            {profile.research.length > 0 && <PaperSection title="Research" papers={profile.research} />}
            {profile.advised.length > 0 && <PaperSection title="Advised" papers={profile.advised} />}

            {!hasPapers && (
              <p className="py-6 text-body text-stone-600 first:pt-0">No published papers yet.</p>
            )}
          </div>

          {hasRail && <CollaboratorRail collaborators={profile.collaborators} />}
        </div>
      </div>
    </div>
  );
}

/** One section under its hairline; the first one has nothing above it to divide from. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="py-6 first:pt-0 last:pb-0">
      <h2 id={id} className="font-display text-title font-semibold text-stone-900">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

/**
 * Shows `step` rows at a time. Showing more puts focus on the first row that
 * arrived, so a keyboard reader lands where the new rows begin and not on a
 * button that has just disappeared.
 */
function useReveal(total: number, step: number) {
  const [shown, setShown] = useState(step);
  const list = useRef<HTMLUListElement>(null);
  const focusAt = useRef<number | null>(null);

  useEffect(() => {
    if (focusAt.current === null) return;
    const row = list.current?.querySelectorAll(":scope > li")[focusAt.current];
    row?.querySelector<HTMLElement>("a")?.focus();
    focusAt.current = null;
  }, [shown]);

  return {
    list,
    shown: Math.min(shown, total),
    hasMore: shown < total,
    showMore: () => {
      focusAt.current = shown;
      setShown(shown + step);
    },
  };
}

function PaperSection({ title, papers }: { title: string; papers: ProfilePaper[] }) {
  const { list, shown, hasMore, showMore } = useReveal(papers.length, PAGE_SIZE.papers);
  return (
    <Section title={title}>
      <ul ref={list} aria-label={title} className="space-y-3">
        {papers.slice(0, shown).map((paper) => (
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
      {hasMore && (
        <button
          type="button"
          onClick={showMore}
          aria-label={`Show more ${title.toLowerCase()} papers`}
          className={cn(PILL_SECONDARY, FOCUS_RING, "mt-4")}
        >
          Show more
        </button>
      )}
    </Section>
  );
}

/**
 * Collaborators: other accounts that shared a published paper with this person.
 * Beside the sections it is divided from them by one vertical hairline; under
 * them, by the same hairline laid flat.
 */
function CollaboratorRail({ collaborators }: { collaborators: Collaborator[] }) {
  const id = useId();
  const { list, shown, hasMore, showMore } = useReveal(collaborators.length, PAGE_SIZE.collaborators);
  return (
    <aside
      aria-labelledby={id}
      className="border-t border-stone-200 pt-6 [@container_profile_(min-width:48rem)]:border-l [@container_profile_(min-width:48rem)]:border-t-0 [@container_profile_(min-width:48rem)]:pl-8 [@container_profile_(min-width:48rem)]:pt-0"
    >
      <h2 id={id} className="font-display text-title font-semibold text-stone-900">Collaborators</h2>
      <ul ref={list} className="-mx-2 mt-3">
        {collaborators.slice(0, shown).map((person) => {
          const name = displayName(person);
          return (
            <li
              key={person.id}
              className={cn(
                "relative flex min-h-11 items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-stone-100 focus-within:bg-stone-100",
                COLOUR_TRANSITION,
              )}
            >
              <PersonAvatar src={person.photo_url} initials={initialsOf(person)} size="sm" />
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
                  {name}
                </Link>
                <p className="text-small text-stone-600">
                  {person.shared_papers} shared {person.shared_papers === 1 ? "paper" : "papers"}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
      {hasMore && (
        <button
          type="button"
          onClick={showMore}
          aria-label="Show more collaborators"
          className={cn(PILL_SECONDARY, FOCUS_RING, "mt-4")}
        >
          Show more
        </button>
      )}
    </aside>
  );
}
