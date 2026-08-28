import { useCallback, useEffect, useState } from "react";
import { AdminApiClient } from "../../api";
import type { AdminRecord } from "../../types";
import { records, value } from "../../lib/records";
import { ContextTabs } from "../../components/ContextTabs";
import { ErrorBanner } from "../../components/ErrorBanner";
import { ApprovalsTable, ResourceChangeActions, formatDate } from "../approvals/ApprovalsTable";

export function accessKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    OWNING_PROJECT_GRANT: "Owning-project grant",
    CROSS_PROJECT_GRANT: "Cross-project grant",
    ELIGIBLE_NOT_GRANTED: "Eligible · not granted",
    REQUEST_PENDING: "Request pending",
    NONE: "No access",
  };
  return labels[kind] ?? kind;
}

export function DomainSchemaAgents({ api, schemaId }: { api: AdminApiClient; schemaId: string }) {
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

export function ResolutionPolicyCard({ title, policy }: { title: string; policy: AdminRecord }) {
  const priorities = records(policy, "schema_priorities");
  const overrides = records(policy, "attribute_overrides");
  return <div className="policy-card"><div className="policy-card-head"><strong>{title}</strong><small>{value(policy, "id")} · v{value(policy, "version")}</small></div>
    {priorities.length
      ? <ol className="precedence">{priorities.map((item) => <li key={String(item.id)}>{String(item.schema_id)}</li>)}</ol>
      : <p className="empty">No schema precedence configured (single-schema resolution).</p>}
    {overrides.length > 0 && <details><summary>{overrides.length} attribute override(s)</summary><ul>{overrides.map((item) => <li key={String(item.id)}>{String(item.attribute_id)}</li>)}</ul></details>}
  </div>;
}

export type DomainTab = "overview" | "schemas" | "preferences" | "access" | "resolution" | "sharing" | "audit";

export function DomainDetail({ domainId, api, writable, onBack }: { domainId: string; api: AdminApiClient; writable: boolean; onBack: () => void }) {
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

