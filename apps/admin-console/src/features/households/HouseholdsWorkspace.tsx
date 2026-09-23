import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminApiClient } from "../../api";
import { ErrorBanner } from "../../components/ErrorBanner";
import type { AdminIdentity, AdminRecord } from "../../types";

function value(record: AdminRecord, key: string): string {
  return String(record[key] ?? "");
}

type MemberDraft = {
  memberId: string;
  displayName: string;
  relationship: string;
  hasLogin: boolean;
  isGuardian: boolean;
};

const emptyDraft: MemberDraft = {
  memberId: "",
  displayName: "",
  relationship: "member",
  hasLogin: false,
  isGuardian: false,
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
    void loadHouseholds();
  }, [loadHouseholds]);

  const loadMembers = useCallback(
    async (householdId: string) => {
      try {
        setMembers(await api.listHouseholdMembers(org, householdId));
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

  const activeMembers = useMemo(
    () => members.filter((item) => value(item, "status") === "active"),
    [members],
  );
  const inactiveMembers = useMemo(
    () => members.filter((item) => value(item, "status") !== "active"),
    [members],
  );

  return (
    <section className="households-workspace">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Control plane</span>
          <h2>Households</h2>
          <p>
            A household groups the people who share an account. Every person — the account holder and
            no-login children — is a member; guardians may write another member&apos;s data. Members
            appear to the agent through the resolve snapshot.
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
            <p className="empty">No households yet. Create one to enrol members.</p>
          )}
          {writable && (
            <div className="new-household">
              <input
                value={newHousehold}
                placeholder="new-household-id"
                onChange={(event) =>
                  setNewHousehold(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))
                }
              />
              <button className="secondary" type="button" onClick={createHousehold}>
                + New household
              </button>
            </div>
          )}
        </div>

        <div className="household-detail">
          {selected ? (
            <>
              <h3>
                Members of <span className="household-id">{selected}</span>
              </h3>
              <div className="member-list">
                {activeMembers.length ? (
                  activeMembers.map((item) => {
                    const memberId = value(item, "member_id");
                    return (
                      <div className="member-row" key={memberId}>
                        <span>
                          <strong>{value(item, "display_name") || memberId}</strong>
                          <small>
                            {memberId} · {value(item, "relationship")}
                          </small>
                        </span>
                        <span className="member-flags">
                          {value(item, "is_guardian") === "true" && (
                            <span className="pill">guardian</span>
                          )}
                          {value(item, "has_login") === "true" && (
                            <span className="pill">login</span>
                          )}
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
                  <p className="empty">No active members. Add the account holder first.</p>
                )}
                {inactiveMembers.map((item) => (
                  <div className="member-row inactive" key={value(item, "member_id")}>
                    <span>
                      <strong>{value(item, "display_name") || value(item, "member_id")}</strong>
                      <small>{value(item, "member_id")} · removed</small>
                    </span>
                  </div>
                ))}
              </div>

              {writable && (
                <div className="member-form">
                  <h4>Add or update a member</h4>
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
                          setDraft({ ...draft, relationship: event.target.value })
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
                      Has login
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
                  </div>
                  <button className="primary" type="button" onClick={saveMember}>
                    Save member
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">
              <strong>Select or create a household</strong>
              <p>Choose a household on the left, or create one, to manage its members.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
