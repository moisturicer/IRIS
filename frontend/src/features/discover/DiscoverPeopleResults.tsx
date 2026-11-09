import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { peopleApi, type PeopleSearchParams } from "@/api/people";
import { FOCUS_RING } from "@/components/ui/interaction";
import { personPath } from "@/lib/access";
import { cn } from "@/lib/utils";
import type { PeopleSearchPage, PeopleSearchResult } from "@/types/people";
import { PersonAvatar } from "@/features/profile/PersonAvatar";
import { affiliationOf, displayName, initialsOf } from "@/features/profile/names";

interface DiscoverPeopleResultsProps {
  query: string;
  preview?: boolean;
  onSeeAll?: () => void;
}

const ROLE_OPTIONS = ["Student", "Adviser", "Faculty", "ITSO", "IERC", "KTTO", "RDCO"];
const PEOPLE_PAGE_SIZE = 20;

function hasNamedOptions(value: unknown): value is { results: { id: number; name: string }[] } {
  return typeof value === "object" && value !== null
    && "results" in value && Array.isArray(value.results)
    && value.results.every((option: unknown) => typeof option === "object" && option !== null
      && "id" in option && typeof option.id === "number"
      && "name" in option && typeof option.name === "string");
}

function isPeopleSearchResult(value: unknown): value is PeopleSearchResult {
  if (typeof value !== "object" || value === null) return false;
  const person = value as Record<string, unknown>;
  return typeof person.id === "number"
    && typeof person.first_name === "string"
    && typeof person.middle_initial === "string"
    && typeof person.last_name === "string"
    && typeof person.role_label === "string"
    && typeof person.college_name === "string"
    && typeof person.department_name === "string"
    && typeof person.course_name === "string"
    && (typeof person.photo_url === "string" || person.photo_url === null)
    && typeof person.published_paper_count === "number"
    && Number.isFinite(person.published_paper_count)
    && person.published_paper_count >= 0;
}

function isPeopleSearchPage(value: unknown): value is PeopleSearchPage {
  if (typeof value !== "object" || value === null) return false;
  const page = value as Record<string, unknown>;
  return typeof page.count === "number" && Number.isFinite(page.count) && page.count >= 0
    && Array.isArray(page.results) && page.results.every(isPeopleSearchResult);
}

function PersonResult({ person }: { person: PeopleSearchResult }) {
  const name = displayName(person);
  const affiliation = affiliationOf(person);
  const paperLabel = `${person.published_paper_count} published paper${person.published_paper_count === 1 ? "" : "s"}`;

  return (
    <article className="flex min-w-0 items-center gap-3 rounded-xl border border-stone-200 bg-white p-3 sm:p-4">
      <PersonAvatar photoUrl={person.photo_url} initials={initialsOf(person)} alt={name} size="sm" />
      <div className="min-w-0 flex-1">
        <Link to={personPath(person.id)} className={cn("font-semibold text-stone-900 underline-offset-2 hover:text-brand hover:underline", FOCUS_RING)}>
          {name}
        </Link>
        {affiliation && <p className="mt-0.5 truncate text-small text-stone-600">{affiliation}</p>}
        <p className="mt-0.5 text-small text-stone-600">{person.role_label} · {paperLabel}</p>
      </div>
    </article>
  );
}

/** Matching public people: a five-person Discover preview or a filtered directory. */
export function DiscoverPeopleResults({ query, preview = false, onSeeAll }: DiscoverPeopleResultsProps) {
  const [college, setCollege] = useState("");
  const [department, setDepartment] = useState("");
  const [role, setRole] = useState("");
  const [colleges, setColleges] = useState<{ id: number; name: string }[]>([]);
  const [departments, setDepartments] = useState<{ id: number; name: string }[]>([]);
  const [collegeFailure, setCollegeFailure] = useState(false);
  const [departmentFailure, setDepartmentFailure] = useState(false);
  const [results, setResults] = useState<PeopleSearchResult[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const activeSearch = useRef("");
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState(false);
  const searchKey = JSON.stringify([query.trim(), college, department, role]);
  const requestedPage = activeSearch.current === searchKey ? page : 1;

  useEffect(() => {
    let current = true;
    accountsApi.colleges().then(({ data }) => {
      if (!current) return;
      if (!hasNamedOptions(data)) {
        setColleges([]);
        setCollegeFailure(true);
        return;
      }
      setCollegeFailure(false);
      setColleges(data.results.map(({ id, name }) => ({ id, name })));
    }).catch(() => { if (current) { setColleges([]); setCollegeFailure(true); } });
    return () => { current = false; };
  }, []);

  useEffect(() => {
    let current = true;
    if (!college) {
      setDepartments([]);
      setDepartmentFailure(false);
      return () => { current = false; };
    }
    accountsApi.departments(Number(college)).then(({ data }) => {
      if (!current) return;
      if (!hasNamedOptions(data)) {
        setDepartments([]);
        setDepartmentFailure(true);
        return;
      }
      setDepartmentFailure(false);
      setDepartments(data.results.map(({ id, name }) => ({ id, name })));
    }).catch(() => { if (current) { setDepartments([]); setDepartmentFailure(true); } });
    return () => { current = false; };
  }, [college]);

  useEffect(() => {
    const trimmedQuery = query.trim();
    if (preview && !trimmedQuery) {
      setResults([]);
      setCount(0);
      activeSearch.current = searchKey;
      setLoading(false);
      return;
    }

    let current = true;
    const params: PeopleSearchParams = {
      q: trimmedQuery || undefined,
      page: requestedPage,
      page_size: PEOPLE_PAGE_SIZE,
      college: college ? Number(college) : undefined,
      department: department ? Number(department) : undefined,
      role: role || undefined,
    };
    if (activeSearch.current !== searchKey) {
      activeSearch.current = searchKey;
      setPage(1);
      setResults([]);
      setCount(0);
      if (page !== 1) return;
    }
    setLoading(true);
    setFailure(false);
    peopleApi.search(params).then(({ data }) => {
      if (!current) return;
      if (!isPeopleSearchPage(data)) throw new Error("Unexpected people search response");
      setResults((previous) => requestedPage === 1 ? data.results : [...previous, ...data.results]);
      setCount(data.count);
    }).catch(() => {
      if (!current) return;
      setFailure(true);
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [query, college, department, role, page, preview, retry, searchKey, requestedPage]);

  if (preview) {
    if (!query.trim() || (!loading && results.length === 0 && !failure)) return null;
    return (
      <section aria-labelledby="discover-people-heading" className="mb-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id="discover-people-heading" className="font-display text-title font-semibold text-stone-900">People</h2>
          {count > 0 && (
            <button type="button" onClick={onSeeAll} className={cn("shrink-0 text-small font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
              See all people
            </button>
          )}
        </div>
        {failure ? <p role="status" className="text-small text-stone-600">People could not be loaded.</p>
          : loading && results.length === 0 ? <p role="status" className="text-small text-stone-600">Searching people…</p>
            : <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {results.slice(0, 5).map((person) => <PersonResult key={person.id} person={person} />)}
            </div>}
      </section>
    );
  }

  const nextPage = requestedPage * PEOPLE_PAGE_SIZE < count;
  return (
    <section aria-labelledby="discover-people-heading" className="mt-5">
      <div className="mb-4 flex flex-wrap gap-3">
        <label className="grid gap-1 text-small font-medium text-stone-700">
          College
          <select value={college} onChange={(event) => { setCollege(event.target.value); setDepartment(""); }} className="h-10 min-w-44 rounded-lg border border-stone-300 bg-white px-3 text-body">
            <option value="">All colleges</option>
            {colleges.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-small font-medium text-stone-700">
          Department
          <select value={department} onChange={(event) => setDepartment(event.target.value)} disabled={!college} className="h-10 min-w-44 rounded-lg border border-stone-300 bg-white px-3 text-body disabled:bg-stone-100">
            <option value="">All departments</option>
            {departments.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-small font-medium text-stone-700">
          Role
          <select value={role} onChange={(event) => setRole(event.target.value)} className="h-10 min-w-36 rounded-lg border border-stone-300 bg-white px-3 text-body">
            <option value="">All roles</option>
            {ROLE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
      </div>
      {(collegeFailure || (college && departmentFailure)) && <p role="alert" className="mb-3 text-small text-stone-700">Some people filters couldn’t be loaded.</p>}
      <h2 id="discover-people-heading" className="sr-only">People</h2>
      {failure ? <div role="alert" className="text-body text-stone-700"><p>We couldn’t load people.</p><button type="button" onClick={() => setRetry((value) => value + 1)} className={cn("mt-2 text-small font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>Try again</button></div>
        : loading && results.length === 0 ? <p role="status" className="text-body text-stone-600">Searching people…</p>
          : results.length === 0 ? <p className="text-body text-stone-600">No people match this search.</p>
            : <>
              <p className="mb-3 text-small text-stone-600">{count} {count === 1 ? "person" : "people"}</p>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {results.map((person) => <PersonResult key={person.id} person={person} />)}
              </div>
              {(nextPage || failure) && <button type="button" onClick={() => failure ? setRetry((value) => value + 1) : setPage((value) => value + 1)} className={cn("mt-6 rounded-lg border border-stone-300 bg-white px-4 py-2 text-small font-semibold text-stone-800 hover:border-brand hover:text-brand", FOCUS_RING)}>{failure ? "Try again" : "Load more people"}</button>}
            </>}
    </section>
  );
}
