/**
 * Guidelines (ADR-063 decision 7, IR-974): what each record type needs, and the
 * Templates to follow, for everyone signed in.
 *
 * Built around the one question a reader brings: "what do I need for my
 * paper?" So the page shows one record type at a time, chosen at the top and
 * kept in the address (`#thesis-research`, which Publish links to), and answers
 * in the order that matters:
 *
 * 1. **What you submit**: the Manuscript, the only thing submitting needs.
 * 2. **Have these ready**: the requirements RDCO marks Required. They never
 *    block submitting; an office asks for them during review.
 * 3. **Only if they apply**: the Optional ones, folded away until asked for.
 *
 * Each group keeps RDCO's order. The Proposal also lists Advisers' Templates
 * (My Templates, IR-975), with a search by Adviser.
 *
 * It only reads and downloads. What shows is the server's: a hidden requirement,
 * or a suspended or former Adviser's Templates, never reach this page.
 */
import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  guidelinesApi, type GuidelineRecordType, type GuidelineRequirement, type SharedTemplate,
} from "@/api/guidelines";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { PlainTextWithLinks } from "@/components/shared/PlainTextWithLinks";
import { SELECTED_SEGMENT } from "@/components/ui/highlightRoles";
import { Input } from "@/components/ui/Input";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { Spinner } from "@/components/ui/Spinner";
import { useApiRead } from "@/hooks/useApiRead";
import { failureMessage } from "@/lib/readFailure";
import { cn } from "@/lib/utils";
import { isGuidelines, isSharedList } from "./requirementGuide";
import { sectionId } from "./sectionId";
import { TemplateDownload } from "./TemplateDownload";

/** The record type whose section lists Advisers' Templates (`RecordTypeName.PROPOSAL`). */
const PROPOSAL = "Proposal";

/** Only a list of record types is usable; anything else is a failed read (CODING_STANDARDS F1). */
export default function GuidelinesPage() {
  const read = useApiRead((signal) => guidelinesApi.list({ signal }).then((r) => r.data), []);
  const types = read.status === "ready" && isGuidelines(read.data) ? read.data : null;

  return (
    <div>
      <PageHeader
        title="Guidelines"
        description="Choose what you are submitting to see what it needs. Only the manuscript is needed to submit: the rest is what RDCO expects, and an office asks for anything it needs later."
      />
      {read.status === "interrupted" ? (
        <InterruptedState what="guidelines" onRetry={read.retry} framed />
      ) : read.status === "failed" ? (
        <LoadFailedAlert
          message={failureMessage(read.error, { lead: "The guidelines didn't load." })}
          onRetry={read.retry}
        />
      ) : read.status === "loading" ? (
        <p role="status" className="flex items-center gap-2 text-small text-stone-600">
          <Spinner size="sm" />
          Loading the guidelines…
        </p>
      ) : !types || types.length === 0 ? (
        <LoadFailedAlert
          message="The guidelines didn't load: IRIS sent an answer this page can't read."
          onRetry={read.retry}
        />
      ) : (
        <TypeChooser types={types} />
      )}
    </div>
  );
}

/** One record type at a time, chosen with a segmented control and kept in the address. */
function TypeChooser({ types }: { types: GuidelineRecordType[] }) {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const tabsId = useId();
  const tabRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  const wanted = decodeURIComponent(hash.slice(1));
  const current = types.find((rt) => sectionId(rt.name) === wanted) ?? types[0];

  const choose = (rt: GuidelineRecordType) => {
    navigate({ hash: sectionId(rt.name) }, { replace: true });
  };

  /* The ARIA tabs pattern: arrows move between record types. */
  const onKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const i = types.findIndex((rt) => rt.id === current.id);
    const next = types[(i + step + types.length) % types.length];
    choose(next);
    tabRefs.current[next.id]?.focus();
  };

  return (
    <>
      <div
        role="tablist"
        aria-label="Record types"
        className="mb-8 flex max-w-full flex-wrap gap-0.5 rounded-control bg-stone-200 p-0.5 sm:inline-flex"
      >
        {types.map((rt) => {
          const on = rt.id === current.id;
          return (
            <button
              key={rt.id}
              ref={(el) => { tabRefs.current[rt.id] = el; }}
              type="button"
              role="tab"
              id={`${tabsId}-${rt.id}`}
              aria-selected={on}
              aria-controls={sectionId(rt.name)}
              tabIndex={on ? 0 : -1}
              onClick={() => choose(rt)}
              onKeyDown={onKey}
              className={cn(
                "flex-1 rounded-control px-4 py-2 text-control font-semibold touch:min-h-11 sm:flex-none",
                on ? SELECTED_SEGMENT : "text-stone-600 hover:text-stone-900",
                COLOUR_TRANSITION,
                FOCUS_RING,
              )}
            >
              {rt.name}
            </button>
          );
        })}
      </div>
      <RecordTypePanel key={current.id} recordType={current} />
    </>
  );
}

function RecordTypePanel({ recordType }: { recordType: GuidelineRecordType }) {
  const headingId = useId();
  const { name, description, manuscript, requirements } = recordType;
  const required = requirements.filter((r) => r.is_required);
  const optional = requirements.filter((r) => !r.is_required);

  return (
    <section
      id={sectionId(name)}
      role="tabpanel"
      aria-labelledby={headingId}
      className="space-y-10"
    >
      <div>
        <h2 id={headingId} className="font-display text-section font-semibold text-stone-900">{name}</h2>
        {description && (
          <PlainTextWithLinks text={description} className="mt-2 text-body text-justified text-stone-700" />
        )}
      </div>

      <Group
        title="What you submit"
        lead="The only thing you need to submit. Upload it in Publish."
      >
        <div className="rounded-card bg-stone-100 px-5 py-4">
          <Requirement
            name="Manuscript"
            description={manuscript.description}
            templateName={manuscript.template_name}
            download={() => guidelinesApi.downloadManuscriptTemplate(recordType.id)}
          />
        </div>
      </Group>

      {required.length > 0 && (
        <Group
          title="Have these ready"
          lead="RDCO expects these. They don't stop you submitting: an office asks for each one during review."
        >
          <RequirementList label={`${name}: have these ready`} items={required} />
        </Group>
      )}

      {optional.length > 0 && <OptionalGroup name={name} items={optional} />}

      {name === PROPOSAL && <AdvisersTemplates />}
    </section>
  );
}

function Group({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id}>
      <h3 id={id} className="font-display text-title font-semibold text-stone-900">{title}</h3>
      <p className="mt-1 text-small text-stone-600">{lead}</p>
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** The Optional requirements, folded away: most readers need none of them. */
function OptionalGroup({ name, items }: { name: string; items: GuidelineRequirement[] }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const count = items.length === 1 ? "1 optional document" : `${items.length} optional documents`;

  return (
    <Group
      title="Only if they apply"
      lead="Optional. Add one only when it fits your work, or when an office asks for it."
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((was) => !was)}
        className={cn(
          "-ml-2 inline-flex items-center gap-2 rounded-control px-2 py-1.5 text-small font-semibold text-stone-800",
          "hover:bg-stone-100 touch:min-h-11",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
      >
        <i
          className={cn("fas fa-chevron-right text-2xs text-stone-500 transition-transform duration-200 motion-reduce:transition-none",
                        open && "rotate-90")}
          aria-hidden
        />
        {open ? `Hide ${count}` : `Show ${count}`}
      </button>
      {open && (
        <div id={listId} className="mt-3">
          <RequirementList label={`${name}: only if they apply`} items={items} />
        </div>
      )}
    </Group>
  );
}

function RequirementList({ label, items }: { label: string; items: GuidelineRequirement[] }) {
  return (
    <ul aria-label={label} className="divide-y divide-stone-200 border-y border-stone-200">
      {items.map((req) => (
        <li key={req.id} className="py-4">
          <Requirement
            name={req.name}
            description={req.description}
            templateName={req.template_name}
            download={() => guidelinesApi.downloadRequirementTemplate(req.id)}
          />
        </li>
      ))}
    </ul>
  );
}

/** One document: its name and what it is, and its Template beside it when RDCO set one. */
function Requirement({ name, description, templateName, download }: {
  name: string;
  description: string;
  templateName: string;
  download: () => Promise<{ data: Blob }>;
}) {
  return (
    <div role="group" aria-label={name} className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
      <div className="min-w-0 flex-1 basis-64 space-y-1">
        <h4 className="text-heading font-semibold text-stone-900">{name}</h4>
        {description && <PlainTextWithLinks text={description} className="text-small text-justified text-stone-700" />}
      </div>
      {templateName && (
        <div className="min-w-0 sm:max-w-[16rem] sm:pt-0.5">
          <TemplateDownload
            fileName={templateName}
            label={`Download the ${name} Template, ${templateName}`}
            download={download}
          />
        </div>
      )}
    </div>
  );
}

function AdvisersTemplates() {
  const headingId = useId();
  const searchId = useId();
  const read = useApiRead((signal) => guidelinesApi.advisersTemplates({ signal }).then((r) => r.data), []);
  const [query, setQuery] = useState("");
  const shared = read.status === "ready" && isSharedList(read.data) ? read.data : null;

  /* The server's order (by Adviser's name, then each Adviser's own order), grouped by Adviser. */
  const advisers = useMemo(() => {
    const groups = new Map<number, { id: number; name: string; templates: SharedTemplate[] }>();
    for (const t of shared ?? []) {
      const group = groups.get(t.shared_by.id) ?? { id: t.shared_by.id, name: t.shared_by.name, templates: [] };
      group.templates.push(t);
      groups.set(t.shared_by.id, group);
    }
    return [...groups.values()];
  }, [shared]);

  const wanted = query.trim().toLowerCase();
  const shown = wanted ? advisers.filter((a) => a.name.toLowerCase().includes(wanted)) : advisers;
  const searchable = read.status === "ready" && shared && advisers.length > 0;

  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-72">
          <h3 id={headingId} className="font-display text-title font-semibold text-stone-900">Advisers&apos; Templates</h3>
          <p className="mt-1 text-small text-stone-600">
            Proposal formats Advisers share from My Templates. Ask your Adviser which one to follow.
          </p>
        </div>
        {searchable && (
          <div className="w-full sm:w-72">
            <Input
              id={searchId}
              label="Search by Adviser"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Part of a name"
            />
          </div>
        )}
      </div>
      {read.status === "interrupted" ? (
        <InterruptedState what="Advisers' Templates" onRetry={read.retry} />
      ) : read.status === "failed" || (read.status === "ready" && !shared) ? (
        <LoadFailedAlert
          message={read.status === "failed"
            ? failureMessage(read.error, { lead: "Advisers' Templates didn't load." })
            : "Advisers' Templates didn't load: IRIS sent an answer this page can't read."}
          onRetry={read.retry}
        />
      ) : read.status === "loading" ? (
        <p role="status" className="flex items-center gap-2 text-small text-stone-600">
          <Spinner size="sm" />
          Loading Advisers&apos; Templates…
        </p>
      ) : advisers.length === 0 ? (
        <p className="text-small text-stone-600">No Adviser shares a Template yet.</p>
      ) : (
        <>
          <div aria-live="polite" className="sr-only">
            {wanted ? `${shown.length} ${shown.length === 1 ? "Adviser matches" : "Advisers match"}.` : ""}
          </div>
          {shown.length === 0 ? (
            <p className="text-small text-stone-600">
              No Adviser&apos;s name matches &ldquo;{query.trim()}&rdquo;.
            </p>
          ) : (
            <div className="divide-y divide-stone-200 border-y border-stone-200">
              {shown.map((adviser) => (
                <AdviserGroup key={adviser.id} name={adviser.name} templates={adviser.templates} />
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** One Adviser's shared Templates, under their name. */
function AdviserGroup({ name, templates }: { name: string; templates: SharedTemplate[] }) {
  return (
    <div className="space-y-3 py-4">
      <h4 className="text-heading font-semibold text-stone-900">{name}</h4>
      <ul aria-label={`${name}'s Templates`} className="space-y-3">
        {templates.map((t) => (
          <li key={t.id} className="flex flex-wrap items-start justify-between gap-x-6 gap-y-1">
            <div className="min-w-0 flex-1 basis-64 space-y-0.5">
              <h5 className="text-small font-semibold text-stone-800">{t.title}</h5>
              {t.description && <PlainTextWithLinks text={t.description} className="text-small text-justified text-stone-700" />}
            </div>
            <div className="min-w-0 sm:max-w-[16rem]">
              <TemplateDownload
                fileName={t.file_name}
                label={`Download ${t.title} by ${name}, ${t.file_name}`}
                download={() => guidelinesApi.downloadAdviserTemplate(t.id)}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
