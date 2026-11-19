import { useEffect, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import {
  firstPageSession,
  knownFirstPage,
  rememberFirstPage,
  rememberNoFirstPage,
} from "@/lib/firstPages";

interface PaperThumbnailProps {
  recordId: number;
  /** Whether the record has a manuscript to draw. Without one the outline stays. */
  available: boolean;
}

/**
 * The 96 px page beside a one-column result (IR-1082, D4; spec §4.6), showing the
 * paper's real first page (IR-1141). Until that arrives, and wherever there is
 * none, the drawn page outline stands in, so a row is the same size either way.
 *
 * The page is a small image the server draws (IR-1241), never the whole
 * manuscript, and it writes no audit event. It is asked for only once the row
 * nears the viewport, and kept for the session (`lib/firstPages`), so going
 * back to Discover asks again only for pages still being drawn. Decoration
 * only, so a screen reader skips it. Phones drop it, as the prototype does, to
 * give the title the width.
 */
export function PaperThumbnail({ recordId, available }: PaperThumbnailProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [src, setSrc] = useState<string | null>(() => (available ? knownFirstPage(recordId) ?? null : null));

  useEffect(() => {
    if (!available || !hostRef.current) return;
    if (!("IntersectionObserver" in window)) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "300px" });
    observer.observe(hostRef.current);
    return () => observer.disconnect();
  }, [available]);

  useEffect(() => {
    if (!available) {
      setSrc(null);
      return;
    }
    const known = knownFirstPage(recordId);
    setSrc(known ?? null);
    if (!visible || known !== undefined) return;

    const controller = new AbortController();
    const session = firstPageSession();
    recordsApi.firstPage(recordId, { signal: controller.signal }).then(
      ({ status, data }) => {
        // 202: a worker is still drawing it. The outline stays, and the next
        // time this row appears it asks again.
        if (controller.signal.aborted || status !== 200 || !data.type.startsWith("image/")) return;
        setSrc(rememberFirstPage(recordId, data, session) ?? null);
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        // 404: no manuscript, or one that can't be drawn. Not asked again this
        // session. Anything else (offline, a timeout) is not remembered.
        if ((error as { response?: { status?: number } })?.response?.status === 404) {
          rememberNoFirstPage(recordId, session);
        }
      },
    );
    return () => controller.abort();
  }, [available, recordId, visible]);

  return (
    <div
      ref={hostRef}
      aria-hidden="true"
      className="relative hidden aspect-[3/4] w-24 shrink-0 overflow-hidden rounded-control border border-stone-200 bg-surface shadow-card sm:block"
    >
      <div className="grid content-start gap-[5px] px-2 py-2.5">
        <span className="mx-auto mb-0.5 h-3.5 w-3.5 rounded-full border-2 border-stone-300" />
        <i className="mx-auto mb-1.5 mt-1 block h-[5px] w-4/5 rounded-full bg-stone-300" />
        {["w-full", "w-full", "w-3/5", "w-full", "w-full", "w-3/5"].map((width, index) => (
          <i key={index} className={`block h-[3px] rounded-full bg-stone-200 ${width}`} />
        ))}
      </div>
      {src && (
        <img
          src={src}
          alt=""
          className="absolute inset-0 h-full w-full bg-white object-cover object-top"
        />
      )}
    </div>
  );
}
