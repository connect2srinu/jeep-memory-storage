import type {
  AdminIdentity,
  AdminRecord,
  AdminRecordEnvelope,
  AdminRecordList,
  ApiErrorEnvelope,
} from "./types";

export class AdminApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code = "REQUEST_FAILED",
    public readonly correlationId?: string,
  ) {
    super(message);
  }
}

export class AdminApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly identity: AdminIdentity,
  ) {}

  private headers(): HeadersInit {
    if (this.identity.accessToken) {
      return {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.identity.accessToken}`,
      };
    }
    return {
      "Content-Type": "application/json",
      "X-Admin-User": this.identity.user,
      "X-Admin-Roles": this.identity.roles.join(","),
      "X-Admin-Domains": this.identity.domains.join(","),
    };
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { ...this.headers(), ...init.headers },
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as Partial<ApiErrorEnvelope>;
      throw new AdminApiError(
        payload.message ?? `Request failed with HTTP ${response.status}`,
        response.status,
        payload.code,
        payload.correlationId,
      );
    }
    return (await response.json()) as T;
  }

  async health(): Promise<boolean> {
    const response = await fetch(`${this.baseUrl.replace(/\/api\/v1\/admin$/, "")}/healthz`);
    return response.ok;
  }

  async list(resource: string, organizationId?: string): Promise<AdminRecord[]> {
    const query = organizationId
      ? `?organizationId=${encodeURIComponent(organizationId)}`
      : "";
    return (await this.request<AdminRecordList>(`/${resource}${query}`)).items;
  }

  async get(resource: string, id: string): Promise<AdminRecord> {
    return (await this.request<AdminRecordEnvelope>(`/${resource}/${encodeURIComponent(id)}`)).data;
  }

  async create(resource: string, payload: AdminRecord): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(`/${resource}`, {
        method: "POST",
        body: JSON.stringify(payload),
      })
    ).data;
  }

  async organizationHierarchy(): Promise<AdminRecord> {
    return (await this.request<AdminRecordEnvelope>("/organization-hierarchy")).data;
  }

  async organizationSettings(organizationId: string): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/organizations/${encodeURIComponent(organizationId)}/settings`,
      )
    ).data;
  }

  async updateOrganizationSettings(
    organizationId: string,
    payload: AdminRecord,
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/organizations/${encodeURIComponent(organizationId)}/settings`,
        { method: "PUT", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async organizationApprovals(organizationId: string): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/organizations/${encodeURIComponent(organizationId)}/approvals`,
      )
    ).data;
  }

  async projectSettings(projectId: string): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/projects/${encodeURIComponent(projectId)}/settings`,
      )
    ).data;
  }

  async updateProjectSettings(projectId: string, payload: AdminRecord): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/projects/${encodeURIComponent(projectId)}/settings`,
        { method: "PUT", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async projectHealth(projectId: string, refresh = false): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/projects/${encodeURIComponent(projectId)}/health${refresh ? "/refresh" : ""}`,
        refresh ? { method: "POST" } : {},
      )
    ).data;
  }

  async updateAgentRuntimeBinding(agentId: string, payload: AdminRecord): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/agents/${encodeURIComponent(agentId)}/runtime-binding`,
        { method: "PUT", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async addOrganizationMember(
    organizationId: string,
    payload: AdminRecord,
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/organizations/${encodeURIComponent(organizationId)}/members`,
        { method: "POST", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async listHouseholds(organizationId: string): Promise<AdminRecord[]> {
    return (
      await this.request<AdminRecordList>(
        `/organizations/${encodeURIComponent(organizationId)}/households`,
      )
    ).items;
  }

  async listHouseholdMembers(
    organizationId: string,
    householdId: string,
  ): Promise<AdminRecord[]> {
    return (
      await this.request<AdminRecordList>(
        `/organizations/${encodeURIComponent(organizationId)}/households/${encodeURIComponent(
          householdId,
        )}/members`,
      )
    ).items;
  }

  async upsertHouseholdMember(
    organizationId: string,
    householdId: string,
    memberId: string,
    payload: AdminRecord,
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/organizations/${encodeURIComponent(organizationId)}/households/${encodeURIComponent(
          householdId,
        )}/members/${encodeURIComponent(memberId)}`,
        { method: "PUT", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async listHouseholdConsents(
    organizationId: string,
    householdId: string,
  ): Promise<AdminRecord[]> {
    return (
      await this.request<AdminRecordList>(
        `/organizations/${encodeURIComponent(organizationId)}/households/${encodeURIComponent(
          householdId,
        )}/consents`,
      )
    ).items;
  }

  async retentionSweep(
    organizationId: string,
    payload: { dryRun: boolean; asOf?: string },
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/organizations/${encodeURIComponent(organizationId)}/retention/sweep`,
        { method: "POST", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async deactivateHouseholdMember(
    organizationId: string,
    householdId: string,
    memberId: string,
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/organizations/${encodeURIComponent(organizationId)}/households/${encodeURIComponent(
          householdId,
        )}/members/${encodeURIComponent(memberId)}`,
        { method: "DELETE" },
      )
    ).data;
  }

  async addProjectMember(projectId: string, payload: AdminRecord): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/projects/${encodeURIComponent(projectId)}/members`,
        { method: "POST", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async previewMemorySetup(payload: AdminRecord): Promise<AdminRecord> {
    return await this.request<AdminRecord>("/memory-setups/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async activateMemorySetup(payload: AdminRecord): Promise<AdminRecord> {
    return await this.request<AdminRecord>("/memory-setups/activate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async update(resource: string, id: string, payload: AdminRecord): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(`/${resource}/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
    ).data;
  }

  async requestDomainChange(id: string, changes: AdminRecord): Promise<AdminRecord> {
    return await this.update("domains", id, { changes });
  }

  async requestSchemaVersion(id: string, payload: AdminRecord): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/schemas/${encodeURIComponent(id)}/versions`,
        { method: "POST", body: JSON.stringify(payload) },
      )
    ).data;
  }

  async agentSchemaAccess(agentId: string): Promise<AdminRecord[]> {
    return (
      await this.request<AdminRecordList>(
        `/agents/${encodeURIComponent(agentId)}/schema-access`,
      )
    ).items;
  }

  async domainDetail(domainId: string): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/domains/${encodeURIComponent(domainId)}/detail`,
      )
    ).data;
  }

  async schemaAgents(schemaId: string): Promise<AdminRecord[]> {
    return (
      await this.request<AdminRecordList>(
        `/schemas/${encodeURIComponent(schemaId)}/agents`,
      )
    ).items;
  }

  async listResourceChanges(): Promise<AdminRecord[]> {
    return await this.list("resource-change-requests");
  }

  async decideResourceChange(
    requestId: string,
    action: "approve" | "reject",
    reason: string,
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(
        `/resource-change-requests/${encodeURIComponent(requestId)}/${action}`,
        { method: "POST", body: JSON.stringify({ reason: reason || undefined }) },
      )
    ).data;
  }

  async decideAccess(
    requestId: string,
    action: "approve" | "reject" | "revoke" | "expire",
    reason: string,
    attributes?: string[],
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(`/access-requests/${requestId}/${action}`, {
        method: "POST",
        body: JSON.stringify({ reason: reason || undefined, attributes }),
      })
    ).data;
  }
}
