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
  ["organizations", "Organizations"],
  ["projects", "Projects"],
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
