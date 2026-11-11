/**
 * The paper's Contact person on Paper View (ADR-051 decision 27, IR-803).
 *
 * Any owner names another owner of the paper its Contact person, who gets the
 * review emails from then on (IR-801's `contact-person/`). The card comes from
 * `capabilities`, so it compares no role names.
 *
 * Choosing an owner doesn't save: a separate button does. Arrowing through a
 * closed native select fires a change on some platforms, and every save tells
 * two people in-app, so one keypress must not send one.
 */
import { useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { capabilitiesFor } from "@/features/records/capabilities";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import type { RecordDetail, RecordOwner } from "@/types/records";

import { RailHeading } from "./headings";

/**
 * What the choice decides. Only the emails for now: ADR-051 decision 27 also
 * shares this person's email on a Discoverable Proposal, which isn't built
 * (IR-421), so the screen doesn't say it yet.
 */
const PURPOSE = "This person gets the review emails.";
const SAVE_FAILED = "The Contact person couldn't be changed. Try again.";

/** An owner's name as the paper shows it, or their email when they gave none. */
function nameOf(owner: RecordOwner): string {
  return owner.full_name.trim() || owner.email;
}

interface ContactPersonCardProps {
  record: Pick<RecordDetail, "id" | "owners" | "capabilities">;
  /** After a change: the owners' order and the record's offers are read again. */
  onChanged: () => void;
}

export function ContactPersonCard({ record, onChanged }: ContactPersonCardProps) {
  const headingId = useId();
  const current = record.owners.find((owner) => owner.is_primary) ?? null;
  const currentId = current?.user ?? null;
  // Who can be chosen: a closed account can't (IR-801 refuses it), unless it
  // already holds the role, so the dropdown still shows who has it.
  const choices = record.owners.filter((owner) => owner.is_primary || !owner.account_closed);
  const [chosen, setChosen] = useState<number | null>(currentId);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The paper read again, after a save here or another owner's elsewhere.
  useEffect(() => setChosen(currentId), [currentId]);

  if (!capabilitiesFor(record).has("change_contact_person")) return null;

  const save = async () => {
    const target = choices.find((owner) => owner.user === chosen);
    if (!target) return;
    setSaving(true);
    setNotice(null);
    setError(null);
    try {
      await recordsApi.changeContactPerson(record.id, target.user);
      setNotice(`${nameOf(target)} is now the Contact person.`);
      onChanged();
    } catch (err) {
      setError(fieldError(err, "owner") ?? errorDetail(err, SAVE_FAILED));
      setChosen(currentId);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      aria-labelledby={headingId}
      className="bg-white ring-1 ring-stone-200 rounded-2xl p-5 shadow-card space-y-3"
    >
      <RailHeading id={headingId}>Contact person</RailHeading>
      {choices.length < 2 ? (
        <div>
          {current && <p className="text-sm font-bold text-stone-900 [overflow-wrap:anywhere]">{nameOf(current)}</p>}
          <p className="mt-1 text-xs text-stone-600">{PURPOSE}</p>
        </div>
      ) : (
        <>
          <Select
            label="Contact person"
            hint={PURPOSE}
            size="lg"
            // A native select is as wide as its longest option; a long name
            // must not push the rail past a phone's width (IR-921).
            className="min-w-0 max-w-full"
            value={chosen ?? ""}
            onChange={(event) => {
              setChosen(Number(event.target.value));
              setNotice(null);
              setError(null);
            }}
          >
            {choices.map((owner) => (
              <option key={owner.user} value={owner.user}>
                {nameOf(owner)}
              </option>
            ))}
          </Select>
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            loading={saving}
            disabled={chosen === null || chosen === currentId}
            onClick={() => void save()}
          >
            Make Contact person
          </Button>
        </>
      )}
      {error && (
        <p role="alert" className="text-small text-brand">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-xs text-stone-700">
          {notice}
        </p>
      )}
    </section>
  );
}
