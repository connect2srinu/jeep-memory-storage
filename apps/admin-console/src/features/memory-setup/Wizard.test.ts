import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { isRecommended, MemorySetupIntro, projectDomainOptions, wizardSteps } from "./Wizard";

describe("memory setup landing page", () => {
  it("orients the user and exposes a start action before the stepper", () => {
    const html = renderToStaticMarkup(
      createElement(MemorySetupIntro, {
        counts: { organizations: 2, projects: 3, schemas: 4, agents: 5 },
        organizationLabel: "retail",
        onStart: () => {},
      }),
    );
    expect(html).toContain("Create Memory Setup");
    expect(html).toContain("Governed memory");
    expect(html).toContain("never pre-creates user profiles");
    expect(html).toContain("Start setup");
    // live inventory counts are surfaced
    expect(html).toContain(">4<");
    expect(html).toContain("retail");
  });
});

describe("domain options follow the selected organization and project", () => {
  const domains = [
    { id: "grocery", name: "Grocery", organization_id: "retail", project_id: "shopping" },
    { id: "customer", name: "Customer", organization_id: "retail", project_id: "customer-experience" },
    { id: "loyalty", name: "Loyalty", organization_id: "bank", project_id: "shopping" },
  ];

  it("filters domains to the chosen organization and project", () => {
    expect(projectDomainOptions(domains, "retail", "shopping").map((item) => item.id)).toEqual(["grocery"]);
    expect(projectDomainOptions(domains, "retail", "customer-experience").map((item) => item.id)).toEqual(["customer"]);
    // Same project name in a different organization must not leak across the tenant boundary.
    expect(projectDomainOptions(domains, "bank", "shopping").map((item) => item.id)).toEqual(["loyalty"]);
  });

  it("returns nothing for a project with no domains yet", () => {
    expect(projectDomainOptions(domains, "retail", "empty-project")).toEqual([]);
  });
});

describe("guided memory setup", () => {
  it("shows sharing and resolution only when required", () => {
    expect(wizardSteps(false, 1)).toEqual([
      "Use Case", "Preferences", "Scope", "Memory", "Agents", "Review", "Activate",
    ]);
    expect(wizardSteps(true, 2)).toEqual([
      "Use Case", "Preferences", "Scope", "Memory", "Agents", "Sharing",
      "Resolution", "Review", "Activate",
    ]);
    // Consumer only: no scope or memory settings of its own.
    expect(wizardSteps(true, 1, true)).toEqual([
      "Use Case", "Preferences", "Agents", "Sharing", "Review", "Activate",
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
