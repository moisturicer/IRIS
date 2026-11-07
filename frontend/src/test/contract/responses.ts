/**
 * The response type each covered call declares (IR-915).
 *
 * The contract test turns these into JSON Schemas (`ts-json-schema-generator`
 * reads plain exported types, and does not resolve `ReturnType<typeof fn>`),
 * then validates each recorded backend response against its schema.
 *
 * Two of these restate a type no module exports (the paginated wrapper and
 * `facets`' inline body). Restated types drift, so `ContractChecks` below
 * makes `tsc` (run by `npm run build`) fail when one stops being identical to
 * the type its API call declares. Do not export anything else from this file:
 * the test generates a schema for the names it lists, and the checks are
 * compile-time only.
 */
import type { authApi } from "@/api/auth";
import type { libraryApi, SavedRecordEntry } from "@/api/library";
import type { recordsApi } from "@/api/records";
import type { reviewsApi } from "@/api/reviews";
import type { LoginResponse, User } from "@/types/auth";
import type {
  Classification, DocumentRequest, MyResearchItem, RecordDetail, RecordListItem, RecordTracker,
} from "@/types/records";
import type { MyReviewsPage } from "@/types/reviews";

/** `PaginatedResponse<T>`, declared (unexported) in `api/records.ts`. */
interface Paginated<T> {
  count:    number;
  next:     string | null;
  previous: string | null;
  results:  T[];
}

export type RecordListResponse = Paginated<RecordListItem>;
export type RecordDetailResponse = RecordDetail;
export type RecordTrackerResponse = RecordTracker;
export type RecordFacetsResponse = { years: number[] };
export type ClassificationsResponse = Paginated<Classification>;
export type DocumentRequestsResponse = DocumentRequest[];
export type RecordMineResponse = MyResearchItem[];
export type LibrarySavesResponse = { results: SavedRecordEntry[] };
export type ReviewsMineResponse = MyReviewsPage;
export type LoginResponseBody = LoginResponse;
export type UserMeResponse = User;

// -- compile-time checks ---------------------------------------------------

type Body<R> = R extends Promise<{ data: infer D }> ? D : never;
type Equal<A, B> =
  (<T>() => T extends A ? 1 : 2) extends (<T>() => T extends B ? 1 : 2) ? true : false;
type Assert<T extends true> = T;

/** Each line fails to compile when the type above stops matching the call's own. */
export type ContractChecks = [
  Assert<Equal<RecordListResponse,       Body<ReturnType<typeof recordsApi.list>>>>,
  Assert<Equal<RecordDetailResponse,     Body<ReturnType<typeof recordsApi.detail>>>>,
  Assert<Equal<RecordTrackerResponse,    Body<ReturnType<typeof recordsApi.tracker>>>>,
  Assert<Equal<RecordFacetsResponse,     Body<ReturnType<typeof recordsApi.facets>>>>,
  Assert<Equal<ClassificationsResponse,  Body<ReturnType<typeof recordsApi.classifications>>>>,
  Assert<Equal<DocumentRequestsResponse, Body<ReturnType<typeof recordsApi.documentRequests>>>>,
  Assert<Equal<RecordMineResponse,       Body<ReturnType<typeof recordsApi.mine>>>>,
  Assert<Equal<LibrarySavesResponse,     Body<ReturnType<typeof libraryApi.saves>>>>,
  Assert<Equal<ReviewsMineResponse,      Body<ReturnType<typeof reviewsApi.mine>>>>,
  Assert<Equal<LoginResponseBody,        Body<ReturnType<typeof authApi.login>>>>,
  Assert<Equal<UserMeResponse,           Body<ReturnType<typeof authApi.me>>>>,
];
