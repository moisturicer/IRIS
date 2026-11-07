import type { AxiosResponse } from "axios";
import { useCallback, useEffect, useRef, useState } from "react";

import { peopleApi } from "@/api/people";
import { isRequestTimeout } from "@/api/requestPolicy";
import { errorDetail } from "@/lib/errorDetail";
import type { Collaborator, ProfilePage, ProfilePaper, PublicProfile } from "@/types/people";

/** One paged list on the Profile and what the reader has done with it. */
export interface ListState<T> {
  items:       T[];
  /** The last page loaded; `0` while the first has not. */
  page:        number;
  hasMore:     boolean;
  loadingMore: boolean;
  /** Why the last attempt failed. With no items it is the first page that failed. */
  error:       string | null;
}

export interface PersonProfileModel {
  profile:       PublicProfile;
  research:      ListState<ProfilePaper>;
  advised:       ListState<ProfilePaper>;
  collaborators: ListState<Collaborator>;
}

export type ListKey = "research" | "advised" | "collaborators";

export type PersonProfileState =
  | { kind: "loading" }
  /** Missing, suspended, inactive, unapproved or a System Admin: one answer, never which. */
  | { kind: "not_found" }
  | { kind: "failed"; message: string; interrupted: boolean }
  | { kind: "ready"; model: PersonProfileModel };

function firstPage<T>(result: PromiseSettledResult<AxiosResponse<ProfilePage<T>>>): ListState<T> {
  if (result.status === "fulfilled") {
    const { results, next } = result.value.data;
    return { items: results, page: 1, hasMore: next !== null, loadingMore: false, error: null };
  }
  return {
    items: [], page: 0, hasMore: false, loadingMore: false,
    error: errorDetail(result.reason, "This couldn't load. Try again."),
  };
}

const isNotFound = (error: unknown) =>
  (error as { response?: { status?: number } }).response?.status === 404;

/**
 * Another person's Profile: the person first, then the first page of each list,
 * all at once. A list that fails keeps its place and says so, with its own
 * retry, so one failed section never hides the rest. Showing more asks for the
 * next page of one list. Everything is fenced by the person it was asked for,
 * so moving from one Profile to another can never mix them.
 */
export function usePersonProfile(id: number) {
  const [state, setState] = useState<PersonProfileState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  const latest = useRef(state);
  latest.current = state;

  useEffect(() => {
    const current = ++generation.current;
    setState({ kind: "loading" });
    Promise.allSettled([
      peopleApi.get(id),
      peopleApi.research(id, 1),
      peopleApi.advised(id, 1),
      peopleApi.collaborators(id, 1),
    ]).then(([person, research, advised, collaborators]) => {
      if (current !== generation.current) return;
      if (person.status === "rejected") {
        setState(isNotFound(person.reason)
          ? { kind: "not_found" }
          : {
              kind: "failed",
              interrupted: isRequestTimeout(person.reason),
              message: errorDetail(person.reason, "Check your connection, then try again."),
            });
        return;
      }
      setState({
        kind: "ready",
        model: {
          profile: person.value.data,
          research: firstPage(research),
          advised: firstPage(advised),
          collaborators: firstPage(collaborators),
        },
      });
    });
  }, [id, attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  /** The next page of one list, or its first when that one failed. */
  const more = useCallback((key: ListKey) => {
    const now = latest.current;
    if (now.kind !== "ready") return;
    const current = generation.current;
    const list = now.model[key] as ListState<{ id: number }>;
    if (list.loadingMore) return;
    const page = list.page + 1;

    const patch = (change: (l: ListState<{ id: number }>) => ListState<{ id: number }>) =>
      setState((s) => (s.kind === "ready" && current === generation.current
        ? { kind: "ready", model: { ...s.model, [key]: change(s.model[key] as ListState<{ id: number }>) } as PersonProfileModel }
        : s));

    patch((l) => ({ ...l, loadingMore: true, error: null }));
    const fetch: Promise<AxiosResponse<ProfilePage<{ id: number }>>> = peopleApi[key](id, page);
    fetch.then(({ data }) => {
      patch((l) => {
        const seen = new Set(l.items.map((item) => item.id));
        return {
          items: [...l.items, ...data.results.filter((item) => !seen.has(item.id))],
          page, hasMore: data.next !== null, loadingMore: false, error: null,
        };
      });
    }).catch((error: unknown) => {
      patch((l) => ({ ...l, loadingMore: false, error: errorDetail(error, "More didn't load. Try again.") }));
    });
  }, [id]);

  return { state, retry, more };
}
