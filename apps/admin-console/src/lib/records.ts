import type { AdminRecord } from "../types";

export function parseJson(value: string): AdminRecord {
  const parsed: unknown = JSON.parse(value);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("JSON must contain an object");
  }
  return parsed as AdminRecord;
}

export function value(record: AdminRecord, key: string): string {
  return String(record[key] ?? "");
}

export function records(record: AdminRecord, key: string): AdminRecord[] {
  return Array.isArray(record[key]) ? record[key] as AdminRecord[] : [];
}

