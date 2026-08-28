import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminApiClient } from "../../api";
import { findNormalizedDuplicates, movePriority, recordId } from "../../governance";
import type { AdminRecord } from "../../types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { parseJson } from "../../lib/records";
import { templates } from "../../lib/templates";

export const editableFields: Record<string, string[]> = {
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

export function editablePayload(resource: string, record: AdminRecord): AdminRecord {
  return Object.fromEntries((editableFields[resource] ?? []).map((key) => [key, record[key]]));
}

export function SchemaAccessRequestForm({ api, organizationId, schemaId, onSubmitted }: { api: AdminApiClient; organizationId: string; schemaId: string; onSubmitted: () => Promise<void> | void }) {
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

export function AgentSchemaAccessEditor({ api, agent, onCancel, onSubmitted }: { api: AdminApiClient; agent: AdminRecord; onCancel: () => void; onSubmitted: () => Promise<void> | void }) {
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

export function SchemaVersionEditor({ api, schema, activeVersion, organizationId, onCancel, onSubmitted }: { api: AdminApiClient; schema: AdminRecord; activeVersion: AdminRecord; organizationId: string; onCancel: () => void; onSubmitted: () => Promise<void> | void }) {
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

export function ResourceDetailPanel({ resource, record, writable, api, contextOrganizationId, onClose, onSaved }: { resource: string; record: AdminRecord; writable: boolean; api: AdminApiClient; contextOrganizationId?: string; onClose: () => void; onSaved: () => Promise<void> | void }) {
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

export function JsonCreateForm({ resource, onCreate }: { resource: string; onCreate: (value: AdminRecord) => Promise<void> }) {
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

export function PriorityEditor({ payload, onChange }: { payload: AdminRecord; onChange: (value: AdminRecord) => void }) {
  const items = Array.isArray(payload.schemaPriorities) ? payload.schemaPriorities as AdminRecord[] : [];
  function move(index: number, direction: -1 | 1) {
    const reordered = movePriority(items, index, direction).map((item, priority) => ({ ...item, priority }));
    onChange({ ...payload, schemaPriorities: reordered });
  }
  return <div className="priorities"><strong>Schema priority</strong>{items.map((item, index) => (
    <div key={String(item.schemaId)}><span>{index + 1}. {String(item.schemaId)}</span><span><button type="button" onClick={() => move(index, -1)} aria-label={`Move ${String(item.schemaId)} up`}>↑</button><button type="button" onClick={() => move(index, 1)} aria-label={`Move ${String(item.schemaId)} down`}>↓</button></span></div>
  ))}</div>;
}

