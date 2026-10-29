import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ResearchCard } from "@/components/shared/ResearchCard";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { TONES } from "@/components/ui/statusTones";
import { cn, formatDate } from "@/lib/utils";
import type { MyResearchItem } from "@/types/records";

import { waitingHref } from "@/features/records/waitingOnYou";

import { groupResearch, type ResearchSection } from "./researchSections";

const CHIP = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-2xs font-semibold";

/**
 * Which offices have cleared it. A clearance kept through a resubmission
 * says so; that is clearance-aware resubmission (ADR-003), shown where the
 * owner works. Who is reviewing now is the server's status line.
 */
function ClearedChips({ item }: { item: MyResearchItem }) {
  // Spans, not a list: the card's status slot is a phrasing context.
  return (
    <>
      {item.cleared_offices.map((office) => (
        <span key={office.office} className={cn(CHIP, TONES.settled)}>
          <i className="fas fa-check" aria-hidden />
          {office.label} cleared{office.preserved && <span className="font-normal"> · kept</span>}
        </span>
      ))}
    </>
  );
}

function ResearchItem({ item }: { item: MyResearchItem }) {
  const byline = [
    item.authors.map((author) => author.name).join(", "),
    item.adviser_name && `Adviser: ${item.adviser_name}`,
  ].filter(Boolean).join(" · ");

  // One link per open request, straight to the act on Paper View (IR-625).
  const waiting = item.submitter_status.waiting_on_you;
  const action = item.pipeline_status === "draft"
    ? <Link to={`/?publish=${item.id}`} className={cn(PILL_SECONDARY, FOCUS_RING)}>Continue</Link>
    : waiting.length > 0
      ? (
        <>
          {waiting.map((request, i) => (
            <Link
              key={`${request.kind}-${request.party}`}
              to={waitingHref(item.id, request)}
              className={cn(i === 0 ? PILL_PRIMARY : PILL_SECONDARY, FOCUS_RING)}
            >
              {request.action_label}{" "}
              <span className="sr-only">({request.label})</span>
            </Link>
          ))}
        </>
      )
      : undefined;

  return (
    <li>
      <ResearchCard
        href={`/records/${item.id}`}
        title={item.title}
        headingLevel={3}
        compact
        eyebrow={item.record_type_name ?? "Research"}
        meta={`Updated ${formatDate(item.updated_at)}`}
        byline={byline || undefined}
        status={
          <>
            <StatusBadge state={item.workflow_state} label={item.submitter_status.line} />
            <ClearedChips item={item} />
          </>
        }
        actions={action}
      />
    </li>
  );
}

function Section({ section }: { section: ResearchSection }) {
  const titleId = `research-${section.id}`;
  const waiting = section.id === "waiting";
  const body = (
    <>
      <div className="mb-3">
        <h2 id={titleId} className={cn("font-display text-title font-semibold", waiting ? "text-brand" : "text-stone-900")}>
          {section.title}
        </h2>
        {section.note && <p className="text-small text-stone-600">{section.note}</p>}
      </div>
      <ul className="space-y-3">
        {section.items.map((item) => <ResearchItem key={item.id} item={item} />)}
      </ul>
    </>
  );

  if (section.id === "archived") {
    return (
      <details className="group rounded-2xl border border-stone-200 bg-surface p-card-compact md:p-card">
        <summary className={cn("cursor-pointer list-none rounded-sm", FOCUS_RING)}>
          <span className="inline-flex items-center gap-2 font-display text-title font-semibold text-stone-900">
            <i className="fas fa-chevron-right text-label text-stone-500 transition-transform duration-150 group-open:rotate-90 motion-reduce:transition-none" aria-hidden />
            Archived
          </span>
          <span className="block text-small text-stone-600">{section.note}</span>
        </summary>
        <ul className="mt-4 space-y-3">
          {section.items.map((item) => <ResearchItem key={item.id} item={item} />)}
        </ul>
      </details>
    );
  }

  return (
    <section
      aria-labelledby={titleId}
      className={cn(waiting && "rounded-2xl border border-brand-100 bg-brand-50 p-card-compact md:p-card")}
    >
      {body}
    </section>
  );
}

interface MyResearchListProps {
  items:   MyResearchItem[];
  loading: boolean;
  failed:  boolean;
  onRetry: () => void;
}

/**
 * The owner's research, grouped by who has each record now (IR-410; spec
 * §4.9 as amended 2026-10-11): what waits on the owner first, then the review
 * path, then drafts and finished work. No counts are shown anywhere.
 */
export function MyResearchList({ items, loading, failed, onRetry }: MyResearchListProps) {
  const [query, setQuery] = useState("");

  const sections = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? items.filter((item) =>
          item.title.toLowerCase().includes(needle) ||
          item.authors.some((author) => author.name.toLowerCase().includes(needle)))
      : items;
    return groupResearch(matched);
  }, [items, query]);

  if (loading) {
    return (
      <div className="space-y-3" role="status">
        <span className="sr-only">Loading your research…</span>
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-32 rounded-xl border border-stone-200 bg-white motion-safe:animate-pulse" aria-hidden />
        ))}
      </div>
    );
  }

  if (failed) {
    return (
      <EmptyState
        framed
        tone="error"
        icon="fa-plug-circle-xmark"
        title="Could not load your research"
        message="Nothing was changed. Check your connection and try again."
        action={<button type="button" onClick={onRetry} className={cn(PILL_SECONDARY, FOCUS_RING)}>Try again</button>}
      />
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        framed
        icon="fa-feather-pointed"
        title="You haven’t published anything yet"
        message="Publish a paper and it will appear here, grouped by who is reviewing it."
        action={<Link to="/?publish=new" className={cn(PILL_PRIMARY, FOCUS_RING)}>Publish</Link>}
      />
    );
  }

  return (
    <div>
      <label className="relative mb-section block">
        <span className="sr-only">Search your research</span>
        <i className="fas fa-magnifying-glass pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-small text-stone-500" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by title or author"
          className="w-full rounded-xl border border-stone-200 bg-white py-2.5 pl-10 pr-3 text-body placeholder:text-stone-500 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
        />
      </label>

      {sections.length === 0 ? (
        <EmptyState
          framed
          icon="fa-magnifying-glass"
          title={`Nothing matches “${query.trim()}”`}
          message="Search looks at titles and author names."
        />
      ) : (
        <div className="space-y-section-lg">
          {sections.map((section) => <Section key={section.id} section={section} />)}
        </div>
      )}
    </div>
  );
}
