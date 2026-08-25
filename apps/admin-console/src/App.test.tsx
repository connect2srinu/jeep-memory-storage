import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AdminApiClient } from "./api";
import { ConsolePage, ConsoleShell, OrganizationHierarchyView } from "./App";
import type { AdminIdentity } from "./types";

const viewer: AdminIdentity = { user: "viewer@example.com", roles: ["VIEWER"], domains: [] };
const platform: AdminIdentity = {
  user: "admin@example.com",
  roles: ["PLATFORM_ADMIN"],
  domains: [],
};
const api = new AdminApiClient("http://memory-api/api/v1/admin", viewer);

describe("Admin Console components", () => {
  it("renders all governed navigation areas and identity", () => {
    const html = renderToStaticMarkup(
      <ConsoleShell identity={platform} section="dashboard" status="connected" onSection={() => {}} />,
    );
    expect(html).toContain("Shared Memory");
    expect(html).toContain("Create Memory Setup");
    expect(html).toContain("Govern &amp; manage");
    expect(html).toContain("Organizations");
    expect(html).toContain("Resolution Policies");
    expect(html).toContain("Dynamic Memory Policies");
    expect(html).toContain("admin@example.com");
  });

  it("hides mutation form for a viewer", () => {
    const html = renderToStaticMarkup(<ConsolePage section="schemas" identity={viewer} api={api} />);
    expect(html).toContain("Read-only for the selected role");
    expect(html).not.toContain("Create governed record");
  });

  it("shows schema editor and preview for a platform admin", () => {
    const html = renderToStaticMarkup(
      <ConsolePage
        section="schemas"
        identity={platform}
        api={new AdminApiClient("http://memory-api/api/v1/admin", platform)}
      />,
    );
    expect(html).toContain("Create schemas JSON");
    expect(html).toContain("Schema preview");
    expect(html).toContain("Create governed record");
  });

  it("renders an organization directory and organization project workspace", () => {
    const hierarchy = {
      organizations: [{
        id: "retail",
        name: "Retail",
        description: "Retail line of business",
        status: "ACTIVE",
        members: [{ id: "m1", display_name: "Retail Owner", role: "OWNER" }],
        projects: [{
          id: "shopping",
          name: "Shopping",
          description: "Shopping experiences",
          owner_team: "shopping-platform",
          domains: [{ id: "grocery", name: "Grocery" }],
          agents: [{ id: "grocery-agent", display_name: "Grocery Assistant" }],
          members: [{ id: "m2", member_principal: "lead@example.com", role: "ADMIN" }],
        }],
      }],
    };
    const html = renderToStaticMarkup(
      <OrganizationHierarchyView
        hierarchy={hierarchy}
        writable
        api={new AdminApiClient("http://memory-api/api/v1/admin", platform)}
        reload={() => {}}
      />,
    );
    expect(html).toContain("Create organization");
    expect(html).toContain("Retail");
    expect(html).toContain("1</b> projects");

    const projectWorkspace = renderToStaticMarkup(
      <OrganizationHierarchyView
        hierarchy={hierarchy}
        writable
        api={new AdminApiClient("http://memory-api/api/v1/admin", platform)}
        reload={() => {}}
        selectedOrganization={{ id: "retail", name: "Retail" }}
        organizationTab="projects"
      />,
    );
    expect(projectWorkspace).toContain("New project");
    expect(projectWorkspace).toContain("Shopping");
    expect(projectWorkspace).toContain("Open project");

    const memberWorkspace = renderToStaticMarkup(
      <OrganizationHierarchyView
        hierarchy={hierarchy}
        writable
        api={new AdminApiClient("http://memory-api/api/v1/admin", platform)}
        reload={() => {}}
        selectedOrganization={{ id: "retail", name: "Retail" }}
        organizationTab="members"
      />,
    );
    expect(memberWorkspace).toContain("Members &amp; Roles");
    expect(memberWorkspace).toContain("Retail Owner");
    expect(memberWorkspace).toContain("Add member");

    const projectAgents = renderToStaticMarkup(
      <OrganizationHierarchyView
        hierarchy={hierarchy}
        writable
        api={new AdminApiClient("http://memory-api/api/v1/admin", platform)}
        reload={() => {}}
        selectedOrganization={{ id: "retail", name: "Retail" }}
        selectedProject={{ id: "shopping", name: "Shopping" }}
        projectTab="agents"
      />,
    );
    expect(projectAgents).toContain("Grocery Assistant");
  });
});
