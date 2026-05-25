/** Shimmer placeholder while waiting for RAG response (FR-M3-01). */
export function AssistantMessageSkeleton() {
  return (
    <div className="flex gap-3 max-w-[88%] animate-pulse" aria-busy="true" aria-label="IRIS is responding">
      <div className="w-8 h-8 rounded-full bg-[#6B0F12]/10 shrink-0" />
      <div className="flex-1 space-y-2.5 pt-1 bg-white border border-stone-200/80 rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="h-3 bg-stone-200 rounded-full w-[92%]" />
        <div className="h-3 bg-stone-200 rounded-full w-[78%]" />
        <div className="h-3 bg-stone-200 rounded-full w-[65%]" />
        <div className="h-3 bg-stone-100 rounded-full w-[40%] mt-3" />
      </div>
    </div>
  );
}
