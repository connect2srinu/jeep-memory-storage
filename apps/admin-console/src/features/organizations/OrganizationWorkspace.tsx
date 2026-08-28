import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminApiClient } from "../../api";
import { canMutate } from "../../governance";
import type { AdminIdentity, AdminRecord } from "../../types";
import { ContextTabs } from "../../components/ContextTabs";
import { ErrorBanner } from "../../components/ErrorBanner";
import { OrganizationApprovalsPanel } from "../approvals/ApprovalsTable";
import { DomainDetail } from "../domain/DomainDetail";
import { ResourceDetailPanel } from "../resources/ResourceDetailPanel";
import { records, value } from "../../lib/records";

export type OrganizationTab = "overview" | "projects" | "approvals" | "members" | "settings";
export type ProjectTab = "overview" | "domains" | "agents" | "health" | "members" | "settings";
export type ContextSelection = { id: string; name: string } | null;

export function OrganizationSettingsPanel({ organizationId, api, writable }: { organizationId: string; api: AdminApiClient; writable: boolean }) {
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

export function ProjectSettingsPanel({ projectId, api, writable }: { projectId: string; api: AdminApiClient; writable: boolean }) {
  const [settings, setSettings] = useState<AdminRecord>({}); const [error, setError] = useState("");
  useEffect(() => { void api.projectSettings(projectId).then(setSettings).catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load project settings")); }, [api, projectId]);
  async function save() { try { setSettings(await api.updateProjectSettings(projectId, { healthRefreshSeconds: Number(settings.health_refresh_seconds || 300), latencyWarningMs: Number(settings.latency_warning_ms || 2000), errorRateWarning: Number(settings.error_rate_warning || 0.05), notificationsEnabled: Boolean(settings.notifications_enabled), notificationChannelIds: String(settings.channel_ids_text || "").split(",").map((item) => item.trim()).filter(Boolean) })); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to save project settings"); } }
  return <div className="settings-panel"><div className="panel-heading"><div><h3>Agent health policy</h3><p>Configure refresh cadence and warning thresholds for project agents.</p></div></div><div className="settings-grid"><label>Refresh interval (seconds)<input type="number" min="30" disabled={!writable} value={value(settings, "health_refresh_seconds") || "300"} onChange={(event) => setSettings({ ...settings, health_refresh_seconds: event.target.value })} /></label><label>Latency warning (ms)<input type="number" min="1" disabled={!writable} value={value(settings, "latency_warning_ms") || "2000"} onChange={(event) => setSettings({ ...settings, latency_warning_ms: event.target.value })} /></label><label>Error-rate warning (0–1)<input type="number" min="0" max="1" step="0.01" disabled={!writable} value={value(settings, "error_rate_warning") || "0.05"} onChange={(event) => setSettings({ ...settings, error_rate_warning: event.target.value })} /></label><label className="toggle-row"><input type="checkbox" disabled={!writable} checked={settings.notifications_enabled !== false} onChange={(event) => setSettings({ ...settings, notifications_enabled: event.target.checked })} /> Enable health notifications</label><label className="wide">Notification channel IDs<input disabled={!writable} defaultValue={(settings.notification_channel_ids as string[] || []).join(", ")} onChange={(event) => setSettings({ ...settings, channel_ids_text: event.target.value })} /></label></div><ErrorBanner error={error} />{writable && <button className="primary" type="button" onClick={save}>Save health policy</button>}</div>;
}

export function ProjectHealthPanel({ projectId, api, writable }: { projectId: string; api: AdminApiClient; writable: boolean }) {
  const [data, setData] = useState<AdminRecord>({ agents: [] }); const [error, setError] = useState(""); const [editing, setEditing] = useState<string | null>(null);
  const load = useCallback(async (refresh = false) => { try { setData(await api.projectHealth(projectId, refresh)); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load agent health"); } }, [api, projectId]);
  useEffect(() => { void load(); }, [load]);
  return <div className="organization-panel"><div className="panel-heading"><div><h3>Agent runtime health</h3><p>Cached provider health is scoped by immutable organization and project IDs.</p></div><button className="primary" type="button" onClick={() => void load(true)}>Refresh from runtime</button></div><ErrorBanner error={error} /><div className="health-grid">{records(data, "agents").map((item) => { const agent = item.agent as AdminRecord; const health = item.health as AdminRecord; const binding = item.binding as AdminRecord | null; const agentId = value(agent, "id"); return <article key={agentId} className="health-card"><div><strong>{value(agent, "display_name")}</strong><span className={`pill ${value(health, "health_status").toLowerCase()}`}>{value(health, "health_status")}</span></div><small>{agentId}</small><dl><dt>Provider</dt><dd>{binding ? value(binding, "provider") : "Not configured"}</dd><dt>Provider status</dt><dd>{value(health, "provider_status")}</dd><dt>Requests (5m)</dt><dd>{value(health, "request_count") || "—"}</dd></dl>{writable && <button className="secondary" type="button" onClick={() => setEditing(editing === agentId ? null : agentId)}>Configure runtime</button>}{editing === agentId && <RuntimeBindingForm agentId={agentId} existing={binding || {}} api={api} onSaved={() => { setEditing(null); void load(); }} />}</article>; })}</div></div>;
}

export function RuntimeBindingForm({ agentId, existing, api, onSaved }: { agentId: string; existing: AdminRecord; api: AdminApiClient; onSaved: () => void }) {
  const [form, setForm] = useState<AdminRecord>({ provider: existing.provider || "GOOGLE_AGENT_RUNTIME", gcpProjectId: existing.gcp_project_id || "", location: existing.location || "us-central1", resourceName: existing.resource_name || "", endpointUrl: existing.endpoint_url || "", environment: existing.environment || "development" }); const [error, setError] = useState("");
  async function save() { try { await api.updateAgentRuntimeBinding(agentId, form); onSaved(); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to save runtime binding"); } }
  return <div className="runtime-form"><label>Provider<select value={String(form.provider)} onChange={(event) => setForm({ ...form, provider: event.target.value })}><option>GOOGLE_AGENT_RUNTIME</option><option>CLOUD_RUN</option><option>ADK_LOCAL</option></select></label><label>GCP project ID<input value={String(form.gcpProjectId)} onChange={(event) => setForm({ ...form, gcpProjectId: event.target.value })} /></label><label>Location<input value={String(form.location)} onChange={(event) => setForm({ ...form, location: event.target.value })} /></label><label>Runtime resource name<input value={String(form.resourceName)} onChange={(event) => setForm({ ...form, resourceName: event.target.value })} /></label><label>Health endpoint URL<input value={String(form.endpointUrl)} onChange={(event) => setForm({ ...form, endpointUrl: event.target.value })} /></label><ErrorBanner error={error} /><button className="primary" type="button" onClick={save}>Save binding</button></div>;
}

export function MemberForm({ title, onSave, onCancel }: { title: string; onSave: (payload: AdminRecord) => Promise<void>; onCancel?: () => void }) {
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

export function ProjectForm({ organizationId, onSave, onCancel }: { organizationId: string; onSave: (payload: AdminRecord) => Promise<void>; onCancel?: () => void }) {
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

export function OrganizationForm({ onSave, onCancel }: { onSave: (payload: AdminRecord) => Promise<void>; onCancel?: () => void }) {
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

export type OrganizationHierarchyViewProps = {
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

export function OrganizationManagement({ identity, api, selectedOrganization, selectedProject, organizationTab, projectTab, onSelectOrganization, onSelectProject, onOrganizationTab, onProjectTab }: { identity: AdminIdentity; api: AdminApiClient; selectedOrganization: ContextSelection; selectedProject: ContextSelection; organizationTab: OrganizationTab; projectTab: ProjectTab; onSelectOrganization: (organization: ContextSelection) => void; onSelectProject: (project: ContextSelection) => void; onOrganizationTab: (tab: OrganizationTab) => void; onProjectTab: (tab: ProjectTab) => void }) {
  const [hierarchy, setHierarchy] = useState<AdminRecord>({ organizations: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => { setLoading(true); try { setHierarchy(await api.organizationHierarchy()); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load organization hierarchy"); } finally { setLoading(false); } }, [api]);
  useEffect(() => { void reload(); }, [reload]);
  return <section><ErrorBanner error={error} />{loading ? <p>Loading organization hierarchy…</p> : <OrganizationHierarchyView hierarchy={hierarchy} writable={canMutate(identity, "organizations")} api={api} reload={reload} selectedOrganization={selectedOrganization} selectedProject={selectedProject} organizationTab={organizationTab} projectTab={projectTab} onSelectOrganization={onSelectOrganization} onSelectProject={onSelectProject} onOrganizationTab={onOrganizationTab} onProjectTab={onProjectTab} />}</section>;
}

