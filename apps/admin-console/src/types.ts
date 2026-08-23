export type AdminRole =
  | "PLATFORM_ADMIN"
  | "DOMAIN_ADMIN"
  | "SCHEMA_OWNER"
  | "AGENT_OWNER"
  | "VIEWER";

export interface AdminIdentity {
  user: string;
  roles: AdminRole[];
  domains: string[];
}

export type AdminRecord = Record<string, unknown>;

export interface AdminRecordList {
  items: AdminRecord[];
}

export interface AdminRecordEnvelope {
  data: AdminRecord;
}

export interface ApiErrorEnvelope {
  code: string;
  message: string;
  correlationId?: string;
}
