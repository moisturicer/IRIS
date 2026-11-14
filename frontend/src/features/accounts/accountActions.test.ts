/**
 * Which actions a row carries for a viewer (IR-1077): the rules of
 * `accountActions.ts` plus "never on your own row".
 */
import { describe, expect, it } from "vitest";

import { rowActions } from "./accountActions";

describe("rowActions", () => {
  it("lists change role and lock for RDCO on a Student, in menu order", () => {
    expect(rowActions("RDCO", 99, { id: 4, role_name: "Student" })).toEqual(["change-role", "lock"]);
  });

  it("lists change role and the coordinator flag for the System Admin on an office row", () => {
    expect(rowActions("System Admin", 99, { id: 2, role_name: "ITSO" })).toEqual(["change-role", "coordinator"]);
  });

  it("lists nothing on a System Admin's row", () => {
    expect(rowActions("RDCO", 99, { id: 6, role_name: "System Admin" })).toEqual([]);
    expect(rowActions("System Admin", 99, { id: 6, role_name: "System Admin" })).toEqual([]);
  });

  it("lists nothing on the viewer's own row, whatever the rules would allow", () => {
    expect(rowActions("RDCO", 4, { id: 4, role_name: "Student" })).toEqual([]);
    expect(rowActions("System Admin", 2, { id: 2, role_name: "ITSO" })).toEqual([]);
  });

  it("lists nothing for any other viewer", () => {
    expect(rowActions("Student", 99, { id: 4, role_name: "Student" })).toEqual([]);
    expect(rowActions(undefined, undefined, { id: 4, role_name: "Student" })).toEqual([]);
  });

  it("lists nothing while the viewer's own id is unknown, so a row can never be their own", () => {
    expect(rowActions("RDCO", undefined, { id: 4, role_name: "Student" })).toEqual([]);
    expect(rowActions("RDCO", null, { id: 4, role_name: "Student" })).toEqual([]);
  });
});
