import { useId, useState } from "react";
import { Link } from "react-router-dom";

import { CHECKBOX } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";

import { TOUR_PAGES } from "./studentTours";
import { saveToursOff, TOURS_OFF_LABEL } from "./toursOff";

/**
 * Settings › Help's "Guided tours" (IR-1342, AC 5): the one place a student
 * takes a tour again. Each link opens its page with `?tour=<key>`, which
 * starts the tour whether or not it was seen. Pages have no tour button.
 *
 * Its first row is "Don't show tours again" (IR-1349), the same account
 * setting as the tickbox on each tour's card, saved as soon as it changes.
 */
export function GuidedToursHelp() {
  const off = useAuthStore((s) => s.user?.tours_off === true);
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState("");
  const helpId = useId();

  const change = async (next: boolean) => {
    setSaving(true);
    setSaid("");
    const saved = await saveToursOff(next);
    setSaving(false);
    setSaid(!saved
      ? `Could not save ${TOURS_OFF_LABEL}. Try again.`
      : next
        ? "Saved. Tours won't start by themselves."
        : "Saved. Tours start again on the pages you haven't toured.");
  };

  return (
    <>
      <p>
        The first time you open each of these, a short tour shows what it is for and how to use it.
        Take any of them again here.
      </p>
      <div className="mt-3">
        <label className="flex min-h-11 cursor-pointer items-center gap-2.5 font-semibold text-stone-900">
          <input type="checkbox" checked={off} disabled={saving} aria-describedby={helpId}
            onChange={(event) => void change(event.target.checked)}
            className={cn(CHECKBOX, "shrink-0", FOCUS_RING)} />
          {TOURS_OFF_LABEL}
        </label>
        <p id={helpId} className="ml-[1.625rem] text-small text-stone-600">
          Ticked, no tour starts by itself when you open a page. The links below work either way.
        </p>
        {/* A div, not a p: Help spaces consecutive paragraphs apart. */}
        <div role="status" className="ml-[1.625rem] min-h-5 text-small text-stone-600">{said}</div>
      </div>
      <ul>
        {TOUR_PAGES.map(({ key, page, href }) => (
          <li key={key}>
            <strong className="font-semibold text-stone-900">{page}</strong>{" "}
            <Link to={href} className="font-medium text-brand underline underline-offset-2">
              Take the tour{" "}<span className="sr-only">of {page}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
