import { useCallback, useEffect, useMemo, useState } from "react";

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

function ResourceChangeActions({ records, api, reload, approvalsOnly }: { records: AdminRecord[]; api: AdminApiClient; reload: () => void; approvalsOnly: boolean }) {
  const visible = approvalsOnly ? records.filter((record) => record.status === "PENDING") : records;
  async function act(id: string, action: "approve" | "reject") {
    await api.decideResourceChange(id, action, `${action} from Admin Console`);
    reload();
  }
  if (!visible.length) return null;
  return <div className="request-list change-request-list">{visible.map((record) => <article key={recordId(record)}>
    <div><strong>{String(record.resource_type === "schemas" ? "Schema version" : "Domain change")} · {String(record.resource_id)}</strong><p>Requested by {String(record.requested_by)}</p><pre>{JSON.stringify(record.proposed_changes, null, 2)}</pre></div>
    <span className={`pill ${String(record.status).toLowerCase()}`}>{String(record.status)}</span>
    <div className="actions">{record.status === "PENDING" && <><button type="button" onClick={() => act(recordId(record), "approve")}>Approve &amp; publish</button><button className="danger" type="button" onClick={() => act(recordId(record), "reject")}>Reject</button></>}</div>
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
  const [selectedResource, setSelectedResource] = useState<{ resource: string; record: AdminRecord } | null>(null);

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
    return <div className="context-workspace"><button className="back-link" type="button" onClick={() => onSelectProject(null)}>← {value(organization, "name")}</button><div className="context-header"><div className="organization-monogram project-monogram">P</div><div><span className="eyebrow">Project</span><h2>{value(project, "name")}</h2><p>{value(project, "description") || value(project, "id")}</p></div><span className="project-team">{value(project, "owner_team")}</span></div><ContextTabs tabs={[["overview", "Overview"], ["domains", "Domains"], ["agents", "Agents"], ["members", "Members & Roles"]]} selected={projectTab} onSelect={(tab) => { setSelectedResource(null); onProjectTab(tab); }} />{projectTab === "overview" && <div className="overview-grid"><article><span>Domains</span><strong>{projectDomains.length}</strong><p>Preference ownership boundaries</p></article><article><span>Agents</span><strong>{projectAgents.length}</strong><p>Registered project consumers</p></article><article><span>Members</span><strong>{projectMembers.length}</strong><p>Direct project assignments</p></article></div>}{projectTab === "domains" && <div className="resource-card-grid">{projectDomains.length ? projectDomains.map((domain) => <button className="resource-card" type="button" key={value(domain, "id")} onClick={() => setSelectedResource({ resource: "domains", record: domain })}><span className="resource-icon">D</span><span><strong>{value(domain, "name")}</strong><small>{value(domain, "id")}</small></span><b>›</b></button>) : <p className="empty">No domains have been created in this project.</p>}</div>}{projectTab === "agents" && <div className="resource-card-grid">{projectAgents.length ? projectAgents.map((agent) => <button className="resource-card" type="button" key={value(agent, "id")} onClick={() => setSelectedResource({ resource: "agents", record: agent })}><span className="resource-icon">A</span><span><strong>{value(agent, "display_name")}</strong><small>{value(agent, "id")}</small></span><b>›</b></button>) : <p className="empty">No agents are registered in this project.</p>}</div>}{projectTab === "members" && <div className="membership-panel"><div className="panel-heading"><div><h3>Project members</h3><p>Direct roles apply only inside this project.</p></div>{writable && <button className="primary" type="button" onClick={() => setShowMemberForm(true)}>+ Add member</button>}</div>{showMemberForm && <MemberForm title={`Add member to ${value(project, "name")}`} onCancel={() => setShowMemberForm(false)} onSave={async (payload) => { await api.addProjectMember(value(project, "id"), payload); await reload(); setShowMemberForm(false); }} />}<div className="member-list">{projectMembers.length ? projectMembers.map((member) => <button className="member-row" type="button" key={value(member, "id")} onClick={() => setSelectedResource({ resource: "project-members", record: member })}><span className="member-avatar">{(value(member, "display_name") || value(member, "member_principal")).slice(0, 1).toUpperCase()}</span><span><strong>{value(member, "display_name") || value(member, "member_principal")}</strong><small>{value(member, "member_principal")}</small></span><span className="role-badge">{value(member, "role")}</span></button>) : <p className="empty">No direct project members.</p>}</div></div>}{selectedResource && <ResourceDetailPanel resource={selectedResource.resource} record={selectedResource.record} writable={writable} api={api} onClose={() => setSelectedResource(null)} onSaved={reload} />}</div>;
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
  if (section === "dashboard") return <section className="dashboard"><span className="eyebrow">Platform overview</span><h2>Governed memory, ready for every shopping journey</h2><p>Organize agents by line of business and project, reuse approved preference domains, and keep cross-project sharing read-only.</p><div className="metric-grid"><article><span className="metric-icon">O</span><strong>Organization</strong><span>Tenant and policy boundary</span></article><article><span className="metric-icon">P</span><strong>Projects</strong><span>Agent and domain collaboration</span></article><article><span className="metric-icon">M</span><strong>Memory Bank</strong><span>Profiles created lazily per user</span></article></div></section>;
  if (section === "create-setup") return <MemorySetupWizard api={api} />;
  if (section === "organizations") return <OrganizationManagement identity={identity} api={api} {...organizationNavigation} />;
  const writable = canMutate(identity, section);
  const hasPendingApprovals = changeRequests.some((record) => record.status === "PENDING") || records.some((record) => record.status === "PENDING");
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
  return <div className="app-shell"><aside><div className="brand"><span>GEAP</span><div><strong>Portal</strong><small>Control plane</small></div></div><button className="context-switcher" type="button" onClick={openOrganizations}><span>{selectedOrganization ? selectedOrganization.name.slice(0, 1).toUpperCase() : "O"}</span><strong>{selectedOrganization?.name ?? "Organizations"}</strong><b>›</b></button><nav aria-label="Administration">{primarySections.map(([id, label]) => <button type="button" key={id} className={`${id === "create-setup" ? "create-action " : ""}${section === id ? "active" : ""}`} onClick={() => onSection(id)}>{label}</button>)}{selectedOrganization && <div className="contextual-nav"><span>Organization</span><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "overview" ? "active" : ""} onClick={() => chooseOrganizationTab("overview")}>Overview</button><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "projects" ? "active" : ""} onClick={() => chooseOrganizationTab("projects")}>Projects</button><button type="button" className={section === "organizations" && !selectedProject && organizationTab === "members" ? "active" : ""} onClick={() => chooseOrganizationTab("members")}>Members &amp; Roles</button></div>}{selectedProject && <div className="contextual-nav project-context-nav"><span>Project · {selectedProject.name}</span><button type="button" className={section === "organizations" && projectTab === "overview" ? "active" : ""} onClick={() => chooseProjectTab("overview")}>Overview</button><button type="button" className={section === "organizations" && projectTab === "domains" ? "active" : ""} onClick={() => chooseProjectTab("domains")}>Domains</button><button type="button" className={section === "organizations" && projectTab === "agents" ? "active" : ""} onClick={() => chooseProjectTab("agents")}>Agents</button><button type="button" className={section === "organizations" && projectTab === "members" ? "active" : ""} onClick={() => chooseProjectTab("members")}>Members &amp; Roles</button></div>}<details className="advanced-nav" open={advancedSections.some(([id]) => id === section && id !== "organizations")}><summary>Govern &amp; manage</summary>{advancedSections.filter(([id]) => id !== "organizations").map(([id, label]) => <button type="button" key={id} className={section === id ? "active" : ""} onClick={() => onSection(id)}>{label}</button>)}</details></nav></aside><main><header className="topbar"><div><span className={`connection ${status}`}></span>Control Plane API {status}</div><div className="identity"><strong>{identity.user}</strong><span>{identity.roles.join(", ")}</span></div></header><ConsolePage section={section} identity={identity} api={api} organizationNavigation={organizationNavigation} /></main></div>;
}

export default function App() {
  const [section, setSection] = useState("organizations");
  const [status, setStatus] = useState("checking");
  const [user, setUser] = useState("platform-admin@example.com");
  const [role, setRole] = useState<AdminRole>("PLATFORM_ADMIN");
  const [domains, setDomains] = useState("grocery,customer");
  const identity = useMemo<AdminIdentity>(() => ({ user, roles: [role], domains: domains.split(",").map((value) => value.trim()).filter(Boolean) }), [user, role, domains]);
  const api = useMemo(() => new AdminApiClient(import.meta.env.VITE_CONTROL_PLANE_API_URL ?? "/control-plane-api/api/v1/admin", identity), [identity]);
  useEffect(() => { api.health().then((ok) => setStatus(ok ? "connected" : "unavailable")).catch(() => setStatus("unavailable")); }, [api]);
  return <><div className="persona"><label>User<input value={user} onChange={(event) => setUser(event.target.value)} /></label><label>Role<select value={role} onChange={(event) => setRole(event.target.value as AdminRole)}><option>PLATFORM_ADMIN</option><option>DOMAIN_ADMIN</option><option>SCHEMA_OWNER</option><option>AGENT_OWNER</option><option>VIEWER</option></select></label><label>Domains<input value={domains} onChange={(event) => setDomains(event.target.value)} /></label></div><ConsoleShell identity={identity} section={section} status={status} onSection={setSection} /></>;
}
