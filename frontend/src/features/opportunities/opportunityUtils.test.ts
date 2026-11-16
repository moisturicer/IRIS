import { describe, expect, it } from "vitest";

import { TONES } from "@/components/ui/statusTones";
import type { Opportunity } from "@/types/opportunities";

import {
  DEADLINE_GROUPS,
  EMPTY_DRAFT,
  OPPORTUNITY_TYPES,
  areaNames,
  byBoardOrder,
  checkDraft,
  countdown,
  deadlineGroup,
  eventDates,
  eventTag,
  hasEvent,
  inputFrom,
  serverErrors,
  withType,
} from "./opportunityUtils";

const at = (days_left: number, is_closed = days_left < 0) =>
  ({ days_left, is_closed, papers_state: is_closed ? "closed" : "accepting" }) as Opportunity;

describe("deadlineGroup", () => {
  it.each([
    [0, "week"], [7, "week"], [8, "month"], [30, "month"], [31, "later"], [-1, "closed"],
  ] as const)("puts a call %i days out in %s", (days, group) => {
    expect(deadlineGroup(at(days))).toBe(group);
  });

  it("goes by the server's papers state, not the day count", () => {
    expect(deadlineGroup({ ...at(3), papers_state: "closed" })).toBe("closed");
  });

  it("names the last group Submissions closed (IR-764)", () => {
    expect(DEADLINE_GROUPS.map((g) => g.title).at(-1)).toBe("Submissions closed");
  });
});

describe("byBoardOrder", () => {
  it("never moves a featured call (ADR-050 decision 12)", () => {
    const plain    = { id: 1, due_date: "2026-11-01", is_featured: false } as Opportunity;
    const featured = { id: 2, due_date: "2026-11-01", is_featured: true } as Opportunity;
    expect([featured, plain].sort(byBoardOrder).map((o) => o.id)).toEqual([1, 2]);
  });
});

describe("the two tags (ADR-050 decision 6)", () => {
  const tagged = (o: Partial<Opportunity>) => ({ ...at(5), papers_label: "Accepting papers", event_state: null, event_label: null, ...o }) as Opportunity;

  it("shows Happening now only while the event runs", () => {
    expect(eventTag(tagged({ event_state: "happening", event_label: "Happening now" }))).toBe("Happening now");
    for (const state of ["upcoming", "over", null] as const) {
      expect(eventTag(tagged({ event_state: state, event_label: state ? "x" : null }))).toBeNull();
    }
  });
});

describe("eventDates", () => {
  it("is nothing for a call with no event, one date for a one-day event, else a range", () => {
    expect(eventDates({ start_date: null, end_date: null } as Opportunity)).toBeNull();
    expect(eventDates({ start_date: "2027-01-20", end_date: null } as Opportunity)).toBe("Jan 20, 2027");
    expect(eventDates({ start_date: "2027-01-20", end_date: "2027-01-20" } as Opportunity)).toBe("Jan 20, 2027");
    expect(eventDates({ start_date: "2027-01-20", end_date: "2027-01-22" } as Opportunity)).toBe("Jan 20, 2027 to Jan 22, 2027");
  });
});

describe("areaNames", () => {
  it("lists every Area on the board once, sorted", () => {
    expect(areaNames([
      { area_names: ["Clean Energy", "AI"] }, { area_names: ["AI"] }, { area_names: [] },
    ] as unknown as Opportunity[])).toEqual(["AI", "Clean Energy"]);
  });
});

describe("withType: Journal and Book Chapter have no event (ADR-050 decision 4)", () => {
  it("drops the event dates and fills an empty location with Online", () => {
    const d = withType({ ...EMPTY_DRAFT, start_date: "2027-01-01", end_date: "2027-01-02" }, "journal");
    expect(d).toMatchObject({ opportunity_type: "journal", start_date: "", end_date: "", location: "Online" });
  });

  it("keeps a location the poster typed", () => {
    expect(withType({ ...EMPTY_DRAFT, location: "Manila" }, "book_chapter").location).toBe("Manila");
  });

  it("leaves an event type's fields alone", () => {
    const d = withType({ ...EMPTY_DRAFT, start_date: "2027-01-01" }, "workshop");
    expect(d).toMatchObject({ opportunity_type: "workshop", start_date: "2027-01-01", location: "" });
  });

  it("knows which types have no event", () => {
    expect(OPPORTUNITY_TYPES.filter((t) => !hasEvent(t.id)).map((t) => t.id)).toEqual(["journal", "book_chapter"]);
  });
});

describe("countdown", () => {
  it("says it in words and uses only the four tones", () => {
    expect(countdown(at(0))).toMatchObject({ label: "Due today", tone: "attention", className: TONES.attention });
    expect(countdown(at(1))).toMatchObject({ label: "1 day left", tone: "attention" });
    expect(countdown(at(7))).toMatchObject({ label: "7 days left", tone: "attention" });
    expect(countdown(at(21))).toMatchObject({ label: "21 days left", tone: "active" });
    expect(countdown(at(22))).toMatchObject({ label: "22 days left", tone: "quiet" });
    expect(countdown(at(-3))).toMatchObject({ label: "Closed", tone: "quiet" });
  });
});

describe("the form's draft", () => {
  it("names the seven required fields when they are empty", () => {
    expect(Object.keys(checkDraft(EMPTY_DRAFT)).sort()).toEqual(
      ["areas", "description", "due_date", "external_url", "location", "opportunity_type", "title"],
    );
  });

  it("sends an empty event date as none, and checks no date", () => {
    const base = {
      ...EMPTY_DRAFT, opportunity_type: "workshop" as const, title: "T", description: "A",
      due_date: "2026-11-01", location: "Online", areas: [1], external_url: "https://example.org",
    };
    // An end before its start is the poster's to fix (ADR-050 decision 5).
    expect(checkDraft({ ...base, start_date: "2027-03-05", end_date: "2027-03-01" })).toEqual({});
    expect(inputFrom(base)).toMatchObject({ start_date: null, end_date: null, areas: [1] });
  });

  it("sends no event dates for a Journal, even ones left in the draft", () => {
    const journal = { ...EMPTY_DRAFT, opportunity_type: "journal" as const, start_date: "2027-01-01", end_date: "2027-01-02" };
    expect(inputFrom(journal)).toMatchObject({ start_date: null, end_date: null });
  });
});

describe("serverErrors", () => {
  it("puts a field's message on the field and anything else on the form", () => {
    expect(serverErrors({ title: ["Too long."], detail: "Slow down.", posted_by: ["Nope."] })).toEqual({
      fields: { title: "Too long." },
      form: "Slow down. Nope.",
    });
  });

  it("tolerates a body that is not an object", () => {
    expect(serverErrors("Bad Request")).toEqual({ fields: {}, form: null });
  });
});
