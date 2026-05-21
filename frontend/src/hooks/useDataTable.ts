import { useState } from "react";

interface DataTableState {
  page:         number;
  pageSize:     number;
  search:       string;
  ordering:     string;
  setPage:      (page: number) => void;
  setPageSize:  (size: number) => void;
  setSearch:    (q: string)    => void;
  setOrdering:  (o: string)    => void;
  queryParams:  Record<string, unknown>;
}

/**
 * Shared server-side pagination + search state for DataTable components.
 * Pass queryParams directly to your API call.
 */
export function useDataTable(defaultOrdering = "-created_at"): DataTableState {
  const [page,     setPage]     = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search,   setSearch]   = useState("");
  const [ordering, setOrdering] = useState(defaultOrdering);

  return {
    page, pageSize, search, ordering,
    setPage, setPageSize, setSearch, setOrdering,
    queryParams: { page, page_size: pageSize, search, ordering },
  };
}
