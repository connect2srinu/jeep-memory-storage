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

  async list(resource: string): Promise<AdminRecord[]> {
    return (await this.request<AdminRecordList>(`/${resource}`)).items;
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

  async decideAccess(
    requestId: string,
    action: "approve" | "reject" | "revoke" | "expire",
    reason: string,
  ): Promise<AdminRecord> {
    return (
      await this.request<AdminRecordEnvelope>(`/access-requests/${requestId}/${action}`, {
        method: "POST",
        body: JSON.stringify({ reason: reason || undefined }),
      })
    ).data;
  }
}
