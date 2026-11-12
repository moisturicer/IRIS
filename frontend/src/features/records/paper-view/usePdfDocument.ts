import { useCallback, useEffect, useRef, useState } from "react";
import { recordsApi } from "@/api/records";
import { loadPdfDocument, type PdfPage } from "@/lib/pdf";

/** How many pages the background loader asks pdf.js for at once, and per re-render. */
const PAGE_CHUNK = 8;

interface PdfDocumentOptions {
  recordId: number;
  /** An earlier version (IR-416), or null for the current paper. */
  version: number | null;
  /** Bumped by "Try again": loads the same paper afresh. */
  attempt: number;
  /**
   * The page to have first: a citation's, or null for page 1. Read when a
   * load starts, not a reason to load again.
   */
  firstPage: number | null;
}

export interface PdfDocumentState {
  status: "loading" | "ready" | "error";
  /** The paper's page count once open; 0 before. */
  pageCount: number;
  /**
   * Each page as pdf.js has it, by index, or `undefined` while it is still
   * loading. The first page asked for is always present once ready.
   */
  pages: (PdfPage | undefined)[];
  /**
   * A page, loading it if need be, without making the reader re-render: what
   * find reads text through. Shares one request per page with the loader.
   */
  pageProxy: (pageNumber: number) => Promise<PdfPage>;
  /** Loads a page out of turn and shows it: one a citation or a find is landing on. */
  prioritize: (pageNumber: number) => void;
  /**
   * The Manuscript revision the server said these bytes are (`X-Manuscript-Revision`),
   * or null when it named none. A highlight sends it back, so the server can
   * refuse one made on a paper that has since been replaced (IR-583).
   */
  revision: string | null;
}

/** One opened document's page requests, so each page is asked of pdf.js once. */
interface Source {
  request: (pageNumber: number) => Promise<PdfPage>;
  pageCount: number;
}

/**
 * The paper the reader shows (IR-565): fetched, opened, and its pages loaded
 * with the useful one first.
 *
 * The reader is ready as soon as the page it opens at -- a citation's, or the
 * first -- has loaded; the rest follow in the background, `PAGE_CHUNK` at a
 * time, so a 120-page thesis is readable without waiting for page 120.
 *
 * A change of record, version or attempt aborts the fetch, stops the loader,
 * and releases the document it had opened, exactly once. Nothing is kept
 * between loads: the bytes and the document live only as long as this load,
 * so there is no reuse to bound or to leak across accounts.
 */
export function usePdfDocument({ recordId, version, attempt, firstPage }: PdfDocumentOptions) {
  const [status, setStatus] = useState<PdfDocumentState["status"]>("loading");
  const [pages, setPages] = useState<(PdfPage | undefined)[]>([]);
  const [source, setSource] = useState<Source | null>(null);
  const [revision, setRevision] = useState<string | null>(null);
  const sourceRef = useRef(source);
  sourceRef.current = source;
  const firstPageRef = useRef(firstPage);
  firstPageRef.current = firstPage;

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    let dispose: (() => void) | null = null;
    setStatus("loading");
    setPages([]);
    setSource(null);
    setRevision(null);

    (async () => {
      try {
        const options = { signal: controller.signal };
        const { data, headers } = version == null
          ? await recordsApi.manuscriptBlob(recordId, options)
          : await recordsApi.versionManuscriptBlob(recordId, version, options);
        if (cancelled) return;
        // The identity of these bytes, named by the server (IR-583). Only the
        // current paper's response carries one.
        setRevision((headers?.["x-manuscript-revision"] as string | undefined) ?? null);
        const buffer = await data.arrayBuffer();
        if (cancelled) return;
        const { document: doc, destroy } = await loadPdfDocument(buffer, controller.signal);
        let disposed = false;
        dispose = () => {
          if (disposed) return;
          disposed = true;
          void destroy();
        };
        if (cancelled) {
          dispose();
          return;
        }

        const requested = new Map<number, Promise<PdfPage>>();
        const request = (pageNumber: number) => {
          let page = requested.get(pageNumber);
          if (!page) {
            page = doc.getPage(pageNumber);
            requested.set(pageNumber, page);
          }
          return page;
        };
        const pageCount = doc.numPages;
        const first = Math.min(pageCount, Math.max(1, firstPageRef.current ?? 1));
        const opening = await request(first);
        if (cancelled) return;

        const initial: (PdfPage | undefined)[] = new Array(pageCount).fill(undefined);
        initial[first - 1] = opening;
        setPages(initial);
        setSource({ request, pageCount });
        setStatus("ready");

        const rest = Array.from({ length: pageCount }, (_, i) => i + 1).filter((n) => n !== first);
        for (let i = 0; i < rest.length; i += PAGE_CHUNK) {
          const chunk = rest.slice(i, i + PAGE_CHUNK);
          // A page pdf.js cannot load stays an empty box of the estimated size.
          const loaded = await Promise.all(chunk.map((n) => request(n).catch(() => undefined)));
          if (cancelled) return;
          setPages((previous) => {
            const next = [...previous];
            chunk.forEach((n, j) => {
              next[n - 1] ??= loaded[j];
            });
            return next;
          });
        }
      } catch {
        dispose?.();
        if (!cancelled) setStatus("error");
      }
    })();

    return () => {
      cancelled = true;
      sourceRef.current = null;
      controller.abort();
      dispose?.();
    };
  }, [recordId, version, attempt]);

  const pageProxy = useCallback(
    (pageNumber: number) =>
      source ? source.request(pageNumber) : Promise.reject(new Error("The paper is not open")),
    [source],
  );

  const prioritize = useCallback(
    (pageNumber: number) => {
      if (!source || pageNumber < 1 || pageNumber > source.pageCount) return;
      source.request(pageNumber).then(
        (page) => {
          // Only into the document it came from: a later load starts afresh.
          if (sourceRef.current !== source) return;
          setPages((previous) => {
            if (previous[pageNumber - 1]) return previous;
            const next = [...previous];
            next[pageNumber - 1] = page;
            return next;
          });
        },
        () => {
          /* stays an empty box; the loader's own pass will not fare better */
        },
      );
    },
    [source],
  );

  return {
    status,
    pageCount: source?.pageCount ?? 0,
    pages,
    pageProxy,
    prioritize,
    revision,
  } satisfies PdfDocumentState;
}
