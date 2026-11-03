import { Link } from "react-router-dom";
import { EntryFrame, EntryTab } from "@/components/auth/EntryFrame";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

/** Public help for visitors who cannot open the signed-in Help page yet. */
export default function EntryHelpPage() {
  return (
    <EntryFrame tabs={<EntryTab>Help</EntryTab>}>
      <h2 className="font-display text-display font-semibold text-stone-900">Getting into IRIS</h2>
      <p className="mt-2 text-body text-stone-700">
        Use your institutional email to register. Check that inbox for the verification link,
        then sign in to see the status of your request.
      </p>
      <p className="mt-section text-body text-stone-700">
        If you cannot remember your password, request a reset link.
      </p>
      <div className="mt-section flex flex-wrap gap-x-6 gap-y-2 text-small font-semibold">
        <Link to="/password/forgot" className={cn("inline-flex min-h-11 items-center rounded text-brand hover:underline", FOCUS_RING)}>
          Reset password
        </Link>
        <Link to="/login" className={cn("inline-flex min-h-11 items-center rounded text-brand hover:underline", FOCUS_RING)}>
          Return to sign in
        </Link>
      </div>
    </EntryFrame>
  );
}
