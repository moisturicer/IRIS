import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { describeFailure } from "@/features/publish/draft";

/** Choose a continuation type, then edit the ordinary child draft in Publish. */
export function ContinueProposal({ recordId }: { recordId: number }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function continueAs(name: string) {
    setBusy(true);
    setError(null);
    try {
      const { data: types } = await recordsApi.recordTypes();
      const type = types.results.find((item) => item.name === name);
      if (!type) throw new Error("Continuation type unavailable");
      const { data: child } = await recordsApi.continueAs(recordId, type.id);
      navigate(`/?publish=${child.id}`);
    } catch (failure) {
      setError(describeFailure(failure, "Could not continue this proposal. Try again.").message);
      setBusy(false);
    }
  }

  return <div className="flex flex-wrap items-center gap-2" aria-busy={busy}>
    {[["Thesis", "Thesis / Research"], ["Project", "Project"]].map(([label, name]) => (
      <button key={name} type="button" disabled={busy}
        className={cn(PILL_SECONDARY, FOCUS_RING)} onClick={() => void continueAs(name)}>
        Continue as {label}
      </button>
    ))}
    {busy && <span role="status">Creating your draft…</span>}
    {error && <p role="alert" className="text-small text-brand">{error}</p>}
  </div>;
}
