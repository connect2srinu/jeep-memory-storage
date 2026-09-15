import { useEffect, useMemo, useState } from "react";

import { AdminApiClient } from "../../api";
import type { AdminRecord } from "../../types";

type WizardStep =
  | "Use Case"
  | "Preferences"
  | "Scope"
  | "Memory"
  | "Agents"
  | "Sharing"
  | "Resolution"
  | "Review"
  | "Activate";

type CustomPreference = {
  attributeId: string;
  displayName: string;
  description: string;
  dataType: "string" | "boolean" | "integer" | "number";
  allowedValues: string[];
  sensitivity: "normal" | "sensitive" | "restricted";
};

const groceryDefaults = new Set([
  "grocery.dietary_preference",
  "grocery.preferred_store",
  "customer.fulfillment_preference",
  "grocery.allow_substitutions",
]);

function text(record: AdminRecord, key: string): string {
  return String(record[key] ?? "");
}

function preferenceOwner(record: AdminRecord): string {
  return text(record, "canonical_owner_id");
}

export function isRecommended(record: AdminRecord, domain: string): boolean {
  const attribute = text(record, "attribute_id");
  const rules = record.validation_rules as Record<string, unknown> | undefined;
  const recommended = Array.isArray(rules?.recommended_domains)
    ? rules.recommended_domains.map(String)
    : [];
  if (recommended.includes(domain)) return true;
  if (domain === "grocery") return groceryDefaults.has(attribute);
  return preferenceOwner(record) === domain;
}

function move<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function projectDomainOptions(
  domains: AdminRecord[],
  organizationId: string,
  projectId: string,
): AdminRecord[] {
  return domains.filter(
    (item) =>
      String(item.organization_id ?? "") === organizationId &&
      String(item.project_id ?? "") === projectId,
  );
}

export function wizardSteps(sharingEnabled: boolean, schemaCount: number): WizardStep[] {
  const items: WizardStep[] = ["Use Case", "Preferences", "Scope", "Memory", "Agents"];
  if (sharingEnabled) items.push("Sharing");
  if (schemaCount > 1) items.push("Resolution");
  items.push("Review", "Activate");
  return items;
}

type SetupCounts = {
  organizations: number;
  projects: number;
  schemas: number;
  agents: number;
};

const setupOutline: Array<[string, string, string]> = [
  ["Domain", "D", "A line-of-business area that owns its preferences, such as grocery or delivery."],
  ["Scope", "S", "Who the memory belongs to. Per-user memory compiles to organization_id + user_id."],
  ["Schemas", "M", "Typed profile fields. A domain can hold more than one; activation registers them."],
  ["Preferences", "P", "The catalog attributes each schema exposes, reused across teams where approved."],
  ["Agents", "A", "The agents that may read or write, with least-privilege permissions."],
  ["Sharing", "H", "Read access other projects request. Requests stay pending until the owner approves."],
];

export function MemorySetupIntro({ counts, organizationLabel, onStart }: { counts: SetupCounts; organizationLabel: string; onStart: () => void }) {
  return <section className="wizard setup-intro">
    <div className="wizard-heading">
      <div>
        <span className="eyebrow">Guided onboarding</span>
        <h2>Create Memory Setup</h2>
        <p>Governed memory, ready for every journey. Organize agents by line of business and project, reuse approved preference domains, and keep cross-project sharing read-only — without writing YAML or scope dictionaries.</p>
      </div>
    </div>
    <div className="setup-outline">
      {setupOutline.map(([title, mark, detail]) => <article key={title}>
        <span className="setup-outline-mark">{mark}</span>
        <div><strong>{title}</strong><p>{detail}</p></div>
      </article>)}
    </div>
    <div className="scope-callout">
      <strong>Activation never pre-creates user profiles</strong>
      <span>Registering a setup makes its schemas available. A profile is created lazily on the first authorized write, so there is nothing to clean up if a user never sets a preference.</span>
    </div>
    <div className="overview-grid setup-inventory">
      <article><span>Organizations</span><strong>{counts.organizations}</strong><p>Tenant and policy boundaries</p></article>
      <article><span>Projects</span><strong>{counts.projects}</strong><p>Collaboration boundaries</p></article>
      <article><span>Schemas</span><strong>{counts.schemas}</strong><p>In {organizationLabel || "the selected organization"}</p></article>
      <article><span>Agents</span><strong>{counts.agents}</strong><p>In {organizationLabel || "the selected organization"}</p></article>
    </div>
    <div className="setup-intro-actions">
      <button className="primary" type="button" onClick={onStart}>Start setup</button>
      <span>Six guided steps. You can review a non-mutating preview before anything is activated.</span>
    </div>
  </section>;
}

export function MemorySetupWizard({ api }: { api: AdminApiClient }) {
  const [catalog, setCatalog] = useState<AdminRecord[]>([]);
  const [organizations, setOrganizations] = useState<AdminRecord[]>([]);
  const [projects, setProjects] = useState<AdminRecord[]>([]);
  const [domains, setDomains] = useState<AdminRecord[]>([]);
  const [schemas, setSchemas] = useState<AdminRecord[]>([]);
  const [agents, setAgents] = useState<AdminRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("Grocery Personalization");
  const [description, setDescription] = useState("Shared grocery shopping preferences");
  const [team, setTeam] = useState("grocery-platform");
  const [organizationId, setOrganizationId] = useState("retail");
  const [projectId, setProjectId] = useState("shopping");
  const [domain, setDomain] = useState("grocery");
  const [environment, setEnvironment] = useState("development");
  const [selectedPreferences, setSelectedPreferences] = useState<string[]>([]);
  const [customPreferences, setCustomPreferences] = useState<CustomPreference[]>([]);
  const [showCustom, setShowCustom] = useState(false);
  const [customDraft, setCustomDraft] = useState<CustomPreference>({
    attributeId: "grocery.",
    displayName: "",
    description: "",
    dataType: "string",
    allowedValues: [],
    sensitivity: "normal",
  });
  const [scopeType, setScopeType] = useState("USER");
  const [customScopeKeys, setCustomScopeKeys] = useState("organization_id,user_id");
  const [canonical, setCanonical] = useState(true);
  const [dynamicEnabled, setDynamicEnabled] = useState(true);
  const [confidence, setConfidence] = useState(0.85);
  const [confirmation, setConfirmation] = useState(true);
  const [retention, setRetention] = useState(365);
  const [topicRows, setTopicRows] = useState<Array<{ name: string; tier: "normal" | "sensitive" | "restricted"; description: string }>>([
    { name: "shopping", tier: "normal", description: "Grocery shopping cadence, list habits, and store preferences" },
    { name: "products", tier: "normal", description: "" },
    { name: "fulfillment", tier: "normal", description: "Delivery and pickup handling preferences" },
  ]);
  const [advancedMemory, setAdvancedMemory] = useState(false);
  const [agentMode, setAgentMode] = useState<"new" | "existing">("new");
  const [agentId, setAgentId] = useState("grocery-assistant");
  const [agentName, setAgentName] = useState("Grocery Assistant");
  const [permission, setPermission] = useState("READ_WRITE");
  const [sharingEnabled, setSharingEnabled] = useState(false);
  const [sharedSchemaIds, setSharedSchemaIds] = useState<string[]>([]);
  const [precedence, setPrecedence] = useState<string[]>([]);
  const [started, setStarted] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [preview, setPreview] = useState<AdminRecord | null>(null);
  const [activation, setActivation] = useState<AdminRecord | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([
      api.list("organizations"),
      api.list("projects"),
    ])
      .then(([organizationRows, projectRows]) => {
        setOrganizations(organizationRows);
        setProjects(projectRows);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load catalog"))
      .finally(() => setLoading(false));
  }, [api]);

  useEffect(() => {
    if (!organizationId) return;
    setLoading(true);
    Promise.all([
      api.list("preference-catalog", organizationId),
      api.list("schemas", organizationId),
      api.list("agents", organizationId),
      api.list("domains", organizationId),
    ])
      .then(([preferences, profileSchemas, registeredAgents, domainRows]) => {
        setCatalog(preferences);
        setSchemas(profileSchemas);
        setAgents(registeredAgents);
        setDomains(domainRows);
        setSharedSchemaIds((current) => current.filter((id) => profileSchemas.some((item) => text(item, "id") === id)));
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load organization catalog"))
      .finally(() => setLoading(false));
  }, [api, organizationId]);

  useEffect(() => {
    const recommended = catalog
      .filter((item) => isRecommended(item, domain))
      .map((item) => text(item, "attribute_id"));
    setSelectedPreferences(recommended);
    setCustomDraft((current) => ({ ...current, attributeId: `${domain}.` }));
    setAgentId(`${domain}-assistant`);
    setAgentName(`${domain.charAt(0).toUpperCase()}${domain.slice(1)} Assistant`);
  }, [catalog, domain]);

  const projectDomains = useMemo(
    () => projectDomainOptions(domains, organizationId, projectId),
    [domains, organizationId, projectId],
  );

  useEffect(() => {
    if (!projectDomains.length) return;
    setDomain((current) =>
      projectDomains.some((item) => text(item, "id") === current)
        ? current
        : text(projectDomains[0], "id"),
    );
  }, [projectDomains]);

  const externalOwners = useMemo(() => {
    const selected = new Set(selectedPreferences);
    return new Set(
      catalog
        .filter((item) => selected.has(text(item, "attribute_id")))
        .map(preferenceOwner)
        .filter((owner) => owner && owner !== domain),
    );
  }, [catalog, domain, selectedPreferences]);

  const discoverableSchemas = useMemo(
    () => schemas.filter((item) => text(item, "domain_id") !== domain && text(item, "status") === "ACTIVE"),
    [domain, schemas],
  );

  useEffect(() => {
    const recommendedSchemas = discoverableSchemas
      .filter((item) => externalOwners.has(text(item, "domain_id")))
      .map((item) => text(item, "id"));
    setSharedSchemaIds(recommendedSchemas);
    setSharingEnabled(recommendedSchemas.length > 0);
  }, [discoverableSchemas, externalOwners]);

  const ownedSchemaId = `${domain}-preferences-v1`;
  const availableSchemas = useMemo(
    () => [ownedSchemaId, ...sharedSchemaIds],
    [ownedSchemaId, sharedSchemaIds],
  );

  useEffect(() => setPrecedence(availableSchemas), [availableSchemas]);

  const steps = useMemo<WizardStep[]>(() => {
    return wizardSteps(sharingEnabled, availableSchemas.length);
  }, [availableSchemas.length, sharingEnabled]);
  const step = steps[Math.min(stepIndex, steps.length - 1)];

  function togglePreference(attribute: string) {
    setSelectedPreferences((current) =>
      current.includes(attribute)
        ? current.filter((item) => item !== attribute)
        : [...current, attribute],
    );
    setPreview(null);
  }

  function addCustomPreference() {
    if (!customDraft.attributeId.startsWith(`${domain}.`) || !customDraft.displayName || !customDraft.description) {
      setError(`Custom preferences require a ${domain}. attribute ID, display name, and description.`);
      return;
    }
    setCustomPreferences((current) => [...current.filter((item) => item.attributeId !== customDraft.attributeId), customDraft]);
    setSelectedPreferences((current) => [...new Set([...current, customDraft.attributeId])]);
    setShowCustom(false);
    setError("");
  }

  const payload = useMemo<AdminRecord>(() => ({
    useCase: {
      name,
      description,
      owningTeam: team,
      organizationId,
      projectId,
      domain,
      environment,
    },
    selectedPreferences,
    customPreferences,
    scope: {
      type: scopeType,
      customKeys: scopeType === "CUSTOM"
        ? customScopeKeys.split(",").map((item) => item.trim()).filter(Boolean)
        : [],
    },
    memory: {
      canonical,
      dynamicEnabled,
      confidenceThreshold: confidence,
      confirmationRequired: confirmation,
      retentionDays: retention,
      memoryTopics: dynamicEnabled
        ? topicRows
            .map((row) => ({ name: row.name.trim(), tier: row.tier }))
            .filter((row) => row.name)
            .map((row) => (row.tier === "normal" ? row.name : `${row.name}:${row.tier}`))
        : [],
      topicDefinitions: dynamicEnabled
        ? Object.fromEntries(
            topicRows
              .filter((row) => row.name.trim() && row.description.trim())
              .map((row) => [row.name.trim(), row.description.trim()]),
          )
        : {},
    },
    agent: {
      id: agentId,
      displayName: agentName,
      existing: agentMode === "existing",
      runtimeType: "ADK_LOCAL",
      identityType: "LOCAL_POC",
      principal: null,
      ownedSchemaPermission: permission,
    },
    sharedSchemas: sharedSchemaIds.map((schemaId) => ({ schemaId, permission: "READ" })),
    resolution: availableSchemas.length > 1
      ? { schemaPrecedence: precedence, attributeOverrides: [] }
      : null,
  }), [
    agentId, agentMode, agentName, availableSchemas.length, canonical, confidence,
    confirmation, customPreferences, customScopeKeys, description, domain, dynamicEnabled,
    environment, name, organizationId, permission, precedence, projectId, retention, scopeType, selectedPreferences,
    sharedSchemaIds, team, topicRows,
  ]);

  async function generatePreview() {
    setSubmitting(true);
    setError("");
    try {
      setPreview(await api.previewMemorySetup(payload));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to validate setup");
    } finally {
      setSubmitting(false);
    }
  }

  async function activate() {
    setSubmitting(true);
    setError("");
    try {
      setActivation(await api.activateMemorySetup(payload));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to activate setup");
    } finally {
      setSubmitting(false);
    }
  }

  function next() {
    setError("");
    if (step === "Use Case" && (!name || !description || !team || !organizationId || !projectId || !domain)) {
      setError("Complete every use-case field before continuing.");
      return;
    }
    if (step === "Preferences" && !selectedPreferences.length) {
      setError("Select or create at least one preference.");
      return;
    }
    if (step === "Agents" && !agentId) {
      setError("Select or register an agent.");
      return;
    }
    setStepIndex((current) => Math.min(current + 1, steps.length - 1));
  }

  if (!started) return <MemorySetupIntro counts={{ organizations: organizations.length, projects: projects.length, schemas: schemas.length, agents: agents.length }} organizationLabel={organizationId} onStart={() => setStarted(true)} />;

  if (loading) return <section className="wizard"><p>Loading enterprise catalog…</p></section>;

  return <section className="wizard">
    <div className="wizard-heading">
      <div><span className="eyebrow">Guided onboarding</span><h2>Create Memory Setup</h2><p>Configure a governed profile without writing YAML or scope dictionaries.</p></div>
      <span className="environment-pill">{environment}</span>
    </div>
    <ol className="progress" aria-label="Memory setup progress">
      {steps.map((item, index) => <li key={item} className={index === stepIndex ? "current" : index < stepIndex ? "complete" : ""}><span>{index + 1}</span>{item}</li>)}
    </ol>
    {error && <div className="alert error" role="alert">{error}</div>}
    <div className="wizard-card">
      {step === "Use Case" && <>
        <h3>Define the business use case</h3><p>These values establish ownership and naming for the generated resources.</p>
        <div className="form-grid">
          <label>Use case name<input value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>Organization<select value={organizationId} onChange={(event) => { setOrganizationId(event.target.value); setProjectId(""); }}><option value="">Select organization</option>{organizations.map((item) => <option key={text(item, "id")} value={text(item, "id")}>{text(item, "name")}</option>)}</select><small>Line-of-business and tenant boundary</small></label>
          <label>Project<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Select project</option>{projects.filter((item) => text(item, "organization_id") === organizationId).map((item) => <option key={text(item, "id")} value={text(item, "id")}>{text(item, "name")}</option>)}</select><small>Agents share project-owned domains</small></label>
          <label>Domain<input list="domain-options" value={domain} onChange={(event) => setDomain(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} /><datalist id="domain-options">{projectDomains.map((item) => <option key={text(item, "id")} value={text(item, "id")}>{text(item, "name")}</option>)}</datalist><small>{projectDomains.length ? "Choose an existing domain in this project, or type a new one to create it." : "No domains in this project yet — type a name to create the first."}</small></label>
          <label className="wide">Description<textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <label>Owning team<input value={team} onChange={(event) => setTeam(event.target.value)} /></label>
          <label>Environment<select value={environment} onChange={(event) => setEnvironment(event.target.value)}><option value="development">Development</option><option value="test">Test</option><option value="production">Production</option></select></label>
        </div>
      </>}
      {step === "Preferences" && <>
        <h3>Select reusable preferences</h3><p>Recommended attributes are preselected. Attributes owned elsewhere are handled through shared access.</p>
        <div className="catalog-grid">{catalog.map((item) => {
          const attribute = text(item, "attribute_id");
          const recommended = isRecommended(item, domain);
          return <label className={`catalog-card ${selectedPreferences.includes(attribute) ? "selected" : ""}`} key={attribute}>
            <input type="checkbox" checked={selectedPreferences.includes(attribute)} onChange={() => togglePreference(attribute)} />
            <span><strong>{text(item, "display_name")}</strong>{recommended && <em>Recommended</em>}<small>{attribute} · {preferenceOwner(item)}</small><p>{text(item, "description")}</p></span>
          </label>;
        })}</div>
        {customPreferences.map((item) => <div className="custom-row" key={item.attributeId}><strong>{item.displayName}</strong><span>{item.attributeId}</span><span className="pill">{item.sensitivity}</span></div>)}
        <button className="secondary" type="button" onClick={() => setShowCustom((value) => !value)}>+ Create custom preference</button>
        {showCustom && <div className="inline-editor"><label>Attribute ID<input value={customDraft.attributeId} onChange={(event) => setCustomDraft({ ...customDraft, attributeId: event.target.value })} /></label><label>Display name<input value={customDraft.displayName} onChange={(event) => setCustomDraft({ ...customDraft, displayName: event.target.value })} /></label><label className="wide">Description<input value={customDraft.description} onChange={(event) => setCustomDraft({ ...customDraft, description: event.target.value })} /></label><label>Datatype<select value={customDraft.dataType} onChange={(event) => setCustomDraft({ ...customDraft, dataType: event.target.value as CustomPreference["dataType"] })}><option>string</option><option>boolean</option><option>integer</option><option>number</option></select></label><label>Allowed values<input placeholder="comma separated" onChange={(event) => setCustomDraft({ ...customDraft, allowedValues: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) })} /></label><label>Sensitivity<select value={customDraft.sensitivity} onChange={(event) => setCustomDraft({ ...customDraft, sensitivity: event.target.value as CustomPreference["sensitivity"] })}><option value="normal">Non-sensitive</option><option value="sensitive">Sensitive</option><option value="restricted">Restricted</option></select></label><button className="primary" type="button" onClick={addCustomPreference}>Add preference</button></div>}
      </>}
      {step === "Scope" && <>
        <h3>Choose who the memory belongs to</h3><p>The platform generates provider scope keys from this business-level selection.</p>
        <div className="choice-grid">{[["USER", "Per User", "One profile per user"], ["HOUSEHOLD", "Per Household", "Shared household profile"], ["USER_STORE", "Per User + Store", "Different values per store"], ["CUSTOM", "Custom", "Advanced scope keys"]].map(([value, title, detail]) => <label className={scopeType === value ? "choice selected" : "choice"} key={value}><input type="radio" name="scope" checked={scopeType === value} onChange={() => setScopeType(value)} /><strong>{title}</strong><span>{detail}</span></label>)}</div>
        <div className="scope-callout"><strong>Organization isolation</strong><span>Memory Bank profiles use organization_id + user_id. Projects and domains are enforced by the control-plane authorization layer.</span></div>
        {scopeType === "CUSTOM" && <label className="advanced-field">Custom keys<input value={customScopeKeys} onChange={(event) => setCustomScopeKeys(event.target.value)} /><small>Comma separated. organization_id is always included.</small></label>}
      </>}
      {step === "Memory" && <>
        <h3>Configure memory behavior</h3>
        <label className="switch-row"><span><strong>Canonical preferences</strong><small>Generate governed structured profile fields</small></span><input type="checkbox" checked={canonical} onChange={(event) => setCanonical(event.target.checked)} /></label>
        <label className="switch-row"><span><strong>Dynamic and inferred memory</strong><small>Allow relevant facts beyond canonical fields</small></span><input type="checkbox" checked={dynamicEnabled} onChange={(event) => setDynamicEnabled(event.target.checked)} /></label>
        {dynamicEnabled && <div className="form-grid"><label>Confidence threshold<input type="number" min="0" max="1" step="0.05" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} /></label><label>Retention days<input type="number" min="1" value={retention} onChange={(event) => setRetention(Number(event.target.value))} /></label><div className="wide"><label>Approved memory topics<small>Categories dynamic memory may retain. Set a sensitivity per topic — sensitive/restricted topics require user-directed writes and are flagged in the snapshot.</small></label><div className="topic-editor">{topicRows.map((row, index) => <div key={index} className="topic-row" style={{ display: "flex", flexDirection: "column", gap: "4px", marginBottom: "10px" }}><div style={{ display: "flex", gap: "8px", alignItems: "center" }}><input style={{ flex: 1 }} value={row.name} placeholder="topic" onChange={(event) => setTopicRows((rows) => rows.map((current, i) => i === index ? { ...current, name: event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "") } : current))} /><select value={row.tier} onChange={(event) => setTopicRows((rows) => rows.map((current, i) => i === index ? { ...current, tier: event.target.value as "normal" | "sensitive" | "restricted" } : current))}><option value="normal">Non-sensitive</option><option value="sensitive">Sensitive</option><option value="restricted">Restricted</option></select><button type="button" className="link-button" onClick={() => setTopicRows((rows) => rows.filter((_, i) => i !== index))}>Remove</button></div><input value={row.description} placeholder="What this topic means for this domain (helps the agent map statements)" onChange={(event) => setTopicRows((rows) => rows.map((current, i) => i === index ? { ...current, description: event.target.value } : current))} /></div>)}<button type="button" className="secondary" onClick={() => setTopicRows((rows) => [...rows, { name: "", tier: "normal", description: "" }])}>+ Add topic</button></div></div><label className="check"><input type="checkbox" checked={confirmation} onChange={(event) => setConfirmation(event.target.checked)} /> Require user confirmation</label></div>}
        <button className="link-button" type="button" onClick={() => setAdvancedMemory((value) => !value)}>{advancedMemory ? "Hide" : "Show"} advanced settings</button>
        {advancedMemory && <pre className="mini-preview">source priority: SESSION → EXPLICIT → PROFILE → DYNAMIC{"\n"}profile generation: lazy; no user instances are pre-created</pre>}
      </>}
      {step === "Agents" && <>
        <h3>Register or select an agent</h3>
        <div className="segmented"><button className={agentMode === "new" ? "active" : ""} onClick={() => setAgentMode("new")}>Register new</button><button className={agentMode === "existing" ? "active" : ""} onClick={() => setAgentMode("existing")}>Select existing</button></div>
        {agentMode === "existing" ? <label>Agent<select value={agentId} onChange={(event) => { setAgentId(event.target.value); setAgentName(text(agents.find((item) => text(item, "id") === event.target.value) ?? {}, "display_name")); }}><option value="">Choose an agent</option>{agents.filter((item) => text(item, "domain_id") === domain && text(item, "status") === "ACTIVE").map((item) => <option key={text(item, "id")} value={text(item, "id")}>{text(item, "display_name")}</option>)}</select></label> : <div className="form-grid"><label>Agent ID<input value={agentId} onChange={(event) => setAgentId(event.target.value)} /></label><label>Display name<input value={agentName} onChange={(event) => setAgentName(event.target.value)} /></label></div>}
        <label>Owned schema access<select value={permission} onChange={(event) => setPermission(event.target.value)}><option>READ</option><option>WRITE</option><option>READ_WRITE</option></select></label>
        <label className="switch-row"><span><strong>Discover shared schemas</strong><small>Request read access to profiles owned by other teams</small></span><input type="checkbox" checked={sharingEnabled} onChange={(event) => { setSharingEnabled(event.target.checked); if (!event.target.checked) setSharedSchemaIds([]); }} /></label>
      </>}
      {step === "Sharing" && <>
        <h3>Request shared schema access</h3><p>Requests remain pending until each target schema owner approves them.</p>
        <div className="catalog-grid">{discoverableSchemas.map((item) => { const id = text(item, "id"); const visibility = text(item, "visibility"); const access = text(item, "access_status"); return <label className={`catalog-card ${sharedSchemaIds.includes(id) ? "selected" : ""}`} key={id}><input type="checkbox" checked={sharedSchemaIds.includes(id)} onChange={() => setSharedSchemaIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])} /><span><strong>{text(item, "display_name")}</strong><small>{id} · owner {text(item, "domain_id")} · {visibility.toLowerCase()}</small><p>{access === "APPROVED" ? "Approved READ access" : access === "PENDING" ? "Access request pending" : "Selecting submits a READ request"}</p></span></label>; })}</div>
      </>}
      {step === "Resolution" && <>
        <h3>Set schema precedence</h3><p>The first schema wins when higher-priority resolution strategies tie.</p>
        <div className="priority-list">{precedence.map((schemaId, index) => <div key={schemaId}><span><b>{index + 1}</b>{schemaId}</span><span><button onClick={() => setPrecedence(move(precedence, index, -1))}>↑</button><button onClick={() => setPrecedence(move(precedence, index, 1))}>↓</button></span></div>)}</div>
        <details><summary>Attribute-level overrides</summary><p>Advanced overrides remain available in Manage / Advanced after activation.</p></details>
      </>}
      {step === "Review" && <>
        <h3>Review generated configuration</h3>
        <div className="summary-grid"><div><span>Use case</span><strong>{name}</strong></div><div><span>Domain</span><strong>{domain}</strong></div><div><span>Preferences</span><strong>{selectedPreferences.length}</strong></div><div><span>Scope</span><strong>{scopeType}</strong></div><div><span>Agent</span><strong>{agentId}</strong></div><div><span>Approvals</span><strong>{sharedSchemaIds.length}</strong></div></div>
        <button className="primary" type="button" disabled={submitting} onClick={generatePreview}>{submitting ? "Validating…" : "Validate and generate preview"}</button>
        {preview && <><div className="alert success">Configuration is valid. No user profile instances will be created.</div>{Array.isArray(preview.warnings) && preview.warnings.map((warning) => <div className="alert warning" key={String(warning)}>{String(warning)}</div>)}<details><summary>Advanced YAML preview / export</summary><pre className="yaml-preview">{String(preview.generatedYaml)}</pre><button className="secondary" onClick={() => navigator.clipboard.writeText(String(preview.generatedYaml))}>Copy YAML</button></details></>}
      </>}
      {step === "Activate" && <>
        <h3>Submit and activate</h3><p>The platform will persist and activate owned resources, create the owned schema grant, register the schema with the configured runtime backend, and submit external access requests.</p>
        {!activation && <button className="primary activate-button" type="button" disabled={submitting} onClick={activate}>{submitting ? "Activating…" : "Activate memory setup"}</button>}
        {activation && <div className="activation-result"><span className="success-mark">✓</span><h3>{String(activation.status).replaceAll("_", " ")}</h3><p>Schema <strong>{String((activation.resources as AdminRecord)?.schemaId)}</strong> is ready for lazy profile creation.</p><pre>{JSON.stringify(activation.provisioning, null, 2)}</pre>{Array.isArray(activation.pendingApprovals) && activation.pendingApprovals.length > 0 && <p>{activation.pendingApprovals.length} shared access request(s) are pending owner approval.</p>}</div>}
      </>}
    </div>
    <div className="wizard-actions"><button className="secondary" type="button" disabled={stepIndex === 0 || submitting} onClick={() => setStepIndex((current) => Math.max(0, current - 1))}>Back</button>{step !== "Activate" && <button className="primary" type="button" disabled={submitting || (step === "Review" && !preview)} onClick={next}>Continue</button>}</div>
  </section>;
}
