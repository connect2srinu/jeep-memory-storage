import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { AdminApiClient, AdminApiError } from "./api";
import {
  canMutate,
  filterRecords,
  findNormalizedDuplicates,
  movePriority,
  paginateRecords,
  recordId,
  sortRecords,
  type SortDirection,
} from "./governance";
import type { AdminIdentity, AdminRecord, AdminRole } from "./types";
import { MemorySetupWizard } from "./Wizard";

type IconName = "home" | "sparkles" | "building" | "domain" | "scope" | "schema" | "catalog" | "agent" | "share" | "approval" | "policy" | "memory" | "audit" | "project" | "users" | "health" | "settings" | "budget" | "observe";

function UiIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10M9 20v-6h6v6"/></>,
    sparkles: <><path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3Z"/><path d="m5 14 .8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8L5 14Zm13-1 .8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8L18 13Z"/></>,
    building: <><path d="M4 21V8l8-4 8 4v13M2 21h20"/><path d="M8 10h2m4 0h2m-8 4h2m4 0h2m-8 4h2m4 0h2"/></>,
    domain: <><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></>,
    scope: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 3v3m0 12v3m9-9h-3M6 12H3"/></>,
    schema: <><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/></>,
    catalog: <><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></>,
    agent: <><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/></>,
    share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.5 6.8-4m-6.8 7 6.8 4"/></>,
    approval: <><path d="M12 3 4 6v6c0 5 3.4 8 8 9 4.6-1 8-4 8-9V6l-8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></>,
    policy: <><path d="M4 7h10M4 17h16M10 12h10"/><circle cx="17" cy="7" r="2"/><circle cx="7" cy="12" r="2"/><circle cx="9" cy="17" r="2"/></>,
    memory: <><path d="M8 4a3 3 0 0 0-3 3v1a3 3 0 0 0-1 5 3 3 0 0 0 3 5h1a4 4 0 0 0 8 0h1a3 3 0 0 0 3-5 3 3 0 0 0-1-5V7a3 3 0 0 0-3-3"/><path d="M12 3v18M8 9h4m0 6h4"/></>,
    audit: <><path d="M6 3h9l4 4v14H6zM15 3v5h5"/><path d="M9 13h6M9 17h6"/></>,
    project: <><path d="M3 7h7l2 2h9v11H3z"/><path d="M3 7V5h7l2 2"/></>,
    users: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v2"/></>,
    health: <><path d="M3 12h4l2-5 4 10 2-5h6"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.7-.7-1.7.9-1.9-2.1-2.1-1.9.9-1.7-.7L10.5 2h-3l-.7 2-1.7.7-1.9-.9-2.1 2.1.9 1.9-.7 1.7-2 .7v3l2 .7.7 1.7-.9 1.9 2.1 2.1 1.9-.9 1.7.7.7 2h3l.7-2 1.7-.7 1.9.9 2.1-2.1-.9-1.9.7-1.7 2-.7Z" transform="translate(1.5 0) scale(.88)"/></>,
    budget: <><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M16 15h2"/></>,
    observe: <><path d="M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6Z"/><circle cx="12" cy="12" r="3"/></>,
  };
  return <svg className="ui-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

const primarySections = [
  ["dashboard", "Dashboard", "home"],
  ["create-setup", "Create Memory Setup", "sparkles"],
] as const;

const advancedSections = [
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

export function ResourceTable({ records, onSelect }: { records: AdminRecord[]; onSelect?: (record: AdminRecord) => void }) {
  const columns = useMemo(
    () => Object.keys(records[0] ?? {}).filter(
      (key) => !["created_at", "updated_at", "before_metadata", "after_metadata"].includes(key),
    ),
    [records],
  );
  const [query, setQuery] = useState("");
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("ascending");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const filteredRecords = useMemo(() => filterRecords(records, query, columns), [records, query, columns]);
  const sortedRecords = useMemo(
    () => sortRecords(filteredRecords, sortColumn, sortDirection),
    [filteredRecords, sortColumn, sortDirection],
  );
  const totalPages = Math.max(1, Math.ceil(sortedRecords.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleRecords = useMemo(
    () => paginateRecords(sortedRecords, currentPage, pageSize),
    [sortedRecords, currentPage, pageSize],
  );
  const firstResult = sortedRecords.length ? (currentPage - 1) * pageSize + 1 : 0;
  const lastResult = Math.min(currentPage * pageSize, sortedRecords.length);

  function toggleSort(column: string) {
    if (sortColumn === column) {
      setSortDirection((current) => current === "ascending" ? "descending" : "ascending");
    } else {
      setSortColumn(column);
      setSortDirection("ascending");
    }
    setPage(1);
  }

  if (!records.length) return <p className="empty">No records found.</p>;

  return (
    <div className="data-grid">
      <div className="data-grid-toolbar">
        <label className="resource-search">
          <span>Search resources</span>
          <input
            type="search"
            placeholder="Search all visible fields"
            value={query}
            onChange={(event) => { setQuery(event.target.value); setPage(1); }}
          />
        </label>
        <label className="page-size-control">
          <span>Rows per page</span>
          <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{columns.map((column) => (
            <th key={column} aria-sort={sortColumn === column ? sortDirection : "none"}>
              <button type="button" className="sort-button" onClick={() => toggleSort(column)} aria-label={`Sort by ${column.replaceAll("_", " ")}`}>
                <span>{column.replaceAll("_", " ")}</span>
                <span aria-hidden="true">{sortColumn === column ? sortDirection === "ascending" ? "▲" : "▼" : "↕"}</span>
              </button>
            </th>
          ))}</tr></thead>
          <tbody>{visibleRecords.map((record, index) => (
            <tr className={onSelect ? "clickable-row" : ""} tabIndex={onSelect ? 0 : undefined} role={onSelect ? "button" : undefined} onClick={() => onSelect?.(record)} onKeyDown={(event) => { if (onSelect && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onSelect(record); } }} key={recordId(record) || index}>{columns.map((column) => (
              <td key={column}>{typeof record[column] === "object" ? JSON.stringify(record[column]) : String(record[column] ?? "—")}</td>
            ))}</tr>
          ))}</tbody>
        </table>
        {!visibleRecords.length && <div className="table-empty">No resources match “{query}”.</div>}
      </div>
      <div className="data-grid-footer">
        <span>{firstResult}–{lastResult} of {sortedRecords.length} resources</span>
        <div className="pagination" aria-label="Table pagination">
          <button type="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous</button>
          <strong>Page {currentPage} of {totalPages}</strong>
          <button type="button" disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}>Next</button>
        </div>
      </div>
    </div>
  );
}

const editableFields: Record<string, string[]> = {
  organizations: ["name", "description", "owner_contact"],
  projects: ["name", "description", "owner_team"],
  domains: ["name", "description", "owner_team", "owner_contact", "contract_version"],
  scopes: ["scope_type", "scope_keys", "description"],
  schemas: ["display_name", "description", "owner_team"],
  "preference-catalog": ["display_name", "description", "allowed_values", "validation_rules", "default_resolution_behavior", "catalog_version"],
  agents: ["display_name", "runtime_type", "identity_type", "principal", "capabilities"],
  "resolution-policies": ["name", "default_rules", "schema_priorities", "attribute_overrides"],
  "dynamic-memory-policies": ["enabled", "confidence_threshold", "memory_topics", "retention_policy", "confirmation_required", "allowed_dynamic_categories"],
};

function editablePayload(resource: string, record: AdminRecord): AdminRecord {
  return Object.fromEntries((editableFields[resource] ?? []).map((key) => [key, record[key]]));
}

function SchemaAccessRequestForm({ api, organizationId, schemaId, onSubmitted }: { api: AdminApiClient; organizationId: string; schemaId: string; onSubmitted: () => Promise<void> | void }) {
  const [agents, setAgents] = useState<AdminRecord[]>([]);
  const [agentId, setAgentId] = useState("");
  const [team, setTeam] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.list("agents", organizationId).then(setAgents).catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load agents")); }, [api, organizationId]);
  async function submit() {
    if (!agentId || !team.trim() || !reason.trim()) { setError("Agent, requesting team, and business reason are required."); return; }
    setSaving(true);
    try {
      await api.create("access-requests", { requestingAgentId: agentId, requestingTeam: team, targetSchemaId: schemaId, requestedPermission: "READ", businessReason: reason });
      setError("");
      await onSubmitted();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to request access"); }
    finally { setSaving(false); }
  }
  return <div className="compact-form"><h4>Request read access</h4><label className="wide">Requesting agent<select value={agentId} onChange={(event) => setAgentId(event.target.value)}><option value="">Choose an agent</option>{agents.map((agent) => <option key={recordId(agent)} value={recordId(agent)}>{String(agent.display_name ?? agent.id)}</option>)}</select></label><label>Requesting team<input value={team} onChange={(event) => setTeam(event.target.value)} /></label><label>Business reason<input value={reason} onChange={(event) => setReason(event.target.value)} /></label><ErrorBanner error={error} /><div className="form-actions wide"><button className="primary" type="button" disabled={saving} onClick={submit}>{saving ? "Submitting…" : "Submit READ request"}</button></div></div>;
}

function AgentSchemaAccessEditor({ api, agent, onCancel, onSubmitted }: { api: AdminApiClient; agent: AdminRecord; onCancel: () => void; onSubmitted: () => Promise<void> | void }) {
  const [schemas, setSchemas] = useState<AdminRecord[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [team, setTeam] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try { setSchemas(await api.agentSchemaAccess(recordId(agent))); setError(""); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load schema access"); }
    finally { setLoading(false); }
  }, [agent, api]);
  useEffect(() => { void load(); }, [load]);
  const current = schemas.filter((item) => item.access_status === "APPROVED" || item.access_status === "PENDING");
  const available = schemas.filter((item) => item.access_status !== "APPROVED" && item.access_status !== "PENDING" && item.status === "ACTIVE");
  function toggle(schemaId: string) { setSelected((items) => items.includes(schemaId) ? items.filter((item) => item !== schemaId) : [...items, schemaId]); }
  async function submit() {
    if (!selected.length || !team.trim() || !reason.trim()) { setError("Select at least one schema and provide the requesting team and business reason."); return; }
    setSaving(true);
    try {
      for (const schemaId of selected) {
        await api.create("access-requests", { requestingAgentId: recordId(agent), requestingTeam: team.trim(), targetSchemaId: schemaId, requestedPermission: "READ", businessReason: reason.trim() });
      }
      setSelected([]); setError(""); await load(); await onSubmitted();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to submit schema access request"); }
    finally { setSaving(false); }
  }
  return <div className="agent-schema-access"><div className="schema-stepper"><span className="active">1 Select schemas</span><span>2 Approval</span><span>3 Runtime access</span></div><h4>Schema access for {String(agent.display_name ?? agent.id)}</h4><p>Adding a schema creates a READ request for its owner. The agent cannot read it until approval and never receives cross-domain WRITE access.</p>{loading ? <p>Loading schema catalog…</p> : <><section><h5>Current access</h5><div className="access-summary">{current.length ? current.map((item) => <div key={recordId(item)}><span><strong>{String(item.display_name)}</strong><small>{recordId(item)} · owner {String(item.domain_id)}</small></span><span className={`pill ${String(item.access_status).toLowerCase()}`}>{String(item.access_status)}{item.permission ? ` · ${String(item.permission)}` : ""}</span></div>) : <p className="empty">No schema grants or pending requests.</p>}</div></section><section><h5>Available schemas</h5><div className="catalog-grid">{available.map((item) => { const id = recordId(item); return <label className={`catalog-card ${selected.includes(id) ? "selected" : ""}`} key={id}><input type="checkbox" checked={selected.includes(id)} onChange={() => toggle(id)} /><span><strong>{String(item.display_name)}</strong><small>{id} · {String(item.visibility).toLowerCase()} · owner {String(item.domain_id)}</small><p>Request READ access</p></span></label>; })}{!available.length && <p className="empty">No additional active schemas are available.</p>}</div></section><div className="form-grid"><label>Requesting team<input value={team} onChange={(event) => setTeam(event.target.value)} placeholder="mobile-platform" /></label><label>Business reason<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Use inventory availability in the mobile experience" /></label></div></>}<ErrorBanner error={error} /><div className="form-actions"><button className="secondary" type="button" onClick={onCancel}>Cancel</button><button className="primary" type="button" disabled={saving || loading || !selected.length} onClick={submit}>{saving ? "Submitting…" : `Submit ${selected.length || ""} READ request${selected.length === 1 ? "" : "s"}`}</button></div></div>;
}

function SchemaVersionEditor({ api, schema, activeVersion, organizationId, onCancel, onSubmitted }: { api: AdminApiClient; schema: AdminRecord; activeVersion: AdminRecord; organizationId: string; onCancel: () => void; onSubmitted: () => Promise<void> | void }) {
  const domainId = String(schema.domain_id);
  const activeMappings = useMemo(() => Array.isArray(activeVersion.mappings) ? activeVersion.mappings as AdminRecord[] : [], [activeVersion]);
  const protectedAttributes = useMemo(() => new Set(activeMappings.map((item) => String(item.attribute_id))), [activeMappings]);
  const [catalog, setCatalog] = useState<AdminRecord[]>([]);
  const [selected, setSelected] = useState<string[]>(activeMappings.map((item) => String(item.attribute_id)));
  const [version, setVersion] = useState("");
  const [step, setStep] = useState<"preferences" | "create" | "review">("preferences");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [attributeName, setAttributeName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [dataType, setDataType] = useState("string");
  const [allowedValues, setAllowedValues] = useState("");
  const [sensitivity, setSensitivity] = useState("normal");

  const loadCatalog = useCallback(async () => {
    const items = await api.list("preference-catalog", organizationId);
    setCatalog(items.filter((item) => String(item.canonical_owner_id ?? "") === domainId));
  }, [api, domainId, organizationId]);
  useEffect(() => { loadCatalog().catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load preference catalog")); }, [loadCatalog]);

  function fieldFor(attributeId: string): string {
    const existing = activeMappings.find((item) => item.attribute_id === attributeId);
    if (existing) return String(existing.profile_field);
    return attributeId.split(".").at(-1)?.replace(/[^a-zA-Z0-9_]/g, "_") || "preference";
  }
  function toggle(attributeId: string) {
    if (protectedAttributes.has(attributeId)) return;
    setSelected((current) => current.includes(attributeId) ? current.filter((item) => item !== attributeId) : [...current, attributeId]);
  }
  async function createPreference() {
    const suffix = attributeName.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/^_+|_+$/g, "");
    if (!suffix || !displayName.trim() || !description.trim()) { setError("Preference name, display name, and description are required."); return; }
    const attributeId = `${domainId}.${suffix}`;
    setSaving(true);
    try {
      await api.create("preference-catalog", {
        attributeId,
        displayName: displayName.trim(),
        description: description.trim(),
        dataType,
        allowedValues: allowedValues.split(",").map((item) => item.trim()).filter(Boolean),
        sensitivityClassification: sensitivity,
        canonicalOwnerId: domainId,
      });
      await loadCatalog();
      setSelected((current) => [...new Set([...current, attributeId])]);
      setAttributeName(""); setDisplayName(""); setDescription(""); setAllowedValues(""); setError(""); setStep("preferences");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to create preference"); }
    finally { setSaving(false); }
  }
  async function submit() {
    if (!version.trim()) { setError("A new schema version is required."); return; }
    if (!selected.length) { setError("Select at least one preference."); return; }
    const properties = Object.fromEntries(selected.map((attributeId) => {
      const preference = catalog.find((item) => item.attribute_id === attributeId);
      const existingProperties = activeVersion.vertex_schema_definition && typeof activeVersion.vertex_schema_definition === "object" ? (activeVersion.vertex_schema_definition as AdminRecord).properties as AdminRecord | undefined : undefined;
      const field = fieldFor(attributeId);
      const existing = existingProperties?.[field];
      const generated: AdminRecord = { type: String(preference?.data_type ?? "string") };
      if (Array.isArray(preference?.allowed_values) && preference.allowed_values.length) generated.enum = preference.allowed_values;
      return [field, existing ?? generated];
    }));
    const priorDefinition = activeVersion.vertex_schema_definition as AdminRecord;
    const priorRequired = Array.isArray(priorDefinition?.required) ? priorDefinition.required as string[] : [];
    const required = priorRequired.filter((field) => Object.hasOwn(properties, field));
    setSaving(true);
    try {
      await api.requestSchemaVersion(recordId(schema), {
        version: version.trim(),
        scopeDefinitionId: activeVersion.scope_definition_id,
        vertexSchemaDefinition: { ...priorDefinition, type: "object", properties, ...(required.length ? { required } : { required: undefined }) },
        generationConfig: activeVersion.generation_config ?? {},
        mappings: selected.map((attributeId) => ({ attributeId, profileField: fieldFor(attributeId) })),
      });
      setError("");
      await onSubmitted();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to submit schema version"); }
    finally { setSaving(false); }
  }

  return <div className="schema-version-wizard"><div className="schema-stepper"><span className={step === "preferences" ? "active" : ""}>1 Preferences</span><span className={step === "create" ? "active" : ""}>2 New preference</span><span className={step === "review" ? "active" : ""}>3 Review</span></div>{step === "preferences" && <><h4>Select preferences</h4><p>Only preferences canonically owned by <strong>{domainId}</strong> can be mapped into this schema. Existing mappings are protected; shared-domain preferences remain linked through approved schema access.</p><div className="catalog-grid">{catalog.map((item) => { const id = String(item.attribute_id); const protectedMapping = protectedAttributes.has(id); return <label className={`catalog-card ${selected.includes(id) ? "selected" : ""} ${protectedMapping ? "protected" : ""}`} key={id}><input type="checkbox" checked={selected.includes(id)} disabled={protectedMapping} onChange={() => toggle(id)} /><span><strong>{String(item.display_name)}</strong><small>{id}</small><p>{protectedMapping ? "Existing mapping · protected" : String(item.description)}</p></span></label>; })}</div><div className="form-actions"><button className="secondary" type="button" onClick={() => setStep("create")}>+ Create preference</button><button className="primary" type="button" disabled={!selected.length} onClick={() => setStep("review")}>Review version</button></div></>}{step === "create" && <><h4>Create a domain preference</h4><div className="form-grid"><label>Attribute name<div className="prefixed-input"><span>{domainId}.</span><input value={attributeName} onChange={(event) => setAttributeName(event.target.value)} placeholder="preferred_brand" /></div></label><label>Display name<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label><label className="wide">Description<input value={description} onChange={(event) => setDescription(event.target.value)} /></label><label>Data type<select value={dataType} onChange={(event) => setDataType(event.target.value)}><option>string</option><option>boolean</option><option>integer</option><option>number</option></select></label><label>Allowed values<input value={allowedValues} onChange={(event) => setAllowedValues(event.target.value)} placeholder="Comma separated; optional" /></label><label>Sensitivity<select value={sensitivity} onChange={(event) => setSensitivity(event.target.value)}><option>normal</option><option>sensitive</option><option>restricted</option></select></label></div><ErrorBanner error={error} /><div className="form-actions"><button className="secondary" type="button" onClick={() => setStep("preferences")}>Back</button><button className="primary" type="button" disabled={saving} onClick={createPreference}>{saving ? "Creating…" : "Create and select"}</button></div></>}{step === "review" && <><h4>Review and submit</h4><div className="protected-settings"><div><span>Schema</span><strong>{recordId(schema)}</strong></div><div><span>Domain</span><strong>{domainId}</strong></div><div><span>Scope (protected)</span><strong>{String(activeVersion.scope_definition_id)}</strong></div><div><span>Current version</span><strong>{String(activeVersion.version)}</strong></div></div><label>New version<input value={version} onChange={(event) => setVersion(event.target.value)} placeholder="For example, 2.0" /></label><div className="mapping-review">{selected.map((attributeId) => <div key={attributeId}><span>{attributeId}{protectedAttributes.has(attributeId) ? " · protected" : " · new"}</span><strong>→ {fieldFor(attributeId)}</strong></div>)}</div><div className="alert warning">Submitting creates a DRAFT. The current active schema remains unchanged until platform approval.</div><ErrorBanner error={error} /><div className="form-actions"><button className="secondary" type="button" onClick={() => setStep("preferences")}>Back</button><button className="primary" type="button" disabled={saving} onClick={submit}>{saving ? "Submitting…" : "Submit version for approval"}</button></div></>}<button className="link-button" type="button" onClick={onCancel}>Cancel schema edit</button></div>;
}

function ResourceDetailPanel({ resource, record, writable, api, contextOrganizationId, onClose, onSaved }: { resource: string; record: AdminRecord; writable: boolean; api: AdminApiClient; contextOrganizationId?: string; onClose: () => void; onSaved: () => Promise<void> | void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(JSON.stringify(editablePayload(resource, record), null, 2));
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [activeSchemaVersion, setActiveSchemaVersion] = useState<AdminRecord | null>(null);
  const [managingSchemaAccess, setManagingSchemaAccess] = useState(false);
  const canEdit = writable && record.editable !== false && Boolean(editableFields[resource]) && (resource !== "schemas" || Boolean(contextOrganizationId));

  useEffect(() => {
    setDraft(JSON.stringify(editablePayload(resource, record), null, 2));
    setEditing(false);
    setError("");
    setMessage("");
    setActiveSchemaVersion(null);
    setManagingSchemaAccess(false);
  }, [record, resource]);

  async function save() {
    setSaving(true);
    try {
      const changes = parseJson(draft);
      if (resource === "domains") {
        await api.requestDomainChange(recordId(record), changes);
        setMessage("Change submitted for approval. The active domain remains unchanged until approval.");
      } else {
        await api.update(resource, recordId(record), { changes });
        setMessage("Changes saved.");
        await onSaved();
      }
      setError("");
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save changes");
    } finally { setSaving(false); }
  }

  async function beginEdit() {
    if (resource !== "schemas") { setEditing(true); return; }
    setSaving(true);
    try {
      const details = await api.get("schemas", recordId(record));
      const versions = Array.isArray(details.versions) ? details.versions as AdminRecord[] : [];
      const active = versions.find((item) => item.status === "ACTIVE");
      if (!active) throw new Error("This schema has no active version to edit.");
      setActiveSchemaVersion(active);
      setEditing(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load schema version");
    } finally { setSaving(false); }
  }

  const visibleEntries = Object.entries(record).filter(([key]) => !["before_metadata", "after_metadata"].includes(key));
  return <div className="detail-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className={`resource-detail ${(resource === "schemas" && editing) || managingSchemaAccess ? "schema-edit-detail" : ""}`} role="dialog" aria-modal="true" aria-label={`${resource} details`}><header><div><span className="eyebrow">{resource.replaceAll("-", " ")}</span><h3>{String(record.name ?? record.display_name ?? record.attribute_id ?? record.id ?? "Resource details")}</h3><small>{recordId(record)}</small></div><button className="icon-button" type="button" aria-label="Close details" onClick={onClose}>×</button></header>{record.visibility === "PLATFORM" && <div className="alert success">Platform resource available to every organization. Runtime use still requires an approved schema grant.</div>}{record.visibility === "RESTRICTED" && <div className="alert warning">Owned by another organization. Metadata is visible; request read access before using this schema.</div>}{message && <div className="alert success">{message}</div>}{managingSchemaAccess && resource === "agents" ? <AgentSchemaAccessEditor api={api} agent={record} onCancel={() => setManagingSchemaAccess(false)} onSubmitted={async () => { setMessage("Schema READ request submitted. It will become available after schema-owner approval."); await onSaved(); }} /> : editing && resource === "schemas" && activeSchemaVersion && contextOrganizationId ? <SchemaVersionEditor api={api} schema={record} activeVersion={activeSchemaVersion} organizationId={contextOrganizationId} onCancel={() => setEditing(false)} onSubmitted={async () => { setMessage("A draft schema version was submitted for approval. The active version remains unchanged."); setEditing(false); await onSaved(); }} /> : editing ? <div className="detail-editor"><p>Edit only the governed fields below.</p><textarea aria-label={`Edit ${resource} JSON`} value={draft} onChange={(event) => setDraft(event.target.value)} /><ErrorBanner error={error} /><div className="form-actions"><button className="secondary" type="button" onClick={() => setEditing(false)}>Cancel</button><button className="primary" type="button" disabled={saving} onClick={save}>{saving ? "Saving…" : resource === "domains" ? "Submit for approval" : "Save changes"}</button></div></div> : <><dl className="detail-list">{visibleEntries.map(([key, item]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof item === "object" && item !== null ? <pre>{JSON.stringify(item, null, 2)}</pre> : String(item ?? "—")}</dd></div>)}</dl><div className="detail-actions">{canEdit && <button className="secondary" type="button" disabled={saving} onClick={beginEdit}>{resource === "schemas" ? "Create new version" : "Edit resource"}</button>}{resource === "agents" && writable && <button className="primary" type="button" onClick={() => setManagingSchemaAccess(true)}>Manage schema access</button>}</div>{resource === "schemas" && contextOrganizationId && record.visibility !== "OWNED" && record.access_status === "NOT_REQUESTED" && <SchemaAccessRequestForm api={api} organizationId={contextOrganizationId} schemaId={recordId(record)} onSubmitted={async () => { setMessage("READ access request submitted for schema-owner approval."); await onSaved(); }} />}</>}</aside></div>;
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

function AccessActions({ records, api, reload, approvalsOnly, writable = true }: { records: AdminRecord[]; api: AdminApiClient; reload: () => void; approvalsOnly: boolean; writable?: boolean }) {
  const visible = approvalsOnly ? records.filter((record) => record.status === "PENDING") : records;
  async function act(id: string, action: "approve" | "reject" | "revoke" | "expire") {
    await api.decideAccess(id, action, `${action} from Admin Console`);
    reload();
  }
  return <div className="request-list">{visible.map((record) => <article key={recordId(record)}>
    <div><strong>{String(record.requesting_agent_id)}</strong> → {String(record.target_schema_id)}<p>{String(record.business_reason)}</p></div>
    <span className={`pill ${String(record.status).toLowerCase()}`}>{String(record.status)}</span>
    <div className="actions">{writable && record.status === "PENDING" && <><button type="button" onClick={() => act(recordId(record), "approve")}>Approve</button><button className="danger" type="button" onClick={() => act(recordId(record), "reject")}>Reject</button></>}{writable && record.status === "APPROVED" && <button className="danger" type="button" onClick={() => act(recordId(record), "revoke")}>Revoke</button>}</div>
  </article>)}</div>;
}

function ResourceChangeActions({ records, api, reload, approvalsOnly, writable = true }: { records: AdminRecord[]; api: AdminApiClient; reload: () => void; approvalsOnly: boolean; writable?: boolean }) {
  const visible = approvalsOnly ? records.filter((record) => record.status === "PENDING") : records;
  async function act(id: string, action: "approve" | "reject") {
    await api.decideResourceChange(id, action, `${action} from Admin Console`);
    reload();
  }
  if (!visible.length) return null;
  return <div className="request-list change-request-list">{visible.map((record) => <article key={recordId(record)}>
    <div><strong>{String(record.resource_type === "schemas" ? "Schema version" : "Domain change")} · {String(record.resource_id)}</strong><p>Requested by {String(record.requested_by)}</p><pre>{JSON.stringify(record.proposed_changes, null, 2)}</pre></div>
    <span className={`pill ${String(record.status).toLowerCase()}`}>{String(record.status)}</span>
    <div className="actions">{writable && record.status === "PENDING" && <><button type="button" onClick={() => act(recordId(record), "approve")}>Approve &amp; publish</button><button className="danger" type="button" onClick={() => act(recordId(record), "reject")}>Reject</button></>}</div>
  </article>)}</div>;
}

function value(record: AdminRecord, key: string): string {
  return String(record[key] ?? "");
}

function records(record: AdminRecord, key: string): AdminRecord[] {
  return Array.isArray(record[key]) ? record[key] as AdminRecord[] : [];
}

type OrganizationTab = "overview" | "projects" | "approvals" | "members" | "settings";
type ProjectTab = "overview" | "domains" | "agents" | "health" | "members" | "settings";
type ContextSelection = { id: string; name: string } | null;

function OrganizationSettingsPanel({ organizationId, api, writable }: { organizationId: string; api: AdminApiClient; writable: boolean }) {
  const [settings, setSettings] = useState<AdminRecord>({});
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => { void api.organizationSettings(organizationId).then(setSettings).catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load settings")); }, [api, organizationId]);
  async function save() {
    try {
      const updated = await api.updateOrganizationSettings(organizationId, {
        budgetEnabled: Boolean(settings.budget_enabled), budgetAmount: settings.budget_amount ? Number(settings.budget_amount) : undefined,
        currency: settings.currency || "USD", budgetPeriod: settings.budget_period || "MONTHLY",
        thresholds: [{ percent: Number(settings.notification_percent || 80), basis: "ACTUAL" }],
        emailRecipients: String(settings.email_recipients_text || "").split(",").map((item) => item.trim()).filter(Boolean),
        monitoringChannelIds: String(settings.channel_ids_text || "").split(",").map((item) => item.trim()).filter(Boolean),
        pubsubTopic: settings.pubsub_topic || undefined, billingAccountId: settings.billing_account_id || undefined,
        billingProjectIds: String(settings.billing_project_ids_text || "").split(",").map((item) => item.trim()).filter(Boolean),
      });
      setSettings(updated); setSaved(true); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to save settings"); }
  }
  const threshold = records(settings, "thresholds")[0]?.percent ?? 80;
  return <div className="settings-panel"><div className="panel-heading"><div><h3>Budget &amp; notifications</h3><p>Set the organization guardrail. Cloud Billing synchronization remains explicit and observable.</p></div><span className="pill">{value(settings, "sync_status") || "LOCAL_ONLY"}</span></div><div className="settings-grid"><label className="toggle-row"><input type="checkbox" checked={Boolean(settings.budget_enabled)} disabled={!writable} onChange={(event) => setSettings({ ...settings, budget_enabled: event.target.checked })} /> Enable budget notifications</label><label>Budget amount<input type="number" min="1" disabled={!writable} value={value(settings, "budget_amount")} onChange={(event) => setSettings({ ...settings, budget_amount: event.target.value })} /></label><label>Currency<input maxLength={3} disabled={!writable} value={value(settings, "currency") || "USD"} onChange={(event) => setSettings({ ...settings, currency: event.target.value.toUpperCase() })} /></label><label>Period<select disabled={!writable} value={value(settings, "budget_period") || "MONTHLY"} onChange={(event) => setSettings({ ...settings, budget_period: event.target.value })}><option>MONTHLY</option><option>QUARTERLY</option><option>ANNUAL</option></select></label><label>Notify at (%)<input type="number" min="1" max="100" disabled={!writable} defaultValue={String(threshold)} onChange={(event) => setSettings({ ...settings, notification_percent: event.target.value })} /></label><label className="wide">Email recipients (comma separated)<input disabled={!writable} defaultValue={(settings.email_recipients as string[] || []).join(", ")} onChange={(event) => setSettings({ ...settings, email_recipients_text: event.target.value })} /></label><label className="wide">Cloud Monitoring channel IDs<input disabled={!writable} defaultValue={(settings.monitoring_channel_ids as string[] || []).join(", ")} onChange={(event) => setSettings({ ...settings, channel_ids_text: event.target.value })} /></label><label>Billing account ID<input disabled={!writable} value={value(settings, "billing_account_id")} onChange={(event) => setSettings({ ...settings, billing_account_id: event.target.value })} /></label><label>GCP project IDs<input disabled={!writable} defaultValue={(settings.billing_project_ids as string[] || []).join(", ")} onChange={(event) => setSettings({ ...settings, billing_project_ids_text: event.target.value })} /></label><label className="wide">Pub/Sub topic<input disabled={!writable} value={value(settings, "pubsub_topic")} onChange={(event) => setSettings({ ...settings, pubsub_topic: event.target.value })} placeholder="projects/my-project/topics/budget-events" /></label></div><ErrorBanner error={error} />{saved && <div className="alert success">Organization settings saved.</div>}{writable && <button className="primary" type="button" onClick={save}>Save settings</button>}</div>;
}

function formatDate(value: unknown): string {
  const raw = String(value ?? "");
  return raw ? raw.slice(0, 10) : "—";
}

const approvalColumns: Array<[string, string]> = [
  ["direction", "Direction"],
  ["status", "Status"],
  ["requesting_agent_name", "Requester"],
  ["requesting_project_id", "From project"],
  ["owning_domain_id", "Owning domain"],
  ["target_schema_id", "Target schema"],
  ["requested_permission", "Permission"],
  ["requested_at", "Requested"],
];

export function ApprovalsTable({ rows, api, reload, writable }: { rows: AdminRecord[]; api: AdminApiClient; reload: () => void; writable: boolean }) {
  const [direction, setDirection] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState("requested_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const statuses = useMemo(() => Array.from(new Set(rows.map((row) => String(row.status)))).sort(), [rows]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (direction !== "ALL" && String(row.direction ?? "") !== direction) return false;
      if (statusFilter !== "ALL" && String(row.status ?? "") !== statusFilter) return false;
      if (!needle) return true;
      return [row.requesting_agent_name, row.requesting_agent_id, row.requesting_team, row.owning_domain_id, row.target_schema_id, row.requested_by]
        .some((field) => String(field ?? "").toLowerCase().includes(needle));
    });
  }, [rows, direction, statusFilter, query]);
  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av = String(a[sortKey] ?? "");
      const bv = String(b[sortKey] ?? "");
      return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    return copy;
  }, [filtered, sortKey, sortDir]);

  function toggleSort(key: string) {
    if (sortKey === key) setSortDir((current) => (current === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("asc"); }
  }
  async function act(id: string, action: "approve" | "reject" | "revoke") {
    await api.decideAccess(id, action, `${action} from Approvals`);
    reload();
  }

  return <div className="approvals-table data-grid">
    <div className="data-grid-toolbar approvals-toolbar">
      <label className="resource-search"><span>Search</span><input type="search" placeholder="Requester, domain, schema…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <label className="filter-control"><span>Direction</span><select value={direction} onChange={(event) => setDirection(event.target.value)}><option value="ALL">All</option><option value="INCOMING">Incoming</option><option value="OUTGOING">Outgoing</option><option value="HISTORY">History</option></select></label>
      <label className="filter-control"><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">All</option>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
    </div>
    <div className="table-wrap"><table><thead><tr>{approvalColumns.map(([key, label]) => (
      <th key={key} aria-sort={sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
        <button type="button" className="sort-button" onClick={() => toggleSort(key)}><span>{label}</span><span aria-hidden="true">{sortKey === key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span></button>
      </th>
    ))}<th>Actions</th></tr></thead>
    <tbody>{sorted.map((row) => {
      const id = recordId(row);
      const status = String(row.status);
      const isIncoming = String(row.direction ?? "") === "INCOMING";
      return <tr key={id}>
        <td><span className={`dir-pill ${String(row.direction ?? "").toLowerCase()}`}>{String(row.direction ?? "—")}</span></td>
        <td><span className={`status-chip ${status.toLowerCase()}`}>{status}</span></td>
        <td><strong>{String(row.requesting_agent_name || row.requesting_agent_id || "—")}</strong>{row.requesting_team ? <small>{String(row.requesting_team)}</small> : null}</td>
        <td>{String(row.requesting_project_id ?? "—")}</td>
        <td>{String(row.owning_domain_id ?? "—")}</td>
        <td>{String(row.target_schema_id ?? "—")}</td>
        <td>{String(row.requested_permission ?? "—")}</td>
        <td>{formatDate(row.requested_at)}</td>
        <td className="row-actions">{writable && isIncoming && status === "PENDING"
          ? <><button type="button" onClick={() => act(id, "approve")}>Approve</button><button className="danger" type="button" onClick={() => act(id, "reject")}>Reject</button></>
          : writable && isIncoming && status === "APPROVED"
            ? <button className="danger" type="button" onClick={() => act(id, "revoke")}>Revoke</button>
            : <span className="muted">—</span>}</td>
      </tr>;
    })}</tbody></table>
      {!sorted.length && <div className="table-empty">No requests match the current filters.</div>}
    </div>
    <div className="data-grid-footer"><span>{sorted.length} of {rows.length} requests</span></div>
  </div>;
}

function OrganizationApprovalsPanel({ organizationId, api, writable = true }: { organizationId: string; api: AdminApiClient; writable?: boolean }) {
  const [data, setData] = useState<AdminRecord>({ incoming: [], outgoing: [], history: [] });
  const [error, setError] = useState("");
  const load = useCallback(async () => { try { setData(await api.organizationApprovals(organizationId)); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load approvals"); } }, [api, organizationId]);
  useEffect(() => { void load(); }, [load]);
  const rows = useMemo(() => [
    ...records(data, "incoming").map((row) => ({ ...row, direction: "INCOMING" })),
    ...records(data, "outgoing").map((row) => ({ ...row, direction: "OUTGOING" })),
    ...records(data, "history").map((row) => ({ ...row, direction: "HISTORY" })),
  ], [data]);
  const pendingIncoming = records(data, "incoming").length;
  return <div className="organization-panel"><div className="panel-heading"><div><h3>Schema access approvals</h3><p>One queue for cross-project schema access. Incoming requests need this organization’s decision; outgoing requests are read-only until the owner approves them.</p></div><span className="count-badge">{pendingIncoming} pending</span></div><ErrorBanner error={error} />{rows.length ? <ApprovalsTable rows={rows} api={api} reload={() => void load()} writable={writable} /> : <div className="empty-state"><strong>No access requests</strong><p>Cross-project schema access requests will appear here for review.</p></div>}</div>;
}

function accessKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    OWNING_PROJECT_GRANT: "Owning-project grant",
    CROSS_PROJECT_GRANT: "Cross-project grant",
    ELIGIBLE_NOT_GRANTED: "Eligible · not granted",
    REQUEST_PENDING: "Request pending",
    NONE: "No access",
  };
  return labels[kind] ?? kind;
}

function DomainSchemaAgents({ api, schemaId }: { api: AdminApiClient; schemaId: string }) {
  const [rows, setRows] = useState<AdminRecord[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    setRows(null);
    setError("");
    api.schemaAgents(schemaId)
      .then((result) => { if (live) setRows(result); })
      .catch((caught) => { if (live) setError(caught instanceof Error ? caught.message : "Unable to load agent access"); });
    return () => { live = false; };
  }, [api, schemaId]);
  if (error) return <ErrorBanner error={error} />;
  if (!rows) return <p className="empty">Loading agent access…</p>;
  if (!rows.length) return <p className="empty">No active agents in this organization.</p>;
  return <div className="table-wrap"><table><thead><tr><th>Agent</th><th>Project</th><th>Access</th><th>Permission</th><th>Status</th></tr></thead>
    <tbody>{rows.map((row) => <tr key={String(row.agent_id)}>
      <td><strong>{String(row.display_name || row.agent_id)}</strong><small>{String(row.agent_id)}</small></td>
      <td>{String(row.project_id ?? "—")}{row.same_project ? " · same project" : ""}</td>
      <td><span className={`access-chip kind-${String(row.access_kind ?? "none").toLowerCase()}`}>{accessKindLabel(String(row.access_kind))}</span></td>
      <td>{String(row.permission ?? "—")}</td>
      <td><span className={`status-chip ${String(row.access_status ?? "").toLowerCase()}`}>{String(row.access_status)}</span></td>
    </tr>)}</tbody></table></div>;
}

function ResolutionPolicyCard({ title, policy }: { title: string; policy: AdminRecord }) {
  const priorities = records(policy, "schema_priorities");
  const overrides = records(policy, "attribute_overrides");
  return <div className="policy-card"><div className="policy-card-head"><strong>{title}</strong><small>{value(policy, "id")} · v{value(policy, "version")}</small></div>
    {priorities.length
      ? <ol className="precedence">{priorities.map((item) => <li key={String(item.id)}>{String(item.schema_id)}</li>)}</ol>
      : <p className="empty">No schema precedence configured (single-schema resolution).</p>}
    {overrides.length > 0 && <details><summary>{overrides.length} attribute override(s)</summary><ul>{overrides.map((item) => <li key={String(item.id)}>{String(item.attribute_id)}</li>)}</ul></details>}
  </div>;
}

type DomainTab = "overview" | "schemas" | "preferences" | "access" | "resolution" | "sharing" | "audit";

function DomainDetail({ domainId, api, writable, onBack }: { domainId: string; api: AdminApiClient; writable: boolean; onBack: () => void }) {
  const [detail, setDetail] = useState<AdminRecord | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<DomainTab>("overview");
  const [selectedSchemaId, setSelectedSchemaId] = useState<string>("");
  const load = useCallback(async () => {
    try {
      const loaded = await api.domainDetail(domainId);
      setDetail(loaded);
      const schemas = records(loaded, "schemas");
      setSelectedSchemaId((current) => current || (schemas[0] ? String(schemas[0].id) : ""));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load domain");
    }
  }, [api, domainId]);
  useEffect(() => { void load(); }, [load]);

  if (error) return <div className="domain-detail"><button className="back-link" type="button" onClick={onBack}>← Domains</button><ErrorBanner error={error} /></div>;
  if (!detail) return <div className="domain-detail"><button className="back-link" type="button" onClick={onBack}>← Domains</button><p className="empty">Loading domain…</p></div>;

  const domain = (detail.domain as AdminRecord) ?? {};
  const project = (detail.project as AdminRecord) ?? {};
  const schemas = records(detail, "schemas");
  const scopes = records(detail, "scopes");
  const homeAgents = records(detail, "home_agents");
  const resolution = (detail.resolution as AdminRecord) ?? {};
  const pending = (detail.pending_requests as AdminRecord) ?? {};
  const selectedSchema = schemas.find((item) => String(item.id) === selectedSchemaId) ?? schemas[0];
  const versions = selectedSchema ? records(selectedSchema, "versions") : [];
  const activeVersion = versions.find((item) => String(item.status) === "ACTIVE") ?? versions[0];
  const mappings = activeVersion ? records(activeVersion, "mappings") : [];

  return <div className="domain-detail"><button className="back-link" type="button" onClick={onBack}>← Domains</button>
    <div className="context-header"><div className="organization-monogram domain-monogram">D</div><div><span className="eyebrow">Domain</span><h2>{value(domain, "name") || value(domain, "id")}</h2><p>{value(domain, "description") || value(domain, "id")}</p><small>Project: {value(project, "name") || value(domain, "project_id")} · Owner: {value(domain, "owner_team")}</small></div><span className={`status-chip ${value(domain, "status").toLowerCase()}`}>{value(domain, "status")}</span></div>
    <ContextTabs tabs={[["overview", "Overview"], ["schemas", "Schemas"], ["preferences", "Preference Catalog"], ["access", "Agent Access"], ["resolution", "Resolution"], ["sharing", "Sharing"], ["audit", "Audit"]]} selected={tab} onSelect={setTab} />
    {selectedSchema && schemas.length > 1 && (tab === "preferences" || tab === "access") && <label className="schema-picker"><span>Schema</span><select value={selectedSchemaId} onChange={(event) => setSelectedSchemaId(event.target.value)}>{schemas.map((item) => <option key={String(item.id)} value={String(item.id)}>{value(item, "display_name") || value(item, "id")}</option>)}</select></label>}
    {tab === "overview" && <div className="domain-overview"><div className="overview-grid"><article><span>Scopes</span><strong>{scopes.length}</strong><p>Provider scope keys</p></article><article><span>Schemas</span><strong>{schemas.length}</strong><p>Typed profile configurations</p></article><article><span>Home agents</span><strong>{homeAgents.length}</strong><p>Registered in this domain</p></article></div><dl className="detail-list"><div><dt>domain id</dt><dd>{value(domain, "id")}</dd></div><div><dt>organization</dt><dd>{value(domain, "organization_id")}</dd></div><div><dt>project</dt><dd>{value(domain, "project_id")}</dd></div><div><dt>owner team</dt><dd>{value(domain, "owner_team")}</dd></div><div><dt>owner contact</dt><dd>{value(domain, "owner_contact") || "—"}</dd></div><div><dt>contract version</dt><dd>{value(domain, "contract_version")}</dd></div><div><dt>scopes</dt><dd>{scopes.map((item) => value(item, "id")).join(", ") || "—"}</dd></div></dl></div>}
    {tab === "schemas" && <div className="resource-card-grid">{schemas.length ? schemas.map((item) => <button className="resource-card" type="button" key={String(item.id)} onClick={() => { setSelectedSchemaId(String(item.id)); setTab("preferences"); }}><span className="resource-icon">M</span><span><strong>{value(item, "display_name") || value(item, "id")}</strong><small>{value(item, "id")} · {records(item, "versions").length} version(s) · {String(item.active_grant_count ?? 0)} grant(s)</small></span><b>›</b></button>) : <p className="empty">No schemas in this domain.</p>}</div>}
    {tab === "preferences" && (selectedSchema ? <div className="table-wrap"><table><thead><tr><th>Attribute</th><th>Profile field</th></tr></thead><tbody>{mappings.length ? mappings.map((item) => <tr key={String(item.id)}><td><strong>{String(item.attribute_id)}</strong></td><td>{String(item.profile_field)}</td></tr>) : <tr><td colSpan={2}>No preference fields mapped in the active version.</td></tr>}</tbody></table></div> : <p className="empty">This domain has no schema yet.</p>)}
    {tab === "access" && (selectedSchema ? <><p className="tab-note">Access is explicit-grant-only: same-project agents are eligible but appear here only after an explicit grant. Read activity is not tracked today — this shows permission, not usage.</p><DomainSchemaAgents api={api} schemaId={String(selectedSchema.id)} /></> : <p className="empty">This domain has no schema yet.</p>)}
    {tab === "resolution" && <div className="resolution-view"><p className="tab-note">Resolution is defined per agent, with a domain-level default. One policy orders schemas by precedence across everything an agent reads.</p>{resolution.domain_default ? <ResolutionPolicyCard title="Domain default" policy={resolution.domain_default as AdminRecord} /> : <p className="empty">No domain-default policy configured.</p>}{records(resolution, "agent_policies").map((item) => <ResolutionPolicyCard key={String(item.id)} title={`Agent policy · ${String(item.agent_id ?? item.id)}`} policy={item} />)}</div>}
    {tab === "sharing" && <div className="sharing-view"><h4>Pending access requests</h4>{records(pending, "access").length ? <ApprovalsTable rows={records(pending, "access").map((row) => ({ ...row, direction: "INCOMING" }))} api={api} reload={() => void load()} writable={writable} /> : <p className="empty">No pending access requests targeting this domain’s schemas.</p>}<h4>Pending change requests</h4>{records(pending, "changes").length ? <ResourceChangeActions records={records(pending, "changes")} api={api} reload={() => void load()} approvalsOnly writable={writable} /> : <p className="empty">No pending change requests.</p>}</div>}
    {tab === "audit" && <div className="table-wrap"><table><thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead><tbody>{records(detail, "audit").length ? records(detail, "audit").map((item) => <tr key={String(item.id)}><td>{formatDate(item.timestamp)}</td><td>{String(item.actor)}</td><td>{String(item.action)}</td><td>{String(item.target_type)} · {String(item.target_id)}</td></tr>) : <tr><td colSpan={4}>No audit events recorded for this domain yet.</td></tr>}</tbody></table></div>}
  </div>;
}

function ProjectSettingsPanel({ projectId, api, writable }: { projectId: string; api: AdminApiClient; writable: boolean }) {
  const [settings, setSettings] = useState<AdminRecord>({}); const [error, setError] = useState("");
  useEffect(() => { void api.projectSettings(projectId).then(setSettings).catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load project settings")); }, [api, projectId]);
  async function save() { try { setSettings(await api.updateProjectSettings(projectId, { healthRefreshSeconds: Number(settings.health_refresh_seconds || 300), latencyWarningMs: Number(settings.latency_warning_ms || 2000), errorRateWarning: Number(settings.error_rate_warning || 0.05), notificationsEnabled: Boolean(settings.notifications_enabled), notificationChannelIds: String(settings.channel_ids_text || "").split(",").map((item) => item.trim()).filter(Boolean) })); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to save project settings"); } }
  return <div className="settings-panel"><div className="panel-heading"><div><h3>Agent health policy</h3><p>Configure refresh cadence and warning thresholds for project agents.</p></div></div><div className="settings-grid"><label>Refresh interval (seconds)<input type="number" min="30" disabled={!writable} value={value(settings, "health_refresh_seconds") || "300"} onChange={(event) => setSettings({ ...settings, health_refresh_seconds: event.target.value })} /></label><label>Latency warning (ms)<input type="number" min="1" disabled={!writable} value={value(settings, "latency_warning_ms") || "2000"} onChange={(event) => setSettings({ ...settings, latency_warning_ms: event.target.value })} /></label><label>Error-rate warning (0–1)<input type="number" min="0" max="1" step="0.01" disabled={!writable} value={value(settings, "error_rate_warning") || "0.05"} onChange={(event) => setSettings({ ...settings, error_rate_warning: event.target.value })} /></label><label className="toggle-row"><input type="checkbox" disabled={!writable} checked={settings.notifications_enabled !== false} onChange={(event) => setSettings({ ...settings, notifications_enabled: event.target.checked })} /> Enable health notifications</label><label className="wide">Notification channel IDs<input disabled={!writable} defaultValue={(settings.notification_channel_ids as string[] || []).join(", ")} onChange={(event) => setSettings({ ...settings, channel_ids_text: event.target.value })} /></label></div><ErrorBanner error={error} />{writable && <button className="primary" type="button" onClick={save}>Save health policy</button>}</div>;
}

function ProjectHealthPanel({ projectId, api, writable }: { projectId: string; api: AdminApiClient; writable: boolean }) {
  const [data, setData] = useState<AdminRecord>({ agents: [] }); const [error, setError] = useState(""); const [editing, setEditing] = useState<string | null>(null);
  const load = useCallback(async (refresh = false) => { try { setData(await api.projectHealth(projectId, refresh)); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load agent health"); } }, [api, projectId]);
  useEffect(() => { void load(); }, [load]);
  return <div className="organization-panel"><div className="panel-heading"><div><h3>Agent runtime health</h3><p>Cached provider health is scoped by immutable organization and project IDs.</p></div><button className="primary" type="button" onClick={() => void load(true)}>Refresh from runtime</button></div><ErrorBanner error={error} /><div className="health-grid">{records(data, "agents").map((item) => { const agent = item.agent as AdminRecord; const health = item.health as AdminRecord; const binding = item.binding as AdminRecord | null; const agentId = value(agent, "id"); return <article key={agentId} className="health-card"><div><strong>{value(agent, "display_name")}</strong><span className={`pill ${value(health, "health_status").toLowerCase()}`}>{value(health, "health_status")}</span></div><small>{agentId}</small><dl><dt>Provider</dt><dd>{binding ? value(binding, "provider") : "Not configured"}</dd><dt>Provider status</dt><dd>{value(health, "provider_status")}</dd><dt>Requests (5m)</dt><dd>{value(health, "request_count") || "—"}</dd></dl>{writable && <button className="secondary" type="button" onClick={() => setEditing(editing === agentId ? null : agentId)}>Configure runtime</button>}{editing === agentId && <RuntimeBindingForm agentId={agentId} existing={binding || {}} api={api} onSaved={() => { setEditing(null); void load(); }} />}</article>; })}</div></div>;
}

function RuntimeBindingForm({ agentId, existing, api, onSaved }: { agentId: string; existing: AdminRecord; api: AdminApiClient; onSaved: () => void }) {
  const [form, setForm] = useState<AdminRecord>({ provider: existing.provider || "GOOGLE_AGENT_RUNTIME", gcpProjectId: existing.gcp_project_id || "", location: existing.location || "us-central1", resourceName: existing.resource_name || "", endpointUrl: existing.endpoint_url || "", environment: existing.environment || "development" }); const [error, setError] = useState("");
  async function save() { try { await api.updateAgentRuntimeBinding(agentId, form); onSaved(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to save runtime binding"); } }
  return <div className="runtime-form"><label>Provider<select value={String(form.provider)} onChange={(event) => setForm({ ...form, provider: event.target.value })}><option>GOOGLE_AGENT_RUNTIME</option><option>CLOUD_RUN</option><option>ADK_LOCAL</option></select></label><label>GCP project ID<input value={String(form.gcpProjectId)} onChange={(event) => setForm({ ...form, gcpProjectId: event.target.value })} /></label><label>Location<input value={String(form.location)} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label><label>Runtime resource name<input value={String(form.resourceName)} onChange={(event) => setForm({ ...form, resourceName: event.target.value })} /></label><label>Health endpoint URL<input value={String(form.endpointUrl)} onChange={(event) => setForm({ ...form, endpointUrl: event.target.value })} /></label><ErrorBanner error={error} /><button className="primary" type="button" onClick={save}>Save binding</button></div>;
}

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
  const [selectedResource, setSelectedResource] = useState<{ resource: string; record: AdminRecord } | null>(null);
  const [selectedDomainId, setSelectedDomainId] = useState<string | null>(null);

  if (!selectedOrganization) {
    return <div className="organization-directory"><div className="section-heading"><div><span className="eyebrow">Organizations</span><h2>Organizations</h2><p>Choose a line of business to manage its projects, members, domains, and agents.</p></div>{writable && <button className="primary" type="button" onClick={() => setShowOrganizationForm(true)}>+ Create organization</button>}</div>{showOrganizationForm && <OrganizationForm onCancel={() => setShowOrganizationForm(false)} onSave={async (payload) => { const created = await api.create("organizations", payload); await reload(); setShowOrganizationForm(false); onSelectOrganization({ id: value(created, "id"), name: value(created, "name") }); }} />}{organizations.length ? <div className="organization-directory-grid">{organizations.map((organization) => { const projects = records(organization, "projects"); const members = records(organization, "members"); return <button className="organization-directory-card" type="button" key={value(organization, "id")} onClick={() => onSelectOrganization({ id: value(organization, "id"), name: value(organization, "name") })}><span className="organization-monogram">{value(organization, "name").slice(0, 1).toUpperCase()}</span><span className="directory-card-body"><strong>{value(organization, "name")}</strong><small>{value(organization, "id")}</small><span><b>{projects.length}</b> projects <b>{members.length}</b> members</span></span><span className="directory-arrow">›</span></button>; })}</div> : <div className="empty-state"><strong>No organizations yet</strong><p>Create the first organization to establish a project and Memory Bank governance boundary.</p></div>}</div>;
  }

  const organization = organizations.find((item) => value(item, "id") === selectedOrganization.id);
  if (!organization) return <div className="empty-state"><strong>Organization not found</strong><button type="button" className="secondary" onClick={() => onSelectOrganization(null)}>Return to organizations</button></div>;
  const organizationProjects = records(organization, "projects");
  const organizationMembers = records(organization, "members");
  const project = selectedProject ? organizationProjects.find((item) => value(item, "id") === selectedProject.id) : undefined;
  const organizationRole = value(organization, "current_member_role");
  const canManageOrganization = writable || organizationRole === "OWNER" || organizationRole === "ADMIN";

  if (project) {
    const projectDomains = records(project, "domains");
    const projectMembers = records(project, "members");
    const projectAgents = records(project, "agents");
    const projectRole = value(project, "current_member_role");
    const canManageProject = canManageOrganization || projectRole === "OWNER" || projectRole === "ADMIN";
    return <div className="context-workspace"><button className="back-link" type="button" onClick={() => onSelectProject(null)}>← {value(organization, "name")}</button><div className="context-header"><div className="organization-monogram project-monogram">P</div><div><span className="eyebrow">Project</span><h2>{value(project, "name")}</h2><p>{value(project, "description") || value(project, "id")}</p><small>Immutable ID: {value(project, "id")} · Organization: {value(project, "organization_id")}</small></div><span className="project-team">{value(project, "owner_team")}</span></div><ContextTabs tabs={[["overview", "Overview"], ["domains", "Domains"], ["agents", "Agents"], ["health", "Agent health"], ["members", "Members & Roles"], ["settings", "Settings"]]} selected={projectTab} onSelect={(tab) => { setSelectedResource(null); setSelectedDomainId(null); onProjectTab(tab); }} />{projectTab === "overview" && <div className="overview-grid"><article><span>Domains</span><strong>{projectDomains.length}</strong><p>Preference ownership boundaries</p></article><article><span>Agents</span><strong>{projectAgents.length}</strong><p>Registered project consumers</p></article><article><span>Members</span><strong>{projectMembers.length}</strong><p>Direct project assignments</p></article></div>}{projectTab === "domains" && (selectedDomainId ? <DomainDetail domainId={selectedDomainId} api={api} writable={canManageProject} onBack={() => setSelectedDomainId(null)} /> : <div className="resource-card-grid">{projectDomains.length ? projectDomains.map((domain) => <button className="resource-card" type="button" key={value(domain, "id")} onClick={() => setSelectedDomainId(value(domain, "id"))}><span className="resource-icon">D</span><span><strong>{value(domain, "name")}</strong><small>{value(domain, "id")}</small></span><b>›</b></button>) : <p className="empty">No domains have been created in this project.</p>}</div>)}{projectTab === "agents" && <div className="resource-card-grid">{projectAgents.length ? projectAgents.map((agent) => <button className="resource-card" type="button" key={value(agent, "id")} onClick={() => setSelectedResource({ resource: "agents", record: agent })}><span className="resource-icon">A</span><span><strong>{value(agent, "display_name")}</strong><small>{value(agent, "id")}</small></span><b>›</b></button>) : <p className="empty">No agents are registered in this project.</p>}</div>}{projectTab === "health" && <ProjectHealthPanel projectId={value(project, "id")} api={api} writable={canManageProject} />}{projectTab === "settings" && <ProjectSettingsPanel projectId={value(project, "id")} api={api} writable={canManageProject} />}{projectTab === "members" && <div className="membership-panel"><div className="panel-heading"><div><h3>Project members</h3><p>Direct roles apply only inside this project.</p></div>{canManageProject && <button className="primary" type="button" onClick={() => setShowMemberForm(true)}>+ Add member</button>}</div>{showMemberForm && <MemberForm title={`Add member to ${value(project, "name")}`} onCancel={() => setShowMemberForm(false)} onSave={async (payload) => { await api.addProjectMember(value(project, "id"), payload); await reload(); setShowMemberForm(false); }} />}<div className="member-list">{projectMembers.length ? projectMembers.map((member) => <button className="member-row" type="button" key={value(member, "id")} onClick={() => setSelectedResource({ resource: "project-members", record: member })}><span className="member-avatar">{(value(member, "display_name") || value(member, "member_principal")).slice(0, 1).toUpperCase()}</span><span><strong>{value(member, "display_name") || value(member, "member_principal")}</strong><small>{value(member, "member_principal")}</small></span><span className="role-badge">{value(member, "role")}</span></button>) : <p className="empty">No direct project members.</p>}</div></div>}{selectedResource && <ResourceDetailPanel resource={selectedResource.resource} record={selectedResource.record} writable={canManageProject} api={api} onClose={() => setSelectedResource(null)} onSaved={reload} />}</div>;
  }

  return <div className="context-workspace"><button className="back-link" type="button" onClick={() => onSelectOrganization(null)}>← Organizations</button><div className="context-header"><div className="organization-monogram">{value(organization, "name").slice(0, 1).toUpperCase()}</div><div><span className="eyebrow">Organization</span><h2>{value(organization, "name")}</h2><p>{value(organization, "description") || value(organization, "id")}</p><small>Immutable ID: {value(organization, "id")}</small></div><span className="role-badge">{organizationRole || "Organization active"}</span></div><ContextTabs tabs={[["overview", "Overview"], ["projects", "Projects"], ["approvals", "Approvals"], ["members", "Members & Roles"], ["settings", "Settings"]]} selected={organizationTab} onSelect={onOrganizationTab} />{organizationTab === "overview" && <div className="overview-grid"><article><span>Projects</span><strong>{organizationProjects.length}</strong><p>Collaboration boundaries</p></article><article><span>Members</span><strong>{organizationMembers.length}</strong><p>Organization-level access</p></article><article><span>Domains</span><strong>{organizationProjects.reduce((count, item) => count + records(item, "domains").length, 0)}</strong><p>Owned memory domains</p></article></div>}{organizationTab === "projects" && <div className="organization-panel"><div className="panel-heading"><div><h3>Projects</h3><p>Agents in a project collaborate through project-owned domains.</p></div>{canManageOrganization && <button className="primary" type="button" onClick={() => setShowProjectForm(true)}>+ New project</button>}</div>{showProjectForm && <div className="panel-form"><ProjectForm organizationId={value(organization, "id")} onCancel={() => setShowProjectForm(false)} onSave={async (payload) => { await api.create("projects", payload); await reload(); setShowProjectForm(false); }} /></div>}<div className="project-directory-grid">{organizationProjects.length ? organizationProjects.map((item) => <article className="project-directory-card" key={value(item, "id")}><span className="resource-icon">P</span><div><h4>{value(item, "name")}</h4><p>{value(item, "description") || value(item, "id")}</p><small>{records(item, "domains").length} domains · {records(item, "members").length} members · ID {value(item, "id")}</small></div><button className="primary" type="button" onClick={() => onSelectProject({ id: value(item, "id"), name: value(item, "name") })}>Open project ›</button></article>) : <p className="empty project-empty">No projects in this organization.</p>}</div></div>}{organizationTab === "approvals" && <OrganizationApprovalsPanel organizationId={value(organization, "id")} api={api} />}{organizationTab === "settings" && <OrganizationSettingsPanel organizationId={value(organization, "id")} api={api} writable={canManageOrganization} />}{organizationTab === "members" && <div className="membership-panel"><div className="panel-heading"><div><h3>Members & Roles</h3><p>Organization members can be assigned to projects in this organization.</p></div>{canManageOrganization && <button className="primary" type="button" onClick={() => setShowMemberForm(true)}>+ Add member</button>}</div>{showMemberForm && <MemberForm title={`Add member to ${value(organization, "name")}`} onCancel={() => setShowMemberForm(false)} onSave={async (payload) => { await api.addOrganizationMember(value(organization, "id"), payload); await reload(); setShowMemberForm(false); }} />}<div className="member-list">{organizationMembers.length ? organizationMembers.map((member) => <div key={value(member, "id")}><span className="member-avatar">{(value(member, "display_name") || value(member, "member_principal")).slice(0, 1).toUpperCase()}</span><span><strong>{value(member, "display_name") || value(member, "member_principal")}</strong><small>{value(member, "member_principal")}</small></span><span className="role-badge">{value(member, "role")}</span></div>) : <p className="empty">No members assigned.</p>}</div></div>}</div>;
}

function OrganizationManagement({ identity, api, selectedOrganization, selectedProject, organizationTab, projectTab, onSelectOrganization, onSelectProject, onOrganizationTab, onProjectTab }: { identity: AdminIdentity; api: AdminApiClient; selectedOrganization: ContextSelection; selectedProject: ContextSelection; organizationTab: OrganizationTab; projectTab: ProjectTab; onSelectOrganization: (organization: ContextSelection) => void; onSelectProject: (project: ContextSelection) => void; onOrganizationTab: (tab: OrganizationTab) => void; onProjectTab: (tab: ProjectTab) => void }) {
  const [hierarchy, setHierarchy] = useState<AdminRecord>({ organizations: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => { setLoading(true); try { setHierarchy(await api.organizationHierarchy()); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load organization hierarchy"); } finally { setLoading(false); } }, [api]);
  useEffect(() => { void reload(); }, [reload]);
  return <section><ErrorBanner error={error} />{loading ? <p>Loading organization hierarchy…</p> : <OrganizationHierarchyView hierarchy={hierarchy} writable={canMutate(identity, "organizations")} api={api} reload={reload} selectedOrganization={selectedOrganization} selectedProject={selectedProject} organizationTab={organizationTab} projectTab={projectTab} onSelectOrganization={onSelectOrganization} onSelectProject={onSelectProject} onOrganizationTab={onOrganizationTab} onProjectTab={onProjectTab} />}</section>;
}

function PlatformOverview() {
  const governance: [IconName, string, string][] = [
    ["building", "Organizations", "Define line-of-business ownership, membership, budgets, and approval responsibility."],
    ["project", "Projects", "Create isolated team workspaces for agents, domains, runtime resources, and policies."],
    ["approval", "Identity & approvals", "Use Entra roles, project membership, and explicit approvals to control every change."],
  ];
  const capabilities: [IconName, string, string][] = [
    ["memory", "Memory & personalization", "Model typed preferences, govern schema sharing, and resolve an effective user context."],
    ["agent", "Agent operations", "Register agents, bind Google runtimes, and inspect deployment and health status by project."],
    ["budget", "Budgets & FinOps", "Set organization spending limits, alert thresholds, billing projects, and notification routes."],
    ["observe", "Monitoring & observability", "Track health, latency, error rate, audit history, and runtime provenance from one place."],
  ];
  const lifecycle = [
    ["Organize", "Create the organization and project boundaries that own platform resources."],
    ["Configure", "Register agents, domains, memory schemas, budgets, and runtime bindings."],
    ["Approve", "Route sensitive changes and cross-boundary access to the accountable owner."],
    ["Operate", "Resolve memory, run agents, and monitor health, cost, latency, and failures."],
    ["Improve", "Use audit and observability signals to tune policy, capacity, and agent behavior."],
  ];
  return <section className="dashboard platform-overview"><div className="overview-hero"><div><span className="eyebrow">Enterprise agent control plane</span><h2>Govern, operate, and optimize every agent</h2><p>GEAP gives platform teams one place to organize agents, manage shared memory, enforce approvals, control spend, and observe runtime health across Google Cloud.</p></div><div className="hero-route" aria-label="Platform operating model"><strong><UiIcon name="building" /> Organization</strong><span>→</span><strong><UiIcon name="project" /> Project</strong><span>→</span><strong><UiIcon name="agent" /> Agents &amp; services</strong><span>→</span><strong><UiIcon name="observe" /> Operations</strong></div></div><div className="overview-status"><span className="status-dot"></span><strong>Control Plane connected</strong><span>Start with an organization, create a project, then configure the capabilities your team needs.</span></div><section className="journey-section"><div className="journey-heading"><span>Structure</span><div><h3>Establish ownership and isolation</h3><p>Immutable organization and project IDs keep resources discoverable, attributable, and safely separated.</p></div></div><div className="journey-grid three">{governance.map(([icon, title, description], index) => <article key={title} className="journey-card"><span className="journey-icon"><UiIcon name={icon} /></span><h4>{title}</h4><p>{description}</p>{index < governance.length - 1 && <b className="journey-arrow">→</b>}</article>)}</div></section><section className="journey-section"><div className="journey-heading"><span>Capabilities</span><div><h3>Run the complete agent platform lifecycle</h3><p>Memory is one governed capability alongside runtime operations, financial controls, and observability.</p></div></div><div className="journey-grid four">{capabilities.map(([icon, title, description]) => <article key={title} className="journey-card"><span className="journey-icon"><UiIcon name={icon} /></span><h4>{title}</h4><p>{description}</p></article>)}</div></section><section className="journey-section runtime-journey"><div className="journey-heading"><span>Lifecycle</span><div><h3>Move from onboarding to continuous operation</h3><p>The control plane keeps governance decisions visible throughout build and runtime.</p></div></div><div className="runtime-flow">{lifecycle.map(([title, description], index) => <article key={title}><span>{index + 1}</span><div><h4>{title}</h4><p>{description}</p></div></article>)}</div></section><div className="overview-bottom"><section><span className="eyebrow">Start here</span><h3>Your first platform setup</h3><ol><li>Select an <strong>Organization</strong> and create a project.</li><li>Register agents and configure domains or shared memory schemas.</li><li>Set organization budget thresholds and notification channels.</li><li>Connect each agent to Cloud Run or Google Agent Runtime.</li><li>Review approvals, agent health, cost signals, and audit history.</li></ol></section><section><span className="eyebrow">Platform outcomes</span><h3>What GEAP helps teams enforce</h3><ul className="guarantee-list"><li>Immutable ownership and project-scoped resource discovery</li><li>Owner-controlled writes and approval-based sharing</li><li>Typed memory with deterministic preference resolution</li><li>Budget guardrails and configurable spend notifications</li><li>Auditable agent health, runtime provenance, and decisions</li></ul></section></div></section>;
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
