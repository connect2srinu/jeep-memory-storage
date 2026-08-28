import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminApiClient } from "./api";
import { canMutate } from "./governance";
import type { AdminIdentity, AdminRecord, AdminRole } from "./types";
import { ErrorBanner } from "./components/ErrorBanner";
import { ResourceTable } from "./components/ResourceTable";
import { UiIcon } from "./components/UiIcon";
import { templates } from "./lib/templates";
import { AccessActions, ResourceChangeActions } from "./features/approvals/ApprovalsTable";
import { JsonCreateForm, ResourceDetailPanel } from "./features/resources/ResourceDetailPanel";
import { OrganizationManagement, type ContextSelection, type OrganizationTab, type ProjectTab } from "./features/organizations/OrganizationWorkspace";
import { PlatformOverview } from "./features/dashboard/PlatformOverview";
import { MemorySetupWizard } from "./features/memory-setup/Wizard";

export const primarySections = [
  ["dashboard", "Dashboard", "home"],
  ["create-setup", "Create Memory Setup", "sparkles"],
] as const;

export const advancedSections = [
  ["organizations", "Organizations & Projects", "building"],
  ["domains", "Domains", "domain"],
  ["scopes", "Scopes", "scope"],
  ["schemas", "Schemas", "schema"],
  ["preference-catalog", "Preference Catalog", "catalog"],
  ["agents", "Agents", "agent"],
  ["access-requests", "Access Requests", "share"],
  ["approvals", "Approvals", "approval"],
  ["resolution-policies", "Resolution Policies", "policy"],
  ["dynamic-memory-policies", "Dynamic Memory Policies", "memory"],
  ["audit", "Audit", "audit"],
] as const;

export const sections = [...primarySections, ...advancedSections] as const;

export type OrganizationNavigation = {
  selectedOrganization: ContextSelection;
  selectedProject: ContextSelection;
  organizationTab: OrganizationTab;
  projectTab: ProjectTab;
  onSelectOrganization: (organization: ContextSelection) => void;
  onSelectProject: (project: ContextSelection) => void;
  onOrganizationTab: (tab: OrganizationTab) => void;
  onProjectTab: (tab: ProjectTab) => void;
};

export const defaultOrganizationNavigation: OrganizationNavigation = {
  selectedOrganization: null,
  selectedProject: null,
  organizationTab: "projects",
  projectTab: "overview",
  onSelectOrganization: () => {},
  onSelectProject: () => {},
  onOrganizationTab: () => {},
  onProjectTab: () => {},
};

export function ConsolePage({ section, identity, api, organizationNavigation = defaultOrganizationNavigation }: { section: string; identity: AdminIdentity; api: AdminApiClient; organizationNavigation?: OrganizationNavigation }) {
  const resource = section === "approvals" ? "access-requests" : section;
  const [records, setRecords] = useState<AdminRecord[]>([]);
  const [changeRequests, setChangeRequests] = useState<AdminRecord[]>([]);
  const [selectedRecord, setSelectedRecord] = useState<AdminRecord | null>(null);
  const [loading, setLoading] = useState(!["dashboard", "create-setup", "organizations"].includes(section));
  const [error, setError] = useState("");
  const title = sections.find(([id]) => id === section)?.[1] ?? section;
  const reload = useCallback(() => {
    if (["dashboard", "create-setup", "organizations"].includes(section)) return;
    setLoading(true);
    const operation = section === "approvals"
      ? Promise.all([api.list("access-requests"), api.listResourceChanges()]).then(([access, changes]) => { setRecords(access); setChangeRequests(changes); })
      : api.list(resource, organizationNavigation.selectedOrganization?.id).then(setRecords);
    operation.catch((caught) => setError(caught instanceof Error ? caught.message : "Request failed")).finally(() => setLoading(false));
  }, [api, organizationNavigation.selectedOrganization?.id, resource, section]);
  useEffect(() => { setSelectedRecord(null); reload(); }, [reload]);
  if (section === "dashboard") return <PlatformOverview />;
  if (section === "create-setup") return canMutate(identity, section) ? <MemorySetupWizard api={api} /> : <p className="read-only">Platform Administrator role is required to create a memory setup.</p>;
  if (section === "organizations") return <OrganizationManagement identity={identity} api={api} {...organizationNavigation} />;
  const writable = canMutate(identity, section);
  const hasPendingApprovals = changeRequests.some((record) => record.status === "PENDING") || records.some((record) => record.status === "PENDING");
  if (section === "approvals" && !writable) return <section><div className="section-heading"><div><span className="eyebrow">Control plane</span><h2>{title}</h2></div><button type="button" onClick={reload}>Refresh</button></div><ErrorBanner error={error} /><ResourceTable records={[...changeRequests, ...records]} /><p className="read-only">Platform Administrator role is required to approve or reject requests.</p></section>;
  return <section><div className="section-heading"><div><span className="eyebrow">Control plane</span><h2>{title}</h2></div><button type="button" onClick={reload}>Refresh</button></div><ErrorBanner error={error} />{loading ? <p>Loading…</p> : section === "approvals" ? <>{!hasPendingApprovals && <div className="empty-state"><strong>No pending approvals</strong><p>Domain change and cross-project access requests will appear here for review.</p></div>}<ResourceChangeActions records={changeRequests} api={api} reload={reload} approvalsOnly /><AccessActions records={records} api={api} reload={reload} approvalsOnly /></> : section === "access-requests" ? <AccessActions records={records} api={api} reload={reload} approvalsOnly={false} /> : <ResourceTable records={records} onSelect={setSelectedRecord} />}{section !== "approvals" && writable && templates[resource] && <JsonCreateForm resource={resource} onCreate={async (payload) => { await api.create(resource, payload); reload(); }} />}{!writable && <p className="read-only">Read-only for the selected role.</p>}{selectedRecord && <ResourceDetailPanel resource={resource} record={selectedRecord} writable={writable} api={api} contextOrganizationId={organizationNavigation.selectedOrganization?.id} onClose={() => setSelectedRecord(null)} onSaved={reload} />}</section>;
}

export function ConsoleShell({ identity, section, status, onSection }: { identity: AdminIdentity; section: string; status: string; onSection: (value: string) => void }) {
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_CONTROL_PLANE_API_URL ?? "/control-plane-api/api/v1/admin", identity), [identity]);
  const [selectedOrganization, setSelectedOrganization] = useState<ContextSelection>(null);
  const [selectedProject, setSelectedProject] = useState<ContextSelection>(null);
  const [organizationTab, setOrganizationTab] = useState<OrganizationTab>("projects");
  const [projectTab, setProjectTab] = useState<ProjectTab>("overview");
  function openOrganizations() { setSelectedOrganization(null); setSelectedProject(null); onSection("organizations"); }
  function selectOrganization(organization: ContextSelection) { setSelectedOrganization(organization); setSelectedProject(null); setOrganizationTab("projects"); onSection("organizations"); }
  function selectProject(project: ContextSelection) { setSelectedProject(project); setProjectTab("overview"); onSection("organizations"); }
  function chooseOrganizationTab(tab: OrganizationTab) { setSelectedProject(null); setOrganizationTab(tab); onSection("organizations"); }
  function chooseProjectTab(tab: ProjectTab) { setProjectTab(tab); onSection("organizations"); }
  const organizationNavigation = { selectedOrganization, selectedProject, organizationTab, projectTab, onSelectOrganization: selectOrganization, onSelectProject: selectProject, onOrganizationTab: chooseOrganizationTab, onProjectTab: chooseProjectTab };
  return <div className="app-shell"><aside><div className="brand"><span>GEAP</span><div><strong>Portal</strong><small>Control plane</small></div></div><button className="context-switcher" type="button" onClick={openOrganizations}><span><UiIcon name="building" /></span><strong>{selectedOrganization?.name ?? "Organizations"}</strong><b>›</b></button><nav aria-label="Administration">{primarySections.map(([id, label, icon]) => <button type="button" key={id} className={`${id === "create-setup" ? "create-action " : ""}${section === id ? "active" : ""}`} onClick={() => onSection(id)}><UiIcon name={icon} /><span>{label}</span></button>)}{selectedOrganization && <div className="contextual-nav"><span>Organization</span><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "overview" ? "active" : ""} onClick={() => chooseOrganizationTab("overview")}><UiIcon name="home" /><span>Overview</span></button><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "projects" ? "active" : ""} onClick={() => chooseOrganizationTab("projects")}><UiIcon name="project" /><span>Projects</span></button><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "members" ? "active" : ""} onClick={() => chooseOrganizationTab("members")}><UiIcon name="users" /><span>Members &amp; Roles</span></button></div>}{selectedProject && <div className="contextual-nav project-context-nav"><span>Project · {selectedProject.name}</span><button type="button" className={section === "organizations" && projectTab === "overview" ? "active" : ""} onClick={() => chooseProjectTab("overview")}><UiIcon name="home" /><span>Overview</span></button><button type="button" className={section === "organizations" && projectTab === "domains" ? "active" : ""} onClick={() => chooseProjectTab("domains")}><UiIcon name="domain" /><span>Domains</span></button><button type="button" className={section === "organizations" && projectTab === "agents" ? "active" : ""} onClick={() => chooseProjectTab("agents")}><UiIcon name="agent" /><span>Agents</span></button><button type="button" className={section === "organizations" && projectTab === "members" ? "active" : ""} onClick={() => chooseProjectTab("members")}><UiIcon name="users" /><span>Members &amp; Roles</span></button></div>}<details className="advanced-nav" open={advancedSections.some(([id]) => id === section && id !== "organizations")}><summary>Govern &amp; manage</summary>{advancedSections.filter(([id]) => id !== "organizations").map(([id, label, icon]) => <button type="button" key={id} className={section === id ? "active" : ""} onClick={() => onSection(id)}><UiIcon name={icon} /><span>{label}</span></button>)}</details></nav></aside><main><header className="topbar"><div><span className={`connection ${status}`}></span>Control Plane API {status}</div><div className="identity"><strong>{identity.user}</strong><span>{identity.roles.join(", ")}</span></div></header><ConsolePage section={section} identity={identity} api={api} organizationNavigation={organizationNavigation} /></main></div>;
}

export default function App({ authenticatedIdentity }: { authenticatedIdentity?: AdminIdentity }) {
  const [section, setSection] = useState("dashboard");
  const [status, setStatus] = useState("checking");
  const identity = useMemo<AdminIdentity>(() => authenticatedIdentity ?? ({
    user: import.meta.env.VITE_LOCAL_ADMIN_USER || "platform-admin@example.com",
    roles: [(import.meta.env.VITE_LOCAL_ADMIN_ROLE || "PLATFORM_ADMIN") as AdminRole],
    domains: String(import.meta.env.VITE_LOCAL_ADMIN_DOMAINS || "grocery,customer").split(",").map((value) => value.trim()).filter(Boolean),
  }), [authenticatedIdentity]);
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_CONTROL_PLANE_API_URL ?? "/control-plane-api/api/v1/admin", identity), [identity]);
  useEffect(() => { api.health().then((ok) => setStatus(ok ? "connected" : "unavailable")).catch(() => setStatus("unavailable")); }, [api]);
  return <ConsoleShell identity={identity} section={section} status={status} onSection={setSection} />;
}
