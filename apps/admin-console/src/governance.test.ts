import { describe, expect, it } from "vitest";

import { canMutate, findNormalizedDuplicates, movePriority, normalizeName } from "./governance";

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
});
