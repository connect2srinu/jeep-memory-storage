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
  if (identity.roles.includes("PLATFORM_USER")) return false;
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

function searchableValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function filterRecords<T extends Record<string, unknown>>(
  records: T[],
  query: string,
  columns?: string[],
): T[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return records;
  return records.filter((record) =>
    (columns ?? Object.keys(record)).some((column) =>
      searchableValue(record[column]).toLocaleLowerCase().includes(normalizedQuery),
    ),
  );
}

export type SortDirection = "ascending" | "descending";

export function sortRecords<T extends Record<string, unknown>>(
  records: T[],
  column: string | null,
  direction: SortDirection,
): T[] {
  if (!column) return records;
  const multiplier = direction === "ascending" ? 1 : -1;
  return records
    .map((record, index) => ({ record, index }))
    .sort((left, right) => {
      const leftValue = left.record[column];
      const rightValue = right.record[column];
      const leftMissing = leftValue === null || leftValue === undefined;
      const rightMissing = rightValue === null || rightValue === undefined;
      if (leftMissing || rightMissing) {
        if (leftMissing && rightMissing) return left.index - right.index;
        return leftMissing ? 1 : -1;
      }
      const comparison =
        typeof leftValue === "number" && typeof rightValue === "number"
          ? leftValue - rightValue
          : searchableValue(leftValue).localeCompare(searchableValue(rightValue), undefined, {
              numeric: true,
              sensitivity: "base",
            });
      return comparison === 0 ? left.index - right.index : comparison * multiplier;
    })
    .map(({ record }) => record);
}

export function paginateRecords<T>(records: T[], page: number, pageSize: number): T[] {
  const safePage = Math.max(1, page);
  const safePageSize = Math.max(1, pageSize);
  const start = (safePage - 1) * safePageSize;
  return records.slice(start, start + safePageSize);
}
