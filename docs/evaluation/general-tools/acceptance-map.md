# IR-589 acceptance map, version 1

ADR-042's product contract was approved by Jive Tyler Revalde on 2026-10-15; these expected results remain unimplemented and unmeasured unless noted below.

This map records the approved product contract separately from the current-system control. The [fixture](../../../backend/apps/ai/evaluation/fixtures/general_tools_contract_v1.json) is the machine-readable source for inputs, deterministic scripts and expected results. The [HTTP control](../../../backend/apps/ai/evaluation/tests/test_general_tools_current_http.py) submits every conversation through both authenticated ask endpoints and reopens it; it checks response shape and private-record exclusion. It also forces the existing comparison/listing lanes for A01/A09 and asserts their failure wording on the live response and replay. Its database cases were **skipped locally** because Postgres was unavailable, so no runtime baseline result is claimed here. Each new behavior below needs a downstream contract assertion before that ticket can claim it passes.

| ID | Approved contract oracle | Required downstream seam | Current evidence |
|---|---|---|---|
| A01 | MeshKV topic, discovered pair and citations survive four turns | HTTP/SSE and reopened Conversation | Current comparison-title failure text source-pinned and HTTP-asserted; control awaits DB |
| A02 | First and third mean the last displayed order, with current source versions | HTTP and Conversation state | HTTP control awaits DB |
| A03 | Exclusions persist; insufficient results are stated without invention | HTTP and Conversation state | HTTP control awaits DB |
| A04 | Exact title resolves, ambiguous alias asks one question, hidden identity stays hidden | HTTP and resolver | HTTP control awaits DB |
| A05 | Late section is read with continuation beyond prefix | HTTP and read result | HTTP control awaits DB; control corpus has one page per paper |
| A06 | Exact distinct-Record metadata count stays separate from screened subset | HTTP and typed aggregate | HTTP control awaits DB |
| A07 | Incompatible datasets do not produce a winner | HTTP and validated answer | HTTP control awaits DB |
| A08 | Detail and simplification preserve context without another retrieval | HTTP and provider-call record | HTTP control awaits DB |
| A09 | Missing field, no match and outage are distinct; a tool outage retains independently supported parts with a material limitation | HTTP/SSE and replay | Current unavailable text source-pinned and HTTP-asserted; control awaits DB |
| A10 | Harmless numerals pass; unsupported 37% claim gets at most one repair | HTTP and answer validator | HTTP control awaits DB |
| A11 | Revocation, stale brief, foreign handle and Paper Chat scope cannot leak; a general explanation remains available without an unsupported paper claim | HTTP/SSE, replay and access seam | HTTP control awaits DB |
| A12 | Cancel/redelivery/reconnect/race make at most one Turn and no stale write | Real shared worker/store | HTTP control awaits DB; race result unmeasured |
| A13 | Live, reopened, copy, mobile, export and Paper Chat omit diagnostics; both prompt boxes show the persistent mistake notice before submission | Public serializer and UI accessibility | HTTP control awaits DB; UI unmeasured |
| A14 | Unsupported summary is omitted; reasoning-only is unavailable | Provider adapter and public serializer | HTTP control awaits DB |
| A15 | Injected text and optional public query cannot widen access or egress | Tool admission and public adapter | HTTP control awaits DB; public adapter not built |

The acceptance target is not the control path's generic 200 response. Downstream tests must use the same synthetic snapshot ID/digest or record their own corpus manifest, replace one approved but unmeasured expectation at a time with an executed assertion, and report the result by ID. No source-inspected text is counted as an HTTP observation.
