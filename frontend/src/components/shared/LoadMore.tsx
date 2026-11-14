import { Button } from "@/components/ui/Button";

interface LoadMoreProps {
  /** The server has another page. */
  hasMore: boolean;
  /** The last attempt to read the next page failed; shown above the button. */
  error: string | null;
  loading: boolean;
  onLoadMore: () => void;
  /** Spacing and borders from the screen the control sits in. */
  className?: string;
}

/**
 * The "Load more" control under a paged list (IR-1100). Shows only while the
 * server has another page, or while the last attempt to read one is still
 * waiting for a retry, so a queue of 20 rows or fewer never shows a button.
 */
export function LoadMore({ hasMore, error, loading, onLoadMore, className = "" }: LoadMoreProps) {
  if (!hasMore && !error) return null;
  return (
    <div className={`flex flex-col items-center gap-2 ${className}`}>
      {error && <p role="alert" className="text-small text-stone-700">{error}</p>}
      <Button type="button" variant="outline" size="sm" onClick={onLoadMore} loading={loading}>
        Load more
      </Button>
    </div>
  );
}
