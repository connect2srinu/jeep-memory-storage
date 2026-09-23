import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminApiClient } from "../../api";
import { ErrorBanner } from "../../components/ErrorBanner";
import type { AdminIdentity, AdminRecord } from "../../types";

function value(record: AdminRecord, key: string): string {
  return String(record[key] ?? "");
}

function flag(record: AdminRecord, key: string): boolean {
  return record[key] === true || record[key] === "true";
}

function when(record: AdminRecord, key: string): string {
  const raw = value(record, key);
  return raw ? new Date(raw).toLocaleString() : "";
}

const KIND_LABELS: Record<string, string> = {
  ROOT: "Account holder",
  DEPENDENT: "Dependent",
  PROXY_ADULT: "Other adult",
};

type MemberDraft = {
  memberId: string;
  displayName: string;
  relationship: string;
  hasLogin: boolean;
  isGuardian: boolean;
  minor: boolean;
};

const emptyDraft: MemberDraft = {
  memberId: "",
  displayName: "",
  relationship: "member",
  hasLogin: false,
  isGuardian: false,
  minor: false,
};

export function HouseholdsWorkspace({
  identity,
  api,
  organizationId,
}: {
  identity: AdminIdentity;
  api: AdminApiClient;
  organizationId?: string | null;
}) {
  const writable = identity.roles.includes("PLATFORM_ADMIN");
  const [organizations, setOrganizations] = useState<AdminRecord[]>([]);
  const [org, setOrg] = useState<string>(organizationId ?? "");
  const [households, setHouseholds] = useState<AdminRecord[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [members, setMembers] = useState<AdminRecord[]>([]);
  const [consents, setConsents] = useState<AdminRecord[]>([]);
  const [newHousehold, setNewHousehold] = useState("");
  const [draft, setDraft] = useState<MemberDraft>(emptyDraft);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .list("organizations")
      .then((rows) => {
        setOrganizations(rows);
        setOrg((current) => {
          if (current) return current;
          if (organizationId) return organizationId;
          // Prefer a real line-of-business org over the platform "default-org", so a roster is not
          // silently enrolled under an organization the agent/domain does not belong to.
          const real = rows.find((row) => value(row, "id") !== "default-org");
          return value(real ?? rows[0] ?? {}, "id");
        });
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Unable to load"));
  }, [api, organizationId]);

  const loadHouseholds = useCallback(async () => {
    if (!org) return;
    setLoading(true);
    try {
      setHouseholds(await api.listHouseholds(org));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load households");
    } finally {
      setLoading(false);
    }
  }, [api, org]);

  useEffect(() => {
    setSelected(null);
    setMembers([]);
    setConsents([]);
    void loadHouseholds();
  }, [loadHouseholds]);

  const loadMembers = useCallback(
    async (householdId: string) => {
      try {
        const [memberRows, consentRows] = await Promise.all([
          api.listHouseholdMembers(org, householdId),
          api.listHouseholdConsents(org, householdId),
        ]);
        setMembers(memberRows);
        setConsents(consentRows);
        setError("");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Unable to load members");
      }
    },
    [api, org],
  );

  function selectHousehold(householdId: string) {
    setSelected(householdId);
    setDraft(emptyDraft);
    void loadMembers(householdId);
  }

  function createHousehold() {
    const id = newHousehold.trim();
    if (!id) return;
    setNewHousehold("");
    setSelected(id);
    setMembers([]);
    setConsents([]);
    setDraft(emptyDraft);
  }

  async function saveMember() {
    if (!selected || !draft.memberId.trim()) {
      setError("A member id is required.");
      return;
    }
    try {
      await api.upsertHouseholdMember(org, selected, draft.memberId.trim(), {
        displayName: draft.displayName.trim() || undefined,
        relationship: draft.relationship.trim() || "member",
        hasLogin: draft.hasLogin,
        isGuardian: draft.isGuardian,
        minor: draft.minor,
      });
      setDraft(emptyDraft);
      await loadMembers(selected);
      await loadHouseholds();
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save member");
    }
  }

  async function removeMember(memberId: string) {
    if (!selected) return;
    try {
      await api.deactivateHouseholdMember(org, selected, memberId);
      await loadMembers(selected);
      await loadHouseholds();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to remove member");
    }
  }

  const current = useMemo(
    () => members.filter((item) => ["active", "provisional"].includes(value(item, "status"))),
    [members],
  );
  const retired = useMemo(
    () => members.filter((item) => !["active", "provisional"].includes(value(item, "status"))),
    [members],
  );
  const names = useMemo(
    () =>
      Object.fromEntries(
        members.map((item) => [
          value(item, "member_id"),
          value(item, "display_name") || value(item, "member_id"),
        ]),
      ),
    [members],
  );

  return (
    <section className="households-workspace">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Control plane</span>
          <h2>Households</h2>
          <p>
            A household is created automatically the first time a customer uses an agent — the
            logged-in customer is its account holder. People they mention (children, other adults)
            are added after the customer confirms. Use this screen to inspect and support households.
          </p>
        </div>
        <label className="household-org-select">
          Organization
          <select value={org} onChange={(event) => setOrg(event.target.value)}>
            {organizations.map((item) => (
              <option key={value(item, "id")} value={value(item, "id")}>
                {value(item, "name") || value(item, "id")}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ErrorBanner error={error} />
      {!writable && <p className="read-only">Platform Administrator role is required to edit.</p>}
      <div className="households-grid">
        <div className="household-list">
          <h3>Households</h3>
          {loading ? (
            <p className="empty">Loading…</p>
          ) : households.length ? (
            households.map((item) => {
              const id = value(item, "household_id");
              return (
                <button
                  key={id}
                  type="button"
                  className={`household-row ${selected === id ? "selected" : ""}`}
                  onClick={() => selectHousehold(id)}
                >
                  <strong>{id}</strong>
                  <small>
                    {value(item, "member_count")} members · {value(item, "guardian_count")} guardian
                    (s)
                  </small>
                </button>
              );
            })
          ) : (
            <p className="empty">No households yet. They appear when a customer first uses an agent.</p>
          )}
          {writable && (
            <div className="new-household">
              <input
                value={newHousehold}
                placeholder="new-household-id"
                onChange={(event) =>
                  setNewHousehold(event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))
                }
              />
              <button className="secondary" type="button" onClick={createHousehold}>
                + New household
              </button>
            </div>
          )}
          {org && <RetentionPanel api={api} organizationId={org} writable={writable} />}
        </div>

        <div className="household-detail">
          {selected ? (
            <>
              <h3>
                Members of <span className="household-id">{selected}</span>
              </h3>
              <div className="member-list">
                {current.length ? (
                  current.map((item) => {
                    const memberId = value(item, "member_id");
                    const aliases = (item.aliases as string[] | undefined) ?? [];
                    return (
                      <div
                        className={`member-row ${value(item, "status") === "provisional" ? "provisional" : ""}`}
                        key={memberId}
                      >
                        <span>
                          <strong>{value(item, "display_name") || "(account holder)"}</strong>
                          <small>
                            {memberId} · {value(item, "relationship")}
                            {value(item, "login_id") && ` · login ${value(item, "login_id")}`}
                          </small>
                          {aliases.length > 0 && (
                            <small className="aliases">Also known as: {aliases.join(", ")}</small>
                          )}
                        </span>
                        <span className="member-flags">
                          <span className="pill">
                            {KIND_LABELS[value(item, "member_kind")] ?? value(item, "member_kind")}
                          </span>
                          {flag(item, "minor") && <span className="pill minor">minor</span>}
                          {flag(item, "is_guardian") && <span className="pill">guardian</span>}
                          {value(item, "status") === "provisional" && (
                            <span className="pill pending">awaiting confirmation</span>
                          )}
                          <span className="pill provenance">{value(item, "provenance")}</span>
                          {writable && (
                            <button
                              type="button"
                              className="link-button"
                              onClick={() => removeMember(memberId)}
                            >
                              Remove
                            </button>
                          )}
                        </span>
                      </div>
                    );
                  })
                ) : (
                  <p className="empty">No members yet.</p>
                )}
                {retired.map((item) => (
                  <div className="member-row inactive" key={value(item, "member_id")}>
                    <span>
                      <strong>{value(item, "display_name") || value(item, "member_id")}</strong>
                      <small>
                        {value(item, "member_id")} · {value(item, "status")}
                        {value(item, "merged_into_member_id") &&
                          ` into ${names[value(item, "merged_into_member_id")] ?? value(item, "merged_into_member_id")}`}
                      </small>
                    </span>
                  </div>
                ))}
              </div>

              <div className="consent-ledger">
                <h4>Health-data consent ledger</h4>
                {consents.length ? (
                  <table>
                    <thead>
                      <tr>
                        <th>About</th>
                        <th>Attribute</th>
                        <th>Status</th>
                        <th>Question shown to the customer</th>
                        <th>Requested</th>
                        <th>Granted / withdrawn</th>
                      </tr>
                    </thead>
                    <tbody>
                      {consents.map((item) => (
                        <tr key={value(item, "id")}>
                          <td>
                            {names[value(item, "subject_member_id")] ??
                              (value(item, "subject_member_id") || "household")}
                          </td>
                          <td>{value(item, "attribute_id")}</td>
                          <td>
                            <span className={`pill ${value(item, "status").toLowerCase()}`}>
                              {value(item, "status")}
                            </span>
                          </td>
                          <td>{value(item, "prompt_text")}</td>
                          <td>{when(item, "requested_at")}</td>
                          <td>{when(item, "withdrawn_at") || when(item, "granted_at")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="empty">No health data has been requested for this household.</p>
                )}
              </div>

              {writable && (
                <div className="member-form">
                  <h4>Enrol or update a member (support)</h4>
                  <div className="form-grid">
                    <label>
                      Member ID
                      <input
                        value={draft.memberId}
                        placeholder="alice or timmy"
                        onChange={(event) => setDraft({ ...draft, memberId: event.target.value })}
                      />
                    </label>
                    <label>
                      Display name
                      <input
                        value={draft.displayName}
                        onChange={(event) =>
                          setDraft({ ...draft, displayName: event.target.value })
                        }
                      />
                    </label>
                    <label>
                      Relationship
                      <select
                        value={draft.relationship}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            relationship: event.target.value,
                            minor: event.target.value === "child",
                          })
                        }
                      >
                        <option value="account_holder">Account holder</option>
                        <option value="spouse">Spouse / partner</option>
                        <option value="child">Child</option>
                        <option value="member">Member</option>
                      </select>
                    </label>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={draft.hasLogin}
                        onChange={(event) => setDraft({ ...draft, hasLogin: event.target.checked })}
                      />
                      Has login (signs in with this member ID)
                    </label>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={draft.isGuardian}
                        onChange={(event) =>
                          setDraft({ ...draft, isGuardian: event.target.checked })
                        }
                      />
                      Guardian (may write other members)
                    </label>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={draft.minor}
                        disabled={draft.hasLogin}
                        onChange={(event) => setDraft({ ...draft, minor: event.target.checked })}
                      />
                      Minor (health data allowed with a guardian's confirmation)
                    </label>
                  </div>
                  <button className="primary" type="button" onClick={saveMember}>
                    Save member
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">
              <strong>Select a household</strong>
              <p>Choose a household on the left to see its members and consent records.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function RetentionPanel({
  api,
  organizationId,
  writable,
}: {
  api: AdminApiClient;
  organizationId: string;
  writable: boolean;
}) {
  const [asOf, setAsOf] = useState("");
  const [result, setResult] = useState<AdminRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(dryRun: boolean) {
    setBusy(true);
    setError("");
    try {
      setResult(
        await api.retentionSweep(organizationId, {
          dryRun,
          ...(dryRun && asOf ? { asOf: new Date(`${asOf}T00:00:00Z`).toISOString() } : {}),
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sweep failed");
    } finally {
      setBusy(false);
    }
  }

  const schemas = (result?.schemas as AdminRecord[] | undefined) ?? [];
  const provisional = (result?.provisionalMembers as AdminRecord[] | undefined) ?? [];
  return (
    <div className="retention-panel">
      <h3>Retention</h3>
      <p>
        Expires values past each schema&apos;s retention, proposed members never confirmed, and
        unanswered health-data questions.
      </p>
      <label>
        Preview as of (optional)
        <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
      </label>
      <div className="retention-actions">
        <button className="secondary" type="button" disabled={busy} onClick={() => run(true)}>
          Preview
        </button>
        {writable && (
          <button className="primary" type="button" disabled={busy} onClick={() => run(false)}>
            Run sweep now
          </button>
        )}
      </div>
      <ErrorBanner error={error} />
      {result && (
        <div className="retention-result">
          <strong>
            {result.dryRun ? "Preview" : "Swept"} as of{" "}
            {new Date(String(result.asOf)).toLocaleDateString()}
          </strong>
          {schemas.length ? (
            schemas.map((item) => (
              <small key={value(item, "schemaId")}>
                {value(item, "schemaId")}: {value(item, "matched")} value(s) past{" "}
                {value(item, "retentionDays")} days
              </small>
            ))
          ) : (
            <small>No schemas in this organization have a retention period.</small>
          )}
          <small>Proposed members to expire: {provisional.length}</small>
          <small>Unanswered health questions to expire: {value(result, "pendingConsents")}</small>
        </div>
      )}
    </div>
  );
}
