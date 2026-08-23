import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminApiClient, AdminApiError } from "./api";
import { canMutate, findNormalizedDuplicates, movePriority, recordId } from "./governance";
import type { AdminIdentity, AdminRecord, AdminRole } from "./types";

const sections = [
  ["dashboard", "Dashboard"],
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

const templates: Record<string, AdminRecord> = {
  domains: { id: "loyalty", name: "Loyalty", description: "", ownerTeam: "loyalty-team" },
  scopes: {
    id: "loyalty:profile-scope",
    scopeType: "DOMAIN_PROFILE",
    scopeKeys: ["user_id", "app_name"],
    ownerDomainId: "loyalty",
  },
  "preference-catalog": {
    attributeId: "loyalty.preferred_reward",
    displayName: "Preferred Reward",
    description: "Preferred loyalty reward",
    dataType: "string",
    sensitivityClassification: "normal",
    canonicalOwnerId: "loyalty",
  },
  schemas: {
    id: "loyalty-preferences-v1",
    domainId: "loyalty",
    displayName: "Loyalty Preferences",
    ownerTeam: "loyalty-team",
    version: "1",
    scopeDefinitionId: "loyalty:profile-scope",
    vertexSchemaDefinition: {
      type: "object",
      properties: { preferred_reward: { type: "string" } },
    },
    generationConfig: {},
    mappings: [
      { attributeId: "loyalty.preferred_reward", profileField: "preferred_reward" },
    ],
  },
  agents: {
    id: "loyalty-agent",
    displayName: "Loyalty Agent",
    domainId: "loyalty",
    runtimeType: "ADK_CLOUD_RUN",
    identityType: "GOOGLE_SERVICE_ACCOUNT",
    capabilities: { resolve_context: true, submit_candidates: true },
  },
  "access-requests": {
    requestingAgentId: "loyalty-agent",
    requestingTeam: "loyalty-team",
    targetSchemaId: "customer-preferences-v1",
    requestedPermission: "READ",
    businessReason: "Customer-aware loyalty experience",
  },
  "resolution-policies": {
    id: "loyalty-policy-v1",
    agentId: "loyalty-agent",
    name: "Loyalty policy",
    version: "1",
    defaultRules: { strategy: "DOMAIN_AUTHORITY" },
    schemaPriorities: [
      { schemaId: "loyalty-preferences-v1", priority: 0 },
      { schemaId: "customer-preferences-v1", priority: 1 },
    ],
    attributeOverrides: [],
  },
  "dynamic-memory-policies": {
    id: "loyalty-dynamic-v1",
    level: "DOMAIN",
    domainId: "loyalty",
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
  const [loading, setLoading] = useState(section !== "dashboard");
  const [error, setError] = useState("");
  const title = sections.find(([id]) => id === section)?.[1] ?? section;
  const reload = useCallback(() => {
    if (section === "dashboard") return;
    setLoading(true);
    api.list(resource).then(setRecords).catch((caught) => setError(caught instanceof Error ? caught.message : "Request failed")).finally(() => setLoading(false));
  }, [api, resource, section]);
  useEffect(reload, [api, resource, section]);
  if (section === "dashboard") return <section><h2>Governed memory control plane</h2><p>Create domain contracts, approve least-privilege access, and inspect every control-plane change from one console.</p><div className="metric-grid"><article><strong>11</strong><span>Administration areas</span></article><article><strong>5</strong><span>RBAC roles</span></article><article><strong>1</strong><span>Memory API boundary</span></article></div></section>;
  const writable = canMutate(identity, section);
  return <section><div className="section-heading"><div><span className="eyebrow">Control plane</span><h2>{title}</h2></div><button type="button" onClick={reload}>Refresh</button></div><ErrorBanner error={error} />{loading ? <p>Loading…</p> : section === "access-requests" || section === "approvals" ? <AccessActions records={records} api={api} reload={reload} approvalsOnly={section === "approvals"} /> : <ResourceTable records={records} />}{writable && templates[resource] && <JsonCreateForm resource={resource} onCreate={async (payload) => { await api.create(resource, payload); reload(); }} />}{!writable && <p className="read-only">Read-only for the selected role.</p>}</section>;
}

export function ConsoleShell({ identity, section, status, onSection }: { identity: AdminIdentity; section: string; status: string; onSection: (value: string) => void }) {
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_MEMORY_API_URL ?? "/memory-api/api/v1/admin", identity), [identity]);
  return <div className="app-shell"><aside><div className="brand"><span>GEAP</span><strong>Memory Admin</strong></div><nav aria-label="Administration">{sections.map(([id, label]) => <button type="button" key={id} className={section === id ? "active" : ""} onClick={() => onSection(id)}>{label}</button>)}</nav></aside><main><header className="topbar"><div><span className={`connection ${status}`}></span>Memory API {status}</div><div className="identity"><strong>{identity.user}</strong><span>{identity.roles.join(", ")}</span></div></header><ConsolePage section={section} identity={identity} api={api} /></main></div>;
}

export default function App() {
  const [section, setSection] = useState("dashboard");
  const [status, setStatus] = useState("checking");
  const [user, setUser] = useState("platform-admin@example.com");
  const [role, setRole] = useState<AdminRole>("PLATFORM_ADMIN");
  const [domains, setDomains] = useState("grocery,customer");
  const identity = useMemo<AdminIdentity>(() => ({ user, roles: [role], domains: domains.split(",").map((value) => value.trim()).filter(Boolean) }), [user, role, domains]);
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_MEMORY_API_URL ?? "/memory-api/api/v1/admin", identity), [identity]);
  useEffect(() => { api.health().then((ok) => setStatus(ok ? "connected" : "unavailable")).catch(() => setStatus("unavailable")); }, [api]);
  return <><div className="persona"><label>User<input value={user} onChange={(event) => setUser(event.target.value)} /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as AdminRole)}><option>PLATFORM_ADMIN</option><option>DOMAIN_ADMIN</option><option>SCHEMA_OWNER</option><option>AGENT_OWNER</option><option>VIEWER</option></select></label><label>Domains<input value={domains} onChange={(event) => setDomains(event.target.value)} /></label></div><ConsoleShell identity={identity} section={section} status={status} onSection={setSection} /></>;
}
