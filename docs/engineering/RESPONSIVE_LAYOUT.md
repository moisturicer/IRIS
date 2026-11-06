# Responsive layout and the viewport matrix (IR-910)

Every routed screen is opened at **360, 768, 1280 and 1745 px** on every pull
request that touches `frontend/`, and two things are asserted at each width.
The check is part of the smoke tier (IR-904), so it runs against the built app
with the network mocked and needs no stack.

## What is asserted

| Check | Rule | Why |
|---|---|---|
| No sideways scroll | `documentElement.scrollWidth - clientWidth` is 0 | WCAG 1.4.10 Reflow. Only the **page** counts: a box inside it may scroll on its own |
| Primary action reachable | The screen's one main control exists, is visible, sits inside the window sideways and is the element under its own centre point (not behind a header, drawer or scrim) | A page that fits but hides what you came to do is not usable |
| Table behaviour (table-heavy screens only) | The table either fits or scrolls inside its own container; a table that is cut off fails | See the next section |
| Not an error screen | "Something went wrong" is not on the page | A crashed page has nothing to overflow and nothing to reach, so it would otherwise pass vacuously |

The measuring code is `e2e/support/viewport.ts` (`measureOverflow`,
`checkReachable`, `describeTable`). `a11y.reflow360`, which the full-stack
journeys call, uses the same `measureOverflow`, so there is one definition of
"scrolls sideways". `e2e/smoke/viewport-helper.spec.ts` runs the helpers against
pages built for the purpose, because a matrix whose measurements cannot fail
proves nothing.

## Where the screens are listed

`e2e/smoke/support/screens.ts` has one entry per routed screen: the role it is
opened as, the API answers it needs, the heading that proves it drew, its
primary action, and (for tables) the table.

The routed screens themselves are listed in
`frontend/src/router/matrixRoutes.json`. Two tests keep the three in step, each
reading only its own stack (CODING_STANDARDS X1): `frontend/src/router/viewportMatrix.test.ts`
fails when that file and the route table disagree, and
`e2e/smoke/viewport-coverage.spec.ts` fails when `screens.ts` and that file
disagree. To add a screen: add the route, add its path to `matrixRoutes.json`,
then add its entry to `screens.ts`.

## Results

Each run writes one row per screen and one column per width to
`e2e/test-results-smoke/viewport-matrix.md` (and `.json`). CI prints the table
in the run's summary and uploads both with the report. A cell is the page's
overflow in px and whether the primary action could be reached. Visual snapshots
are **not** taken; that is a team decision (IR-910 leaves it optional).

## Table-heavy screens: small-screen behaviour

The screens whose content is a data table are **Users** (RDCO and System
Admin), **Role Requests**, **Audit Log**, **Download Requests** and **Delete
Requests**. The matrix draws one row on each and records what the table did at each
width. Their behaviour below a table's natural width is:

- **The table keeps its columns and scrolls sideways inside its own card.**
  The page never scrolls sideways. WCAG 1.4.10 exempts two-dimensional data
  tables from reflow, and re-flowing a six-column table into stacked cards would
  lose the column headers that make it readable.
- **The card is the scroll container** (`relative overflow-x-auto`). It must be
  `relative`: a screen-reader-only (`sr-only`) cell is `position: absolute`, and
  an absolutely positioned child of a scroll container that is not itself
  positioned escapes the clip and widens the whole page. That is what made
  Users, Role Requests and Admin Users scroll sideways at 360 and 768 px
  before IR-910.
- On Users, the search box and Filter sit **above** the table, outside the
  scroll container, so they stay reachable without scrolling it. Keep a screen's
  primary action outside its table's container for the same reason.

If a table needs a different behaviour (cards, a column picker), change it here
first and in the table's test second.

## Known limits

- The API is mocked, so the matrix draws screens with a small, hand-built set of
  rows. A screen with real data can still be wider than these rows make it; a
  long unbroken value is the usual cause (see IR-921). The matrix is a floor,
  not a substitute for looking at the real screen. My Reviews, the Office
  console, Workflow Analytics, Notifications, Opportunities and a blank Ask IRIS
  chat are drawn empty.
- "Primary action" is the control the screen exists for where there is one
  (Publish, Sign In, Export CSV). Where a screen is for reading, the entry names
  the first control a visitor would reach for (a tab, a filter, the Home
  breadcrumb), which proves the screen is usable at that width but is a weaker
  claim. The results table names the control in each row.
- Retired addresses (`router/redirects.tsx`) are not visited; the page each one
  lands on is a screen of its own in the matrix.
- Screens that only exist after an action (dialogs, the Publish wizard, an open
  review) are not separate routes and are not in the matrix.
- Contrast and touch-target size are not measured here.
