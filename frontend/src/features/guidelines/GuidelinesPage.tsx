/**
 * Guidelines (ADR-063 decision 7, IR-974): what each record type needs, and the
 * Templates to follow, for everyone signed in.
 *
 * One section per record type, stacked so a reader sees all three and can find
 * a document anywhere on the page: the type's description, the Manuscript (the
 * fixed first requirement), then the requirements RDCO lists on Setup, in
 * RDCO's order. The Proposal section also lists Advisers' Templates (My
 * Templates, IR-975), with a search by Adviser. Labels inform and never block.
 *
 * It only reads and downloads. What shows is the server's: a hidden requirement,
 * or a suspended or former Adviser's Templates, never reach this page.
 */
import { useEffect, useId, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  guidelinesApi, type GuidelineRecordType, type GuidelineRequirement, type SharedTemplate,
} from "@/api/guidelines";
import { PageHeader } from "@/components/layout/PageHeader";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { PlainTextWithLinks } from "@/components/shared/PlainTextWithLinks";
import { Input } from "@/components/ui/Input";
import { Spinner } from "@/components/ui/Spinner";
import { useApiRead } from "@/hooks/useApiRead";
import { failureMessage } from "@/lib/readFailure";
import { RequirementLabel } from "@/features/setup/RequirementLabel";
import { isGuidelines, isSharedList } from "./requirementGuide";
import { sectionId } from "./sectionId";
import { TemplateDownload } from "./TemplateDownload";

/** The record type whose section lists Advisers' Templates (`RecordTypeName.PROPOSAL`). */
const PROPOSAL = "Proposal";

/** Only a list of record types is usable; anything else is a failed read (CODING_STANDARDS F1). */
export default function GuidelinesPage() {
  const read = useApiRead((signal) => guidelinesApi.list({ signal }).then((r) => r.data), []);
  const types = read.status === "ready" && isGuidelines(read.data) ? read.data : null;
  const { hash } = useLocation();

  // The browser jumps to `#thesis-research` before the sections exist (they
  // arrive with the read), so jump once they do: Publish links straight here.
  useEffect(() => {
    if (!hash || !types) return;
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView?.();
  }, [hash, types]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Guidelines"
        description="What each record type needs, and the Templates to follow. Only the manuscript is needed to submit: Required and Optional tell you what RDCO expects, and an office asks for anything it needs later."
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
      ) : !types ? (
        <LoadFailedAlert
          message="The guidelines didn't load: IRIS sent an answer this page can't read."
          onRetry={read.retry}
        />
      ) : (
        <>
          <nav aria-label="Record types" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
            <span className="text-stone-600">Jump to</span>
            {types.map((rt) => (
              <a key={rt.id} href={`#${sectionId(rt.name)}`}
                 className="font-medium text-brand underline underline-offset-2">
                {rt.name}
              </a>
            ))}
          </nav>
          {types.map((rt) => <RecordTypeSection key={rt.id} recordType={rt} />)}
        </>
      )}
    </div>
  );
}

function RecordTypeSection({ recordType }: { recordType: GuidelineRecordType }) {
  const headingId = useId();
  const { name, description, manuscript, requirements } = recordType;

  return (
    <section id={sectionId(name)} aria-labelledby={headingId}
             className="scroll-mt-6 space-y-4 rounded-card border border-stone-200 bg-white p-5">
      <h2 id={headingId} className="text-heading font-semibold text-stone-900">{name}</h2>
      {description && <PlainTextWithLinks text={description} className="text-body text-stone-700" />}
      <ul aria-label={`${name} requirements`} className="divide-y divide-stone-100">
        <li className="py-3 first:pt-0">
          <RequirementRow
            name="Manuscript"
            required
            description={manuscript.description}
            templateName={manuscript.template_name}
            download={() => guidelinesApi.downloadManuscriptTemplate(recordType.id)}
          />
        </li>
        {requirements.map((req: GuidelineRequirement) => (
          <li key={req.id} className="py-3 last:pb-0">
            <RequirementRow
              name={req.name}
              required={req.is_required}
              description={req.description}
              templateName={req.template_name}
              download={() => guidelinesApi.downloadRequirementTemplate(req.id)}
            />
          </li>
        ))}
      </ul>
      {name === PROPOSAL && <AdvisersTemplates />}
    </section>
  );
}

function RequirementRow({ name, required, description, templateName, download }: {
  name: string;
  required: boolean;
  description: string;
  templateName: string;
  download: () => Promise<{ data: Blob }>;
}) {
  return (
    <div role="group" aria-label={name} className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-small font-semibold text-stone-900">{name}</h3>
        <RequirementLabel required={required} />
      </div>
      {description && <PlainTextWithLinks text={description} className="text-small text-stone-700" />}
      {templateName && (
        <TemplateDownload
          fileName={templateName}
          label={`Download the ${name} Template, ${templateName}`}
          download={download}
        />
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

  return (
    <section aria-labelledby={headingId} className="space-y-3 border-t border-stone-200 pt-4">
      <div>
        <h3 id={headingId} className="text-body font-semibold text-stone-900">Advisers&apos; Templates</h3>
        <p className="text-small text-stone-600">
          Proposal formats Advisers share from My Templates. Ask your Adviser which one to follow.
        </p>
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
          <div className="max-w-sm">
            <Input
              id={searchId}
              label="Search by Adviser"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Part of a name"
            />
          </div>
          <div aria-live="polite" className="sr-only">
            {wanted ? `${shown.length} ${shown.length === 1 ? "Adviser matches" : "Advisers match"}.` : ""}
          </div>
          {shown.length === 0 ? (
            <p className="text-small text-stone-600">No Adviser&apos;s name matches &ldquo;{query.trim()}&rdquo;.</p>
          ) : (
            <div className="space-y-4">
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

function AdviserGroup({ name, templates }: { name: string; templates: SharedTemplate[] }) {
  return (
    <div className="space-y-2">
      <h4 className="text-small font-semibold text-stone-900">{name}</h4>
      <ul aria-label={`${name}'s Templates`} className="space-y-3">
        {templates.map((t) => (
          <li key={t.id} className="space-y-1 rounded-card bg-stone-50 px-3 py-2">
            <h5 className="text-small font-medium text-stone-900">{t.title}</h5>
            {t.description && <PlainTextWithLinks text={t.description} className="text-small text-stone-700" />}
            <TemplateDownload
              fileName={t.file_name}
              label={`Download ${t.title} by ${name}, ${t.file_name}`}
              download={() => guidelinesApi.downloadAdviserTemplate(t.id)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
