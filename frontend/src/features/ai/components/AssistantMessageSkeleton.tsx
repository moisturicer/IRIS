import { SynthesisIcon } from "./AskIrisIcons";

/** Placeholder while a grounded answer is being retrieved (FR-M3-01). */
export function AssistantMessageSkeleton() {
  return (
    <div className="flex gap-3 max-w-[88%]" aria-busy="true" aria-label="IRIS is searching the repository">
      <div className="w-8 h-8 rounded-full bg-brand/10 text-brand shrink-0 flex items-center justify-center">
        <SynthesisIcon className="w-[18px] h-[18px]" spinning />
      </div>
      <div className="flex-1 bg-white border border-stone-200/80 rounded-2xl rounded-bl-sm px-4 py-3">
        <p className="text-[12px] font-medium text-stone-500 mb-2.5">
          Searching the CIT-U repository…
        </p>
        <div className="space-y-2.5 animate-pulse motion-reduce:animate-none">
          <div className="h-3 bg-stone-200 rounded-full w-[92%]" />
          <div className="h-3 bg-stone-200 rounded-full w-[78%]" />
          <div className="h-3 bg-stone-100 rounded-full w-[55%]" />
        </div>
      </div>
    </div>
  );
}
