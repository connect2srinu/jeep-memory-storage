import type { AdminIdentity } from "./types";

export function normalizeName(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[^a-z0-9]/g, "");
}

export function findNormalizedDuplicates(values: string[]): string[] {
  const seen = new Map<string, string>();
  const duplicates = new Set<string>();
  for (const value of values.filter(Boolean)) {
    const normalized = normalizeName(value);
    if (seen.has(normalized)) duplicates.add(value);
    else seen.set(normalized, value);
  }
  return [...duplicates];
}

export function canMutate(identity: AdminIdentity, section: string): boolean {
  if (identity.roles.includes("PLATFORM_ADMIN")) return true;
  if (identity.roles.includes("VIEWER") && identity.roles.length === 1) return false;
  if (section === "access-requests") {
    return identity.roles.some((role) => role === "AGENT_OWNER" || role === "DOMAIN_ADMIN");
  }
  if (section === "approvals") {
    return identity.roles.some((role) => role === "SCHEMA_OWNER" || role === "DOMAIN_ADMIN");
  }
  if (section === "agents") {
    return identity.roles.some((role) => role === "AGENT_OWNER" || role === "DOMAIN_ADMIN");
  }
  return identity.roles.some((role) => role === "DOMAIN_ADMIN" || role === "SCHEMA_OWNER");
}

export function movePriority<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const result = [...items];
  [result[index], result[target]] = [result[target], result[index]];
  return result;
}

export function recordId(record: Record<string, unknown>): string {
  return String(record.id ?? record.attribute_id ?? "");
}
