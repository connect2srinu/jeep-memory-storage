import { describe, expect, it } from "vitest";

import {
  canMutate,
  filterRecords,
  findNormalizedDuplicates,
  movePriority,
  normalizeName,
  paginateRecords,
  sortRecords,
} from "./governance";

describe("governance helpers", () => {
  it("detects normalized duplicate names", () => {
    expect(normalizeName("Preferred Store")).toBe("preferredstore");
    expect(findNormalizedDuplicates(["preferred_store", "Preferred Store", "diet"])).toEqual([
      "Preferred Store",
    ]);
  });

  it("enforces viewer and domain role guards", () => {
    expect(canMutate({ user: "v", roles: ["VIEWER"], domains: [] }, "domains")).toBe(false);
    expect(
      canMutate({ user: "a", roles: ["AGENT_OWNER"], domains: ["grocery"] }, "agents"),
    ).toBe(true);
    expect(
      canMutate({ user: "s", roles: ["SCHEMA_OWNER"], domains: ["customer"] }, "approvals"),
    ).toBe(true);
  });

  it("reorders priorities without mutating the input", () => {
    const input = ["grocery", "customer", "inventory"];
    expect(movePriority(input, 1, -1)).toEqual(["customer", "grocery", "inventory"]);
    expect(input).toEqual(["grocery", "customer", "inventory"]);
  });

  it("searches primitive and nested resource values", () => {
    const records = [
      { id: "grocery-agent", capabilities: { resolve_context: true } },
      { id: "customer-agent", capabilities: { inspect_provenance: true } },
    ];
    expect(filterRecords(records, "PROVENANCE")).toEqual([records[1]]);
    expect(filterRecords(records, "grocery", ["id"])).toEqual([records[0]]);
  });

  it("sorts values stably and keeps missing values last", () => {
    const records = [
      { id: "third", priority: 10 },
      { id: "first", priority: 2 },
      { id: "missing", priority: null },
    ];
    expect(sortRecords(records, "priority", "ascending").map((record) => record.id)).toEqual([
      "first",
      "third",
      "missing",
    ]);
    expect(sortRecords(records, "id", "descending").map((record) => record.id)).toEqual([
      "third",
      "missing",
      "first",
    ]);
  });

  it("returns the requested page without mutating records", () => {
    const records = [1, 2, 3, 4, 5];
    expect(paginateRecords(records, 2, 2)).toEqual([3, 4]);
    expect(records).toEqual([1, 2, 3, 4, 5]);
  });
});
