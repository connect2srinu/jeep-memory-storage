import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminApiClient, AdminApiError } from "./api";
import { canMutate, findNormalizedDuplicates, movePriority, recordId } from "./governance";
import type { AdminIdentity, AdminRecord, AdminRole } from "./types";
import { MemorySetupWizard } from "./Wizard";

const primarySections = [
  ["dashboard", "Dashboard"],
  ["create-setup", "Create Memory Setup"],
] as const;

const advancedSections = [
  ["organizations", "Organizations & Projects"],
  ["domains", "Domains"],
  ["scopes", "Scopes"],
  ["schemas", "Schemas"],
  ["preference-catalog", "Preference Catalog"],
  ["agents", "Agents"],
  ["access-requests", "Access Requests"],
  ["approvals", "Approvals"],
  ["resolution-policies", "Resolution Policies"],
  ["dynamic-memory-policies", "Dynamic Memory Policies"],
  ["audit", "Audit"],
] as const;

const sections = [...primarySections, ...advancedSections] as const;

const templates: Record<string, AdminRecord> = {
  organizations: {
    id: "retail",
    name: "Retail",
    description: "Retail line of business",
    ownerContact: "retail-platform@example.com",
  },
  projects: {
    id: "rewards-experience",
    organizationId: "retail",
    name: "Rewards Experience",
    description: "Rewards personalization agents and domains",
    ownerTeam: "rewards-team",
  },
  domains: {
    id: "rewards",
    organizationId: "retail",
    projectId: "rewards-experience",
    name: "Rewards",
    description: "",
    ownerTeam: "rewards-team",
  },
  scopes: {
    id: "rewards:profile-scope",
    scopeType: "DOMAIN_PROFILE",
    scopeKeys: ["organization_id", "user_id"],
    ownerDomainId: "rewards",
  },
  "preference-catalog": {
    attributeId: "rewards.preferred_reward",
    displayName: "Preferred Reward",
    description: "Preferred reward",
    dataType: "string",
    sensitivityClassification: "normal",
    canonicalOwnerId: "rewards",
  },
  schemas: {
    id: "rewards-preferences-v1",
    domainId: "rewards",
    displayName: "Rewards Preferences",
    ownerTeam: "rewards-team",
    version: "1",
    scopeDefinitionId: "rewards:profile-scope",
    vertexSchemaDefinition: {
      type: "object",
      properties: { preferred_reward: { type: "string" } },
    },
    generationConfig: {},
    mappings: [
      { attributeId: "rewards.preferred_reward", profileField: "preferred_reward" },
    ],
  },
  agents: {
    id: "rewards-agent",
    displayName: "Rewards Agent",
    organizationId: "retail",
    projectId: "rewards-experience",
    domainId: "rewards",
    runtimeType: "ADK_CLOUD_RUN",
    identityType: "GOOGLE_SERVICE_ACCOUNT",
    capabilities: { resolve_context: true, submit_candidates: true },
  },
  "access-requests": {
    requestingAgentId: "rewards-agent",
    requestingTeam: "rewards-team",
    targetSchemaId: "customer-preferences-v1",
    requestedPermission: "READ",
    businessReason: "Customer-aware rewards experience",
  },
  "resolution-policies": {
    id: "rewards-policy-v1",
    agentId: "rewards-agent",
    name: "Rewards policy",
    version: "1",
    defaultRules: { strategy: "DOMAIN_AUTHORITY" },
    schemaPriorities: [
      { schemaId: "rewards-preferences-v1", priority: 0 },
      { schemaId: "customer-preferences-v1", priority: 1 },
    ],
    attributeOverrides: [],
  },
  "dynamic-memory-policies": {
    id: "rewards-dynamic-v1",
    level: "DOMAIN",
    domainId: "rewards",
    confidenceThreshold: 0.8,
  },
};

function parseJson(value: string): AdminRecord {
  const parsed: unknown = JSON.parse(value);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("JSON must contain an object");
  }
  return parsed as AdminRecord;
}

function ErrorBanner({ error }: { error: string }) {
  return error ? <div className="alert error" role="alert">{error}</div> : null;
}

function ResourceTable({ records }: { records: AdminRecord[] }) {
  if (!records.length) return <p className="empty">No records found.</p>;
  const columns = Object.keys(records[0]).filter(
    (key) => !["created_at", "updated_at", "before_metadata", "after_metadata"].includes(key),
  );
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead>
        <tbody>{records.map((record, index) => (
          <tr key={recordId(record) || index}>{columns.map((column) => (
            <td key={column}>{typeof record[column] === "object" ? JSON.stringify(record[column]) : String(record[column] ?? "—")}</td>
          ))}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function JsonCreateForm({ resource, onCreate }: { resource: string; onCreate: (value: AdminRecord) => Promise<void> }) {
  const [value, setValue] = useState(JSON.stringify(templates[resource] ?? {}, null, 2));
  const [error, setError] = useState("");
  useEffect(() => {
    setValue(JSON.stringify(templates[resource] ?? {}, null, 2));
    setError("");
  }, [resource]);
  const parsed = useMemo(() => {
    try { return parseJson(value); } catch { return null; }
  }, [value]);
  const mappingNames = resource === "schemas" && parsed && Array.isArray(parsed.mappings)
    ? parsed.mappings.flatMap((item) => {
        const mapping = item as Record<string, unknown>;
        return [String(mapping.attributeId ?? ""), String(mapping.profileField ?? "")];
      })
    : [];
  const duplicates = findNormalizedDuplicates(mappingNames);

  async function submit() {
    try {
      if (duplicates.length) throw new Error(`Normalized duplicates: ${duplicates.join(", ")}`);
      await onCreate(parseJson(value));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create record");
    }
  }

  return (
    <section className="editor">
      <div><h3>Create</h3><p>Review the governed payload before submitting.</p></div>
      <textarea aria-label={`Create ${resource} JSON`} value={value} onChange={(event) => setValue(event.target.value)} />
      {duplicates.length > 0 && <div className="alert warning">Duplicate normalized fields: {duplicates.join(", ")}</div>}
      {resource === "schemas" && parsed && <details><summary>Schema preview</summary><pre>{JSON.stringify(parsed.vertexSchemaDefinition, null, 2)}</pre></details>}
      {resource === "resolution-policies" && parsed && <PriorityEditor payload={parsed} onChange={(next) => setValue(JSON.stringify(next, null, 2))} />}
      <ErrorBanner error={error} />
      <button className="primary" type="button" onClick={submit}>Create governed record</button>
    </section>
  );
}

function PriorityEditor({ payload, onChange }: { payload: AdminRecord; onChange: (value: AdminRecord) => void }) {
  const items = Array.isArray(payload.schemaPriorities) ? payload.schemaPriorities as AdminRecord[] : [];
  function move(index: number, direction: -1 | 1) {
    const reordered = movePriority(items, index, direction).map((item, priority) => ({ ...item, priority }));
    onChange({ ...payload, schemaPriorities: reordered });
  }
  return <div className="priorities"><strong>Schema priority</strong>{items.map((item, index) => (
    <div key={String(item.schemaId)}><span>{index + 1}. {String(item.schemaId)}</span><span><button type="button" onClick={() => move(index, -1)} aria-label={`Move ${String(item.schemaId)} up`}>↑</button><button type="button" onClick={() => move(index, 1)} aria-label={`Move ${String(item.schemaId)} down`}>↓</button></span></div>
  ))}</div>;
}

function AccessActions({ records, api, reload, approvalsOnly }: { records: AdminRecord[]; api: AdminApiClient; reload: () => void; approvalsOnly: boolean }) {
  const visible = approvalsOnly ? records.filter((record) => record.status === "PENDING") : records;
  async function act(id: string, action: "approve" | "reject" | "revoke" | "expire") {
    await api.decideAccess(id, action, `${action} from Admin Console`);
    reload();
  }
  return <div className="request-list">{visible.map((record) => <article key={recordId(record)}>
    <div><strong>{String(record.requesting_agent_id)}</strong> → {String(record.target_schema_id)}<p>{String(record.business_reason)}</p></div>
    <span className={`pill ${String(record.status).toLowerCase()}`}>{String(record.status)}</span>
    <div className="actions">{record.status === "PENDING" && <><button type="button" onClick={() => act(recordId(record), "approve")}>Approve</button><button className="danger" type="button" onClick={() => act(recordId(record), "reject")}>Reject</button></>}{record.status === "APPROVED" && <button className="danger" type="button" onClick={() => act(recordId(record), "revoke")}>Revoke</button>}</div>
  </article>)}</div>;
}

function value(record: AdminRecord, key: string): string {
  return String(record[key] ?? "");
}

function records(record: AdminRecord, key: string): AdminRecord[] {
  return Array.isArray(record[key]) ? record[key] as AdminRecord[] : [];
}

type OrganizationTab = "overview" | "projects" | "members";
type ProjectTab = "overview" | "domains" | "agents" | "members";
type ContextSelection = { id: string; name: string } | null;

function MemberForm({ title, onSave, onCancel }: { title: string; onSave: (payload: AdminRecord) => Promise<void>; onCancel?: () => void }) {
  const [principal, setPrincipal] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState("VIEWER");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!principal.trim()) { setError("Member email or principal is required."); return; }
    setSaving(true);
    try {
      await onSave({ memberPrincipal: principal, displayName: displayName || undefined, role });
      setPrincipal("");
      setDisplayName("");
      setRole("VIEWER");
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to add member");
    } finally { setSaving(false); }
  }

  return <div className="compact-form"><h5>{title}</h5><label>Member email or principal<input value={principal} onChange={(event) => setPrincipal(event.target.value)} placeholder="owner@example.com" /></label><label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Optional" /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value)}><option>OWNER</option><option>ADMIN</option><option>VIEWER</option></select></label>{error && <div className="alert error wide">{error}</div>}<div className="form-actions wide">{onCancel && <button className="secondary" type="button" onClick={onCancel}>Cancel</button>}<button className="primary" type="button" disabled={saving} onClick={submit}>{saving ? "Adding…" : "Add member"}</button></div></div>;
}

function ProjectForm({ organizationId, onSave, onCancel }: { organizationId: string; onSave: (payload: AdminRecord) => Promise<void>; onCancel?: () => void }) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ownerTeam, setOwnerTeam] = useState("");
  const [error, setError] = useState("");
  async function submit() {
    if (!id || !name || !ownerTeam) { setError("Project ID, name, and owning team are required."); return; }
    try {
      await onSave({ id, organizationId, name, description, ownerTeam });
      setId(""); setName(""); setDescription(""); setOwnerTeam(""); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to create project"); }
  }
  return <div className="compact-form project-form"><h5>Create project</h5><label>Project ID<input value={id} onChange={(event) => setId(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} placeholder="grocery-online" /></label><label>Project name<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Owning team<input value={ownerTeam} onChange={(event) => setOwnerTeam(event.target.value)} /></label><label className="wide">Description<input value={description} onChange={(event) => setDescription(event.target.value)} /></label>{error && <div className="alert error wide">{error}</div>}<div className="form-actions wide">{onCancel && <button className="secondary" type="button" onClick={onCancel}>Cancel</button>}<button className="primary" type="button" onClick={submit}>Create project</button></div></div>;
}

function OrganizationForm({ onSave, onCancel }: { onSave: (payload: AdminRecord) => Promise<void>; onCancel?: () => void }) {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ownerContact, setOwnerContact] = useState("");
  const [error, setError] = useState("");
  async function submit() {
    if (!id || !name) { setError("Organization ID and name are required."); return; }
    try {
      await onSave({ id, name, description, ownerContact: ownerContact || undefined });
      setId(""); setName(""); setDescription(""); setOwnerContact(""); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to create organization"); }
  }
  return <div className="organization-create"><div><span className="eyebrow">New line of business</span><h3>Create organization</h3><p>Organizations are immediately active in this POC and become the top-level Memory Bank scope boundary.</p></div><div className="compact-form"><label>Organization ID<input value={id} onChange={(event) => setId(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} placeholder="retail" /></label><label>Name<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Owner contact<input value={ownerContact} onChange={(event) => setOwnerContact(event.target.value)} /></label><label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} /></label>{error && <div className="alert error wide">{error}</div>}<div className="form-actions wide">{onCancel && <button className="secondary" type="button" onClick={onCancel}>Cancel</button>}<button className="primary" type="button" onClick={submit}>Create organization</button></div></div></div>;
}

function ContextTabs<T extends string>({ tabs, selected, onSelect }: { tabs: Array<[T, string]>; selected: T; onSelect: (tab: T) => void }) {
  return <div className="context-tabs" role="tablist">{tabs.map(([id, label]) => <button type="button" role="tab" aria-selected={selected === id} className={selected === id ? "active" : ""} key={id} onClick={() => onSelect(id)}>{label}</button>)}</div>;
}

type OrganizationHierarchyViewProps = {
  hierarchy: AdminRecord;
  writable: boolean;
  api: AdminApiClient;
  reload: () => Promise<void> | void;
  selectedOrganization?: ContextSelection;
  selectedProject?: ContextSelection;
  organizationTab?: OrganizationTab;
  projectTab?: ProjectTab;
  onSelectOrganization?: (organization: ContextSelection) => void;
  onSelectProject?: (project: ContextSelection) => void;
  onOrganizationTab?: (tab: OrganizationTab) => void;
  onProjectTab?: (tab: ProjectTab) => void;
};

export function OrganizationHierarchyView({ hierarchy, writable, api, reload, selectedOrganization = null, selectedProject = null, organizationTab = "projects", projectTab = "overview", onSelectOrganization = () => {}, onSelectProject = () => {}, onOrganizationTab = () => {}, onProjectTab = () => {} }: OrganizationHierarchyViewProps) {
  const organizations = records(hierarchy, "organizations");
  const [showOrganizationForm, setShowOrganizationForm] = useState(false);
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [showMemberForm, setShowMemberForm] = useState(false);

  if (!selectedOrganization) {
    return <div className="organization-directory"><div className="section-heading"><div><span className="eyebrow">Organizations</span><h2>Organizations</h2><p>Choose a line of business to manage its projects, members, domains, and agents.</p></div>{writable && <button className="primary" type="button" onClick={() => setShowOrganizationForm(true)}>+ Create organization</button>}</div>{showOrganizationForm && <OrganizationForm onCancel={() => setShowOrganizationForm(false)} onSave={async (payload) => { const created = await api.create("organizations", payload); await reload(); setShowOrganizationForm(false); onSelectOrganization({ id: value(created, "id"), name: value(created, "name") }); }} />}{organizations.length ? <div className="organization-directory-grid">{organizations.map((organization) => { const projects = records(organization, "projects"); const members = records(organization, "members"); return <button className="organization-directory-card" type="button" key={value(organization, "id")} onClick={() => onSelectOrganization({ id: value(organization, "id"), name: value(organization, "name") })}><span className="organization-monogram">{value(organization, "name").slice(0, 1).toUpperCase()}</span><span className="directory-card-body"><strong>{value(organization, "name")}</strong><small>{value(organization, "id")}</small><span><b>{projects.length}</b> projects <b>{members.length}</b> members</span></span><span className="directory-arrow">›</span></button>; })}</div> : <div className="empty-state"><strong>No organizations yet</strong><p>Create the first organization to establish a project and Memory Bank governance boundary.</p></div>}</div>;
  }

  const organization = organizations.find((item) => value(item, "id") === selectedOrganization.id);
  if (!organization) return <div className="empty-state"><strong>Organization not found</strong><button type="button" className="secondary" onClick={() => onSelectOrganization(null)}>Return to organizations</button></div>;
  const organizationProjects = records(organization, "projects");
  const organizationMembers = records(organization, "members");
  const project = selectedProject ? organizationProjects.find((item) => value(item, "id") === selectedProject.id) : undefined;

  if (project) {
    const projectDomains = records(project, "domains");
    const projectMembers = records(project, "members");
    const projectAgents = records(project, "agents");
    return <div className="context-workspace"><button className="back-link" type="button" onClick={() => onSelectProject(null)}>← {value(organization, "name")}</button><div className="context-header"><div className="organization-monogram project-monogram">P</div><div><span className="eyebrow">Project</span><h2>{value(project, "name")}</h2><p>{value(project, "description") || value(project, "id")}</p></div><span className="project-team">{value(project, "owner_team")}</span></div><ContextTabs tabs={[["overview", "Overview"], ["domains", "Domains"], ["agents", "Agents"], ["members", "Members & Roles"]]} selected={projectTab} onSelect={onProjectTab} />{projectTab === "overview" && <div className="overview-grid"><article><span>Domains</span><strong>{projectDomains.length}</strong><p>Preference ownership boundaries</p></article><article><span>Agents</span><strong>{projectAgents.length}</strong><p>Registered project consumers</p></article><article><span>Members</span><strong>{projectMembers.length}</strong><p>Direct project assignments</p></article></div>}{projectTab === "domains" && <div className="resource-card-grid">{projectDomains.length ? projectDomains.map((domain) => <article key={value(domain, "id")}><span className="resource-icon">D</span><div><strong>{value(domain, "name")}</strong><small>{value(domain, "id")}</small></div></article>) : <p className="empty">No domains have been created in this project.</p>}</div>}{projectTab === "agents" && <div className="resource-card-grid">{projectAgents.length ? projectAgents.map((agent) => <article key={value(agent, "id")}><span className="resource-icon">A</span><div><strong>{value(agent, "display_name")}</strong><small>{value(agent, "id")}</small></div></article>) : <p className="empty">No agents are registered in this project.</p>}</div>}{projectTab === "members" && <div className="membership-panel"><div className="panel-heading"><div><h3>Project members</h3><p>Direct roles apply only inside this project.</p></div>{writable && <button className="primary" type="button" onClick={() => setShowMemberForm(true)}>+ Add member</button>}</div>{showMemberForm && <MemberForm title={`Add member to ${value(project, "name")}`} onCancel={() => setShowMemberForm(false)} onSave={async (payload) => { await api.addProjectMember(value(project, "id"), payload); await reload(); setShowMemberForm(false); }} />}<div className="member-list">{projectMembers.length ? projectMembers.map((member) => <div key={value(member, "id")}><span className="member-avatar">{(value(member, "display_name") || value(member, "member_principal")).slice(0, 1).toUpperCase()}</span><span><strong>{value(member, "display_name") || value(member, "member_principal")}</strong><small>{value(member, "member_principal")}</small></span><span className="role-badge">{value(member, "role")}</span></div>) : <p className="empty">No direct project members.</p>}</div></div>}</div>;
  }

  return <div className="context-workspace"><button className="back-link" type="button" onClick={() => onSelectOrganization(null)}>← Organizations</button><div className="context-header"><div className="organization-monogram">{value(organization, "name").slice(0, 1).toUpperCase()}</div><div><span className="eyebrow">Organization</span><h2>{value(organization, "name")}</h2><p>{value(organization, "description") || value(organization, "id")}</p></div><span className="role-badge">Organization active</span></div><ContextTabs tabs={[["overview", "Overview"], ["projects", "Projects"], ["members", "Members & Roles"]]} selected={organizationTab} onSelect={onOrganizationTab} />{organizationTab === "overview" && <div className="overview-grid"><article><span>Projects</span><strong>{organizationProjects.length}</strong><p>Collaboration boundaries</p></article><article><span>Members</span><strong>{organizationMembers.length}</strong><p>Organization-level access</p></article><article><span>Domains</span><strong>{organizationProjects.reduce((count, item) => count + records(item, "domains").length, 0)}</strong><p>Owned memory domains</p></article></div>}{organizationTab === "projects" && <div className="organization-panel"><div className="panel-heading"><div><h3>Projects</h3><p>Agents in a project collaborate through project-owned domains.</p></div>{writable && <button className="primary" type="button" onClick={() => setShowProjectForm(true)}>+ New project</button>}</div>{showProjectForm && <div className="panel-form"><ProjectForm organizationId={value(organization, "id")} onCancel={() => setShowProjectForm(false)} onSave={async (payload) => { await api.create("projects", payload); await reload(); setShowProjectForm(false); }} /></div>}<div className="project-directory-grid">{organizationProjects.length ? organizationProjects.map((item) => <article className="project-directory-card" key={value(item, "id")}><span className="resource-icon">P</span><div><h4>{value(item, "name")}</h4><p>{value(item, "description") || value(item, "id")}</p><small>{records(item, "domains").length} domains · {records(item, "members").length} members</small></div><button className="primary" type="button" onClick={() => onSelectProject({ id: value(item, "id"), name: value(item, "name") })}>Open project ›</button></article>) : <p className="empty project-empty">No projects in this organization.</p>}</div></div>}{organizationTab === "members" && <div className="membership-panel"><div className="panel-heading"><div><h3>Members & Roles</h3><p>Organization members can be assigned to projects in this organization.</p></div>{writable && <button className="primary" type="button" onClick={() => setShowMemberForm(true)}>+ Add member</button>}</div>{showMemberForm && <MemberForm title={`Add member to ${value(organization, "name")}`} onCancel={() => setShowMemberForm(false)} onSave={async (payload) => { await api.addOrganizationMember(value(organization, "id"), payload); await reload(); setShowMemberForm(false); }} />}<div className="member-list">{organizationMembers.length ? organizationMembers.map((member) => <div key={value(member, "id")}><span className="member-avatar">{(value(member, "display_name") || value(member, "member_principal")).slice(0, 1).toUpperCase()}</span><span><strong>{value(member, "display_name") || value(member, "member_principal")}</strong><small>{value(member, "member_principal")}</small></span><span className="role-badge">{value(member, "role")}</span></div>) : <p className="empty">No members assigned.</p>}</div></div>}</div>;
}

function OrganizationManagement({ identity, api, selectedOrganization, selectedProject, organizationTab, projectTab, onSelectOrganization, onSelectProject, onOrganizationTab, onProjectTab }: { identity: AdminIdentity; api: AdminApiClient; selectedOrganization: ContextSelection; selectedProject: ContextSelection; organizationTab: OrganizationTab; projectTab: ProjectTab; onSelectOrganization: (organization: ContextSelection) => void; onSelectProject: (project: ContextSelection) => void; onOrganizationTab: (tab: OrganizationTab) => void; onProjectTab: (tab: ProjectTab) => void }) {
  const [hierarchy, setHierarchy] = useState<AdminRecord>({ organizations: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => { setLoading(true); try { setHierarchy(await api.organizationHierarchy()); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load organization hierarchy"); } finally { setLoading(false); } }, [api]);
  useEffect(() => { void reload(); }, [reload]);
  return <section><ErrorBanner error={error} />{loading ? <p>Loading organization hierarchy…</p> : <OrganizationHierarchyView hierarchy={hierarchy} writable={canMutate(identity, "organizations")} api={api} reload={reload} selectedOrganization={selectedOrganization} selectedProject={selectedProject} organizationTab={organizationTab} projectTab={projectTab} onSelectOrganization={onSelectOrganization} onSelectProject={onSelectProject} onOrganizationTab={onOrganizationTab} onProjectTab={onProjectTab} />}</section>;
}

type OrganizationNavigation = {
  selectedOrganization: ContextSelection;
  selectedProject: ContextSelection;
  organizationTab: OrganizationTab;
  projectTab: ProjectTab;
  onSelectOrganization: (organization: ContextSelection) => void;
  onSelectProject: (project: ContextSelection) => void;
  onOrganizationTab: (tab: OrganizationTab) => void;
  onProjectTab: (tab: ProjectTab) => void;
};

const defaultOrganizationNavigation: OrganizationNavigation = {
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
  const [loading, setLoading] = useState(!["dashboard", "create-setup", "organizations"].includes(section));
  const [error, setError] = useState("");
  const title = sections.find(([id]) => id === section)?.[1] ?? section;
  const reload = useCallback(() => {
    if (["dashboard", "create-setup", "organizations"].includes(section)) return;
    setLoading(true);
    api.list(resource).then(setRecords).catch((caught) => setError(caught instanceof Error ? caught.message : "Request failed")).finally(() => setLoading(false));
  }, [api, resource, section]);
  useEffect(reload, [api, resource, section]);
  if (section === "dashboard") return <section className="dashboard"><span className="eyebrow">Platform overview</span><h2>Governed memory, ready for every shopping journey</h2><p>Organize agents by line of business and project, reuse approved preference domains, and keep cross-project sharing read-only.</p><div className="metric-grid"><article><span className="metric-icon">O</span><strong>Organization</strong><span>Tenant and policy boundary</span></article><article><span className="metric-icon">P</span><strong>Projects</strong><span>Agent and domain collaboration</span></article><article><span className="metric-icon">M</span><strong>Memory Bank</strong><span>Profiles created lazily per user</span></article></div></section>;
  if (section === "create-setup") return <MemorySetupWizard api={api} />;
  if (section === "organizations") return <OrganizationManagement identity={identity} api={api} {...organizationNavigation} />;
  const writable = canMutate(identity, section);
  return <section><div className="section-heading"><div><span className="eyebrow">Control plane</span><h2>{title}</h2></div><button type="button" onClick={reload}>Refresh</button></div><ErrorBanner error={error} />{loading ? <p>Loading…</p> : section === "access-requests" || section === "approvals" ? <AccessActions records={records} api={api} reload={reload} approvalsOnly={section === "approvals"} /> : <ResourceTable records={records} />}{writable && templates[resource] && <JsonCreateForm resource={resource} onCreate={async (payload) => { await api.create(resource, payload); reload(); }} />}{!writable && <p className="read-only">Read-only for the selected role.</p>}</section>;
}

export function ConsoleShell({ identity, section, status, onSection }: { identity: AdminIdentity; section: string; status: string; onSection: (value: string) => void }) {
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_MEMORY_API_URL ?? "/memory-api/api/v1/admin", identity), [identity]);
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
  return <div className="app-shell"><aside><div className="brand"><span>GEAP</span><div><strong>Shared Memory</strong><small>Control plane</small></div></div><button className="context-switcher" type="button" onClick={openOrganizations}><span>{selectedOrganization ? selectedOrganization.name.slice(0, 1).toUpperCase() : "O"}</span><strong>{selectedOrganization?.name ?? "Organizations"}</strong><b>›</b></button><nav aria-label="Administration">{primarySections.map(([id, label]) => <button type="button" key={id} className={`${id === "create-setup" ? "create-action " : ""}${section === id ? "active" : ""}`} onClick={() => onSection(id)}>{label}</button>)}{selectedOrganization && <div className="contextual-nav"><span>Organization</span><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "overview" ? "active" : ""} onClick={() => chooseOrganizationTab("overview")}>Overview</button><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "projects" ? "active" : ""} onClick={() => chooseOrganizationTab("projects")}>Projects</button><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "members" ? "active" : ""} onClick={() => chooseOrganizationTab("members")}>Members &amp; Roles</button></div>}{selectedProject && <div className="contextual-nav project-context-nav"><span>Project · {selectedProject.name}</span><button type="button" className={section === "organizations" && projectTab === "overview" ? "active" : ""} onClick={() => chooseProjectTab("overview")}>Overview</button><button type="button" className={section === "organizations" && projectTab === "domains" ? "active" : ""} onClick={() => chooseProjectTab("domains")}>Domains</button><button type="button" className={section === "organizations" && projectTab === "agents" ? "active" : ""} onClick={() => chooseProjectTab("agents")}>Agents</button><button type="button" className={section === "organizations" && projectTab === "members" ? "active" : ""} onClick={() => chooseProjectTab("members")}>Members &amp; Roles</button></div>}<details className="advanced-nav" open={advancedSections.some(([id]) => id === section && id !== "organizations")}><summary>Govern &amp; manage</summary>{advancedSections.filter(([id]) => id !== "organizations").map(([id, label]) => <button type="button" key={id} className={section === id ? "active" : ""} onClick={() => onSection(id)}>{label}</button>)}</details></nav></aside><main><header className="topbar"><div><span className={`connection ${status}`}></span>Memory API {status}</div><div className="identity"><strong>{identity.user}</strong><span>{identity.roles.join(", ")}</span></div></header><ConsolePage section={section} identity={identity} api={api} organizationNavigation={organizationNavigation} /></main></div>;
}

export default function App() {
  const [section, setSection] = useState("organizations");
  const [status, setStatus] = useState("checking");
  const [user, setUser] = useState("platform-admin@example.com");
  const [role, setRole] = useState<AdminRole>("PLATFORM_ADMIN");
  const [domains, setDomains] = useState("grocery,customer");
  const identity = useMemo<AdminIdentity>(() => ({ user, roles: [role], domains: domains.split(",").map((value) => value.trim()).filter(Boolean) }), [user, role, domains]);
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_MEMORY_API_URL ?? "/memory-api/api/v1/admin", identity), [identity]);
  useEffect(() => { api.health().then((ok) => setStatus(ok ? "connected" : "unavailable")).catch(() => setStatus("unavailable")); }, [api]);
  return <><div className="persona"><label>User<input value={user} onChange={(event) => setUser(event.target.value)} /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as AdminRole)}><option>PLATFORM_ADMIN</option><option>DOMAIN_ADMIN</option><option>SCHEMA_OWNER</option><option>AGENT_OWNER</option><option>VIEWER</option></select></label><label>Domains<input value={domains} onChange={(event) => setDomains(event.target.value)} /></label></div><ConsoleShell identity={identity} section={section} status={status} onSection={setSection} /></>;
}
