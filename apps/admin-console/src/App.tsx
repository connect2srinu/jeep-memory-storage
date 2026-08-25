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

function MemberForm({ title, onSave }: { title: string; onSave: (payload: AdminRecord) => Promise<void> }) {
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

  return <div className="compact-form"><h5>{title}</h5><label>Member email or principal<input value={principal} onChange={(event) => setPrincipal(event.target.value)} placeholder="owner@example.com" /></label><label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Optional" /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value)}><option>OWNER</option><option>ADMIN</option><option>VIEWER</option></select></label>{error && <div className="alert error">{error}</div>}<button className="primary" type="button" disabled={saving} onClick={submit}>{saving ? "Adding…" : "Add member"}</button></div>;
}

function ProjectForm({ organizationId, onSave }: { organizationId: string; onSave: (payload: AdminRecord) => Promise<void> }) {
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
  return <div className="compact-form project-form"><h5>Create project</h5><label>Project ID<input value={id} onChange={(event) => setId(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} placeholder="grocery-online" /></label><label>Project name<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Owning team<input value={ownerTeam} onChange={(event) => setOwnerTeam(event.target.value)} /></label><label className="wide">Description<input value={description} onChange={(event) => setDescription(event.target.value)} /></label>{error && <div className="alert error wide">{error}</div>}<button className="primary" type="button" onClick={submit}>Create project</button></div>;
}

function OrganizationForm({ onSave }: { onSave: (payload: AdminRecord) => Promise<void> }) {
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
  return <div className="organization-create"><div><span className="eyebrow">New line of business</span><h3>Create organization</h3><p>Organizations are the top-level tenant and Memory Bank scope boundary.</p></div><div className="compact-form"><label>Organization ID<input value={id} onChange={(event) => setId(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} placeholder="retail" /></label><label>Name<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Owner contact<input value={ownerContact} onChange={(event) => setOwnerContact(event.target.value)} /></label><label>Description<input value={description} onChange={(event) => setDescription(event.target.value)} /></label>{error && <div className="alert error wide">{error}</div>}<button className="primary" type="button" onClick={submit}>Create organization</button></div></div>;
}

export function OrganizationHierarchyView({ hierarchy, writable, api, reload }: { hierarchy: AdminRecord; writable: boolean; api: AdminApiClient; reload: () => void }) {
  const organizations = records(hierarchy, "organizations");
  if (!organizations.length) return <div><p className="empty">No organizations have been created.</p>{writable && <OrganizationForm onSave={async (payload) => { await api.create("organizations", payload); reload(); }} />}</div>;
  return <div className="organization-workspace">{writable && <OrganizationForm onSave={async (payload) => { await api.create("organizations", payload); reload(); }} />}<div className="organization-list">{organizations.map((organization) => {
    const organizationProjects = records(organization, "projects");
    const organizationMembers = records(organization, "members");
    return <article className="organization-card" key={value(organization, "id")}><header><div className="organization-monogram">{value(organization, "name").slice(0, 1).toUpperCase()}</div><div><span className="eyebrow">Organization</span><h3>{value(organization, "name")}</h3><p>{value(organization, "description") || "No description provided"}</p></div><span className={`pill ${value(organization, "status").toLowerCase()}`}>{value(organization, "status")}</span></header><div className="organization-meta"><span><b>{organizationProjects.length}</b> projects</span><span><b>{organizationMembers.length}</b> members</span><span><b>{organizationProjects.reduce((count, project) => count + records(project, "domains").length, 0)}</b> domains</span></div><section className="member-strip"><strong>Organization members</strong><div>{organizationMembers.length ? organizationMembers.map((member) => <span className="member-chip" key={value(member, "id")}><b>{value(member, "display_name") || value(member, "member_principal")}</b><small>{value(member, "role")}</small></span>) : <span className="empty">No members assigned</span>}</div></section><div className="project-group"><div className="group-heading"><div><span className="eyebrow">Project groups</span><h4>Projects in {value(organization, "name")}</h4></div></div>{organizationProjects.length ? organizationProjects.map((project) => <article className="project-card" key={value(project, "id")}><div className="project-summary"><div><h4>{value(project, "name")}</h4><p>{value(project, "description") || value(project, "id")}</p></div><span className="project-team">{value(project, "owner_team")}</span></div><div className="project-columns"><div><h5>Domains</h5><div className="domain-tags">{records(project, "domains").length ? records(project, "domains").map((domain) => <span key={value(domain, "id")}>{value(domain, "name")}</span>) : <small className="empty">No domains yet</small>}</div></div><div><h5>Project members</h5><div className="project-members">{records(project, "members").length ? records(project, "members").map((member) => <span key={value(member, "id")}><b>{value(member, "display_name") || value(member, "member_principal")}</b><small>{value(member, "role")}</small></span>) : <small className="empty">No direct project members</small>}</div></div></div>{writable && <details className="inline-action"><summary>+ Add project member</summary><MemberForm title={`Add member to ${value(project, "name")}`} onSave={async (payload) => { await api.addProjectMember(value(project, "id"), payload); reload(); }} /></details>}</article>) : <p className="empty project-empty">No projects in this organization.</p>}</div>{writable && <div className="organization-actions"><details><summary>+ Create project</summary><ProjectForm organizationId={value(organization, "id")} onSave={async (payload) => { await api.create("projects", payload); reload(); }} /></details><details><summary>+ Add organization member</summary><MemberForm title={`Add member to ${value(organization, "name")}`} onSave={async (payload) => { await api.addOrganizationMember(value(organization, "id"), payload); reload(); }} /></details></div>}</article>;
  })}</div></div>;
}

function OrganizationManagement({ identity, api }: { identity: AdminIdentity; api: AdminApiClient }) {
  const [hierarchy, setHierarchy] = useState<AdminRecord>({ organizations: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(() => { setLoading(true); api.organizationHierarchy().then(setHierarchy).catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load organization hierarchy")).finally(() => setLoading(false)); }, [api]);
  useEffect(reload, [reload]);
  return <section><div className="section-heading"><div><span className="eyebrow">Governance hierarchy</span><h2>Organizations &amp; Projects</h2><p>Manage line-of-business membership and group agents and domains into project boundaries.</p></div><button type="button" onClick={reload}>Refresh</button></div><ErrorBanner error={error} />{loading ? <p>Loading organization hierarchy…</p> : <OrganizationHierarchyView hierarchy={hierarchy} writable={canMutate(identity, "organizations")} api={api} reload={reload} />}</section>;
}

export function ConsolePage({ section, identity, api }: { section: string; identity: AdminIdentity; api: AdminApiClient }) {
  const resource = section === "approvals" ? "access-requests" : section;
  const [records, setRecords] = useState<AdminRecord[]>([]);
  const [loading, setLoading] = useState(!["dashboard", "create-setup"].includes(section));
  const [error, setError] = useState("");
  const title = sections.find(([id]) => id === section)?.[1] ?? section;
  const reload = useCallback(() => {
    if (["dashboard", "create-setup"].includes(section)) return;
    setLoading(true);
    api.list(resource).then(setRecords).catch((caught) => setError(caught instanceof Error ? caught.message : "Request failed")).finally(() => setLoading(false));
  }, [api, resource, section]);
  useEffect(reload, [api, resource, section]);
  if (section === "dashboard") return <section className="dashboard"><span className="eyebrow">Platform overview</span><h2>Governed memory, ready for every shopping journey</h2><p>Organize agents by line of business and project, reuse approved preference domains, and keep cross-project sharing read-only.</p><div className="metric-grid"><article><span className="metric-icon">O</span><strong>Organization</strong><span>Tenant and policy boundary</span></article><article><span className="metric-icon">P</span><strong>Projects</strong><span>Agent and domain collaboration</span></article><article><span className="metric-icon">M</span><strong>Memory Bank</strong><span>Profiles created lazily per user</span></article></div></section>;
  if (section === "create-setup") return <MemorySetupWizard api={api} />;
  if (section === "organizations") return <OrganizationManagement identity={identity} api={api} />;
  const writable = canMutate(identity, section);
  return <section><div className="section-heading"><div><span className="eyebrow">Control plane</span><h2>{title}</h2></div><button type="button" onClick={reload}>Refresh</button></div><ErrorBanner error={error} />{loading ? <p>Loading…</p> : section === "access-requests" || section === "approvals" ? <AccessActions records={records} api={api} reload={reload} approvalsOnly={section === "approvals"} /> : <ResourceTable records={records} />}{writable && templates[resource] && <JsonCreateForm resource={resource} onCreate={async (payload) => { await api.create(resource, payload); reload(); }} />}{!writable && <p className="read-only">Read-only for the selected role.</p>}</section>;
}

export function ConsoleShell({ identity, section, status, onSection }: { identity: AdminIdentity; section: string; status: string; onSection: (value: string) => void }) {
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_MEMORY_API_URL ?? "/memory-api/api/v1/admin", identity), [identity]);
  return <div className="app-shell"><aside><div className="brand"><span>GEAP</span><div><strong>Shared Memory</strong><small>Control plane</small></div></div><nav aria-label="Administration">{primarySections.map(([id, label]) => <button type="button" key={id} className={`${id === "create-setup" ? "create-action " : ""}${section === id ? "active" : ""}`} onClick={() => onSection(id)}>{label}</button>)}<details className="advanced-nav" open={advancedSections.some(([id]) => id === section)}><summary>Govern &amp; manage</summary>{advancedSections.map(([id, label]) => <button type="button" key={id} className={section === id ? "active" : ""} onClick={() => onSection(id)}>{label}</button>)}</details></nav></aside><main><header className="topbar"><div><span className={`connection ${status}`}></span>Memory API {status}</div><div className="identity"><strong>{identity.user}</strong><span>{identity.roles.join(", ")}</span></div></header><ConsolePage section={section} identity={identity} api={api} /></main></div>;
}

export default function App() {
  const [section, setSection] = useState("create-setup");
  const [status, setStatus] = useState("checking");
  const [user, setUser] = useState("platform-admin@example.com");
  const [role, setRole] = useState<AdminRole>("PLATFORM_ADMIN");
  const [domains, setDomains] = useState("grocery,customer");
  const identity = useMemo<AdminIdentity>(() => ({ user, roles: [role], domains: domains.split(",").map((value) => value.trim()).filter(Boolean) }), [user, role, domains]);
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_MEMORY_API_URL ?? "/memory-api/api/v1/admin", identity), [identity]);
  useEffect(() => { api.health().then((ok) => setStatus(ok ? "connected" : "unavailable")).catch(() => setStatus("unavailable")); }, [api]);
  return <><div className="persona"><label>User<input value={user} onChange={(event) => setUser(event.target.value)} /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as AdminRole)}><option>PLATFORM_ADMIN</option><option>DOMAIN_ADMIN</option><option>SCHEMA_OWNER</option><option>AGENT_OWNER</option><option>VIEWER</option></select></label><label>Domains<input value={domains} onChange={(event) => setDomains(event.target.value)} /></label></div><ConsoleShell identity={identity} section={section} status={status} onSection={setSection} /></>;
}
