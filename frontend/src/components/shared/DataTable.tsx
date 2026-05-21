/**
 * Generic paginated DataTable.
 * Wraps TanStack Table (react-table v8) for server-side pagination.
 * TODO: add column sorting support (pass sort state up via onSortChange prop).
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
  data:          T[];
  columns:       ColumnDef<T, unknown>[];
  loading?:      boolean;
  page:          number;
  pageSize:      number;
  totalCount:    number;
  onPageChange:  (page: number) => void;
}

export function DataTable<T>({
  data,
  columns,
  loading,
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

  return (
    <div className="flex flex-col">
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead className="bg-gray-50 border-b border-gray-200">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="text-left px-4 py-3 font-semibold text-gray-600 whitespace-nowrap"
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
                    <Spinner />
                  </div>
                </td>
              </tr>
            ) : table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="py-12 text-center text-gray-400 text-[13px]">
                  No records found.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-b border-gray-100 hover:bg-gray-50">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 text-gray-700">
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
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 text-[12px] text-gray-500">
          <span>{start}-{end} of {totalCount}</span>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              <i className="fa fa-chevron-left text-[11px]" />
            </Button>
            <span className="px-2 py-1 font-medium text-gray-700">{page} / {totalPages}</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              <i className="fa fa-chevron-right text-[11px]" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
