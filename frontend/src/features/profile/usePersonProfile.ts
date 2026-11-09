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
  loading:     boolean;
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
    return { items: results, page: 1, hasMore: next !== null, loading: false, loadingMore: false, error: null };
  }
  return {
    items: [], page: 0, hasMore: false, loading: false, loadingMore: false,
    error: errorDetail(result.reason, "This couldn't load. Try again."),
  };
}

type IdList = ListState<{ id: number }>;
type ListPatch = (change: (list: IdList) => IdList) => void;

/** Shared paging and retry behavior for a Profile list. */
function loadMoreProfileList(id: number, key: ListKey, list: IdList, patch: ListPatch) {
  const page = list.page + 1;
  patch((value) => ({ ...value, loadingMore: true, error: null }));
  const fetch: Promise<AxiosResponse<ProfilePage<{ id: number }>>> = peopleApi[key](id, page);
  fetch.then(({ data }) => {
    patch((value) => {
      const seen = new Set(value.items.map((item) => item.id));
      return {
        items: [...value.items, ...data.results.filter((item) => !seen.has(item.id))],
        page, hasMore: data.next !== null, loading: false, loadingMore: false, error: null,
      };
    });
  }).catch((error: unknown) => {
    patch((value) => ({ ...value, loadingMore: false, error: errorDetail(error, "More didn't load. Try again.") }));
  });
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
    const list = now.model[key] as IdList;
    if (list.loadingMore) return;

    const patch: ListPatch = (change) =>
      setState((s) => (s.kind === "ready" && current === generation.current
        ? { kind: "ready", model: { ...s.model, [key]: change(s.model[key] as IdList) } as PersonProfileModel }
        : s));
    loadMoreProfileList(id, key, list, patch);
  }, [id]);

  return { state, retry, more };
}

/** The signed-in person's three lists, without requesting their public-profile header again. */
export function useOwnProfileLists(id: number | null) {
  const [lists, setLists] = useState(() => pendingLists());
  const generation = useRef(0);
  const latest = useRef(lists);
  latest.current = lists;

  useEffect(() => {
    const current = ++generation.current;
    if (id === null) {
      setLists(pendingLists(false));
      return () => { generation.current += 1; };
    }

    setLists(pendingLists());
    Promise.allSettled([
      peopleApi.research(id, 1),
      peopleApi.advised(id, 1),
      peopleApi.collaborators(id, 1),
    ]).then(([research, advised, collaborators]) => {
      if (current !== generation.current) return;
      setLists({
        research: firstPage(research),
        advised: firstPage(advised),
        collaborators: firstPage(collaborators),
      });
    });
    return () => { generation.current += 1; };
  }, [id]);

  const more = useCallback((key: ListKey) => {
    if (id === null) return;
    const now = latest.current;
    const list = now[key] as IdList;
    if (list.loadingMore) return;
    const current = generation.current;

    const patch: ListPatch = (change) =>
      setLists((state) => (current === generation.current
        ? { ...state, [key]: change(state[key] as IdList) }
        : state));
    loadMoreProfileList(id, key, list, patch);
  }, [id]);

  return { ...lists, onMore: more };
}

function pendingList<T>(): ListState<T> {
  return { items: [], page: 0, hasMore: false, loading: true, loadingMore: false, error: null };
}

function pendingLists(loading = true) {
  const list = <T,>() => loading ? pendingList<T>() : {
    items: [], page: 0, hasMore: false, loading: false, loadingMore: false, error: null,
  };
  return { research: list<ProfilePaper>(), advised: list<ProfilePaper>(), collaborators: list<Collaborator>() };
}
