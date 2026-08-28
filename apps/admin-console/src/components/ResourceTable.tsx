import { useMemo, useState } from "react";
import { filterRecords, paginateRecords, recordId, sortRecords, type SortDirection } from "../governance";
import type { AdminRecord } from "../types";

export function ResourceTable({ records, onSelect }: { records: AdminRecord[]; onSelect?: (record: AdminRecord) => void }) {
  const columns = useMemo(
    () => Object.keys(records[0] ?? {}).filter(
      (key) => !["created_at", "updated_at", "before_metadata", "after_metadata"].includes(key),
    ),
    [records],
  );
  const [query, setQuery] = useState("");
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("ascending");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const filteredRecords = useMemo(() => filterRecords(records, query, columns), [records, query, columns]);
  const sortedRecords = useMemo(
    () => sortRecords(filteredRecords, sortColumn, sortDirection),
    [filteredRecords, sortColumn, sortDirection],
  );
  const totalPages = Math.max(1, Math.ceil(sortedRecords.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleRecords = useMemo(
    () => paginateRecords(sortedRecords, currentPage, pageSize),
    [sortedRecords, currentPage, pageSize],
  );
  const firstResult = sortedRecords.length ? (currentPage - 1) * pageSize + 1 : 0;
  const lastResult = Math.min(currentPage * pageSize, sortedRecords.length);

  function toggleSort(column: string) {
    if (sortColumn === column) {
      setSortDirection((current) => current === "ascending" ? "descending" : "ascending");
    } else {
      setSortColumn(column);
      setSortDirection("ascending");
    }
    setPage(1);
  }

  if (!records.length) return <p className="empty">No records found.</p>;

  return (
    <div className="data-grid">
      <div className="data-grid-toolbar">
        <label className="resource-search">
          <span>Search resources</span>
          <input
            type="search"
            placeholder="Search all visible fields"
            value={query}
            onChange={(event) => { setQuery(event.target.value); setPage(1); }}
          />
        </label>
        <label className="page-size-control">
          <span>Rows per page</span>
          <select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}>
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr>{columns.map((column) => (
            <th key={column} aria-sort={sortColumn === column ? sortDirection : "none"}>
              <button type="button" className="sort-button" onClick={() => toggleSort(column)} aria-label={`Sort by ${column.replaceAll("_", " ")}`}>
                <span>{column.replaceAll("_", " ")}</span>
                <span aria-hidden="true">{sortColumn === column ? sortDirection === "ascending" ? "▲" : "▼" : "↕"}</span>
              </button>
            </th>
          ))}</tr></thead>
          <tbody>{visibleRecords.map((record, index) => (
            <tr className={onSelect ? "clickable-row" : ""} tabIndex={onSelect ? 0 : undefined} role={onSelect ? "button" : undefined} onClick={() => onSelect?.(record)} onKeyDown={(event) => { if (onSelect && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onSelect(record); } }} key={recordId(record) || index}>{columns.map((column) => (
              <td key={column}>{typeof record[column] === "object" ? JSON.stringify(record[column]) : String(record[column] ?? "—")}</td>
            ))}</tr>
          ))}</tbody>
        </table>
        {!visibleRecords.length && <div className="table-empty">No resources match “{query}”.</div>}
      </div>
      <div className="data-grid-footer">
        <span>{firstResult}–{lastResult} of {sortedRecords.length} resources</span>
        <div className="pagination" aria-label="Table pagination">
          <button type="button" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>Previous</button>
          <strong>Page {currentPage} of {totalPages}</strong>
          <button type="button" disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}>Next</button>
        </div>
      </div>
    </div>
  );
}

