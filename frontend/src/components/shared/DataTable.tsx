/**
 * Generic paginated DataTable.
 * Wraps TanStack Table (react-table v8) for server-side pagination.
 */
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import { Spinner } from "@/components/ui/Spinner";
import { Button }  from "@/components/ui/Button";

interface DataTableProps<T> {
  caption:       string;
  data:          T[];
  columns:       ColumnDef<T, unknown>[];
  loading?:      boolean;
  /** Reads again; a load that runs past 10 s offers it as Try again (IR-1078). */
  onRetry?:      () => void;
  page:          number;
  pageSize:      number;
  totalCount:    number;
  onPageChange:  (page: number) => void;
}

export function DataTable<T>({
  caption,
  data,
  columns,
  loading,
  onRetry,
  page,
  pageSize,
  totalCount,
  onPageChange,
}: DataTableProps<T>) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    // Server-side -- disable internal pagination
    manualPagination: true,
    pageCount: Math.ceil(totalCount / pageSize),
  });

  const totalPages = Math.ceil(totalCount / pageSize);
  const start      = totalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const end        = Math.min(page * pageSize, totalCount);
  const status = loading
    ? `Loading ${caption}.`
    : totalCount === 0
      ? `${caption} has no results.`
      : `${caption}: showing ${start}–${end} of ${totalCount}. Page ${page} of ${totalPages}.`;

  return (
    <div className="flex flex-col">
      <p
        role="status"
        aria-live="polite"
        aria-atomic="true"
        aria-label={`${caption} status`}
        className="sr-only"
      >
        {status}
      </p>

      <div className="relative overflow-x-auto">
        <table className="w-full text-body">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-stone-50 border-b border-stone-200">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    scope="col"
                    className="text-left px-4 py-3 font-semibold text-stone-600 whitespace-nowrap"
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center">
                  <div className="flex justify-center">
                    <Spinner onRetry={onRetry} />
                  </div>
                </td>
              </tr>
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center text-stone-500 text-body">
                  No records found.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-b border-stone-100 hover:bg-stone-50">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 text-stone-700">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination bar */}
      {totalCount > 0 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-stone-200 text-small text-stone-500">
          <span>{start}-{end} of {totalCount}</span>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              aria-label="Previous page"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              <i className="fa fa-chevron-left text-label" aria-hidden />
            </Button>
            <span className="px-2 py-1 font-medium text-stone-700">{page} / {totalPages}</span>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Next page"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              <i className="fa fa-chevron-right text-label" aria-hidden />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
