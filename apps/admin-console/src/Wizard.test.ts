import { describe, expect, it } from "vitest";

import { isRecommended, wizardSteps } from "./Wizard";

describe("guided memory setup", () => {
  it("shows sharing and resolution only when required", () => {
    expect(wizardSteps(false, 1)).toEqual([
      "Use Case", "Preferences", "Scope", "Memory", "Agents", "Review", "Activate",
    ]);
    expect(wizardSteps(true, 2)).toEqual([
      "Use Case", "Preferences", "Scope", "Memory", "Agents", "Sharing",
      "Resolution", "Review", "Activate",
    ]);
  });

  it("recommends Grocery defaults and catalog-configured domains", () => {
    expect(isRecommended({ attribute_id: "grocery.allow_substitutions" }, "grocery")).toBe(true);
    expect(isRecommended({
      attribute_id: "customer.favorite_brand",
      canonical_owner_id: "customer",
      validation_rules: { recommended_domains: ["grocery"] },
    }, "grocery")).toBe(true);
    expect(isRecommended({ attribute_id: "delivery.preferred_window" }, "grocery")).toBe(false);
  });
});
