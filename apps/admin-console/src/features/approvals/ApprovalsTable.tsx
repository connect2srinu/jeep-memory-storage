import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminApiClient } from "../../api";
import { recordId } from "../../governance";
import type { AdminRecord } from "../../types";
import { ErrorBanner } from "../../components/ErrorBanner";
import { records } from "../../lib/records";

export function AccessActions({ records, api, reload, approvalsOnly, writable = true }: { records: AdminRecord[]; api: AdminApiClient; reload: () => void; approvalsOnly: boolean; writable?: boolean }) {
  const visible = approvalsOnly ? records.filter((record) => record.status === "PENDING") : records;
  async function act(id: string, action: "approve" | "reject" | "revoke" | "expire") {
    await api.decideAccess(id, action, `${action} from Admin Console`);
    reload();
  }
  return <div className="request-list">{visible.map((record) => <article key={recordId(record)}>
    <div><strong>{String(record.requesting_agent_id)}</strong> → {String(record.target_schema_id)}<p>{String(record.business_reason)}</p></div>
    <span className={`pill ${String(record.status).toLowerCase()}`}>{String(record.status)}</span>
    <div className="actions">{writable && record.status === "PENDING" && <><button type="button" onClick={() => act(recordId(record), "approve")}>Approve</button><button className="danger" type="button" onClick={() => act(recordId(record), "reject")}>Reject</button></>}{writable && record.status === "APPROVED" && <button className="danger" type="button" onClick={() => act(recordId(record), "revoke")}>Revoke</button>}</div>
  </article>)}</div>;
}

export function ResourceChangeActions({ records, api, reload, approvalsOnly, writable = true }: { records: AdminRecord[]; api: AdminApiClient; reload: () => void; approvalsOnly: boolean; writable?: boolean }) {
  const visible = approvalsOnly ? records.filter((record) => record.status === "PENDING") : records;
  async function act(id: string, action: "approve" | "reject") {
    await api.decideResourceChange(id, action, `${action} from Admin Console`);
    reload();
  }
  if (!visible.length) return null;
  return <div className="request-list change-request-list">{visible.map((record) => <article key={recordId(record)}>
    <div><strong>{String(record.resource_type === "schemas" ? "Schema version" : "Domain change")} · {String(record.resource_id)}</strong><p>Requested by {String(record.requested_by)}</p><pre>{JSON.stringify(record.proposed_changes, null, 2)}</pre></div>
    <span className={`pill ${String(record.status).toLowerCase()}`}>{String(record.status)}</span>
    <div className="actions">{writable && record.status === "PENDING" && <><button type="button" onClick={() => act(recordId(record), "approve")}>Approve &amp; publish</button><button className="danger" type="button" onClick={() => act(recordId(record), "reject")}>Reject</button></>}</div>
  </article>)}</div>;
}

export function formatDate(value: unknown): string {
  const raw = String(value ?? "");
  return raw ? raw.slice(0, 10) : "—";
}

export const approvalColumns: Array<[string, string]> = [
  ["direction", "Direction"],
  ["status", "Status"],
  ["requesting_agent_name", "Requester"],
  ["requesting_project_id", "From project"],
  ["owning_domain_id", "Owning domain"],
  ["target_schema_id", "Target schema"],
  ["requested_permission", "Permission"],
  ["requested_at", "Requested"],
];

export function ApprovalsTable({ rows, api, reload, writable }: { rows: AdminRecord[]; api: AdminApiClient; reload: () => void; writable: boolean }) {
  const [direction, setDirection] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState("requested_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const statuses = useMemo(() => Array.from(new Set(rows.map((row) => String(row.status)))).sort(), [rows]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (direction !== "ALL" && String(row.direction ?? "") !== direction) return false;
      if (statusFilter !== "ALL" && String(row.status ?? "") !== statusFilter) return false;
      if (!needle) return true;
      return [row.requesting_agent_name, row.requesting_agent_id, row.requesting_team, row.owning_domain_id, row.target_schema_id, row.requested_by]
        .some((field) => String(field ?? "").toLowerCase().includes(needle));
    });
  }, [rows, direction, statusFilter, query]);
  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av = String(a[sortKey] ?? "");
      const bv = String(b[sortKey] ?? "");
      return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    });
    return copy;
  }, [filtered, sortKey, sortDir]);

  function toggleSort(key: string) {
    if (sortKey === key) setSortDir((current) => (current === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("asc"); }
  }
  async function act(id: string, action: "approve" | "reject" | "revoke") {
    await api.decideAccess(id, action, `${action} from Approvals`);
    reload();
  }

  return <div className="approvals-table data-grid">
    <div className="data-grid-toolbar approvals-toolbar">
      <label className="resource-search"><span>Search</span><input type="search" placeholder="Requester, domain, schema…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
      <label className="filter-control"><span>Direction</span><select value={direction} onChange={(event) => setDirection(event.target.value)}><option value="ALL">All</option><option value="INCOMING">Incoming</option><option value="OUTGOING">Outgoing</option><option value="HISTORY">History</option></select></label>
      <label className="filter-control"><span>Status</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="ALL">All</option>{statuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
    </div>
    <div className="table-wrap"><table><thead><tr>{approvalColumns.map(([key, label]) => (
      <th key={key} aria-sort={sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
        <button type="button" className="sort-button" onClick={() => toggleSort(key)}><span>{label}</span><span aria-hidden="true">{sortKey === key ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span></button>
      </th>
    ))}<th>Actions</th></tr></thead>
    <tbody>{sorted.map((row) => {
      const id = recordId(row);
      const status = String(row.status);
      const isIncoming = String(row.direction ?? "") === "INCOMING";
      return <tr key={id}>
        <td><span className={`dir-pill ${String(row.direction ?? "").toLowerCase()}`}>{String(row.direction ?? "—")}</span></td>
        <td><span className={`status-chip ${status.toLowerCase()}`}>{status}</span></td>
        <td><strong>{String(row.requesting_agent_name || row.requesting_agent_id || "—")}</strong>{row.requesting_team ? <small>{String(row.requesting_team)}</small> : null}</td>
        <td>{String(row.requesting_project_id ?? "—")}</td>
        <td>{String(row.owning_domain_id ?? "—")}</td>
        <td>{String(row.target_schema_id ?? "—")}</td>
        <td>{String(row.requested_permission ?? "—")}</td>
        <td>{formatDate(row.requested_at)}</td>
        <td className="row-actions">{writable && isIncoming && status === "PENDING"
          ? <><button type="button" onClick={() => act(id, "approve")}>Approve</button><button className="danger" type="button" onClick={() => act(id, "reject")}>Reject</button></>
          : writable && isIncoming && status === "APPROVED"
            ? <button className="danger" type="button" onClick={() => act(id, "revoke")}>Revoke</button>
            : <span className="muted">—</span>}</td>
      </tr>;
    })}</tbody></table>
      {!sorted.length && <div className="table-empty">No requests match the current filters.</div>}
    </div>
    <div className="data-grid-footer"><span>{sorted.length} of {rows.length} requests</span></div>
  </div>;
}

export function OrganizationApprovalsPanel({ organizationId, api, writable = true }: { organizationId: string; api: AdminApiClient; writable?: boolean }) {
  const [data, setData] = useState<AdminRecord>({ incoming: [], outgoing: [], history: [] });
  const [error, setError] = useState("");
  const load = useCallback(async () => { try { setData(await api.organizationApprovals(organizationId)); setError(""); } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to load approvals"); } }, [api, organizationId]);
  useEffect(() => { void load(); }, [load]);
  const rows = useMemo(() => [
    ...records(data, "incoming").map((row) => ({ ...row, direction: "INCOMING" })),
    ...records(data, "outgoing").map((row) => ({ ...row, direction: "OUTGOING" })),
    ...records(data, "history").map((row) => ({ ...row, direction: "HISTORY" })),
  ], [data]);
  const pendingIncoming = records(data, "incoming").length;
  return <div className="organization-panel"><div className="panel-heading"><div><h3>Schema access approvals</h3><p>One queue for cross-project schema access. Incoming requests need this organization’s decision; outgoing requests are read-only until the owner approves them.</p></div><span className="count-badge">{pendingIncoming} pending</span></div><ErrorBanner error={error} />{rows.length ? <ApprovalsTable rows={rows} api={api} reload={() => void load()} writable={writable} /> : <div className="empty-state"><strong>No access requests</strong><p>Cross-project schema access requests will appear here for review.</p></div>}</div>;
}

