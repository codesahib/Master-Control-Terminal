import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ACCOUNT_NAMES } from "../components/Shell";
import { useApp } from "../context";
import { errorMessage, money } from "../lib/format";
import { useApi } from "../lib/useApi";
import { navigate, useRoute } from "../router";
import type { ContributionLimitSetting } from "../types";

export function Room() {
  const { params } = useRoute();
  const { refresh, notify } = useApp();
  const account = params.get("account") || "RRSP";
  const query = useApi<ContributionLimitSetting[]>("/contribution-limits");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string>();

  useEffect(() => setDrafts({}), [query.data]);

  const rows = (query.data || []).filter((row) => row.account === account).sort((a, b) => Number(b.tax_year) - Number(a.tax_year));

  async function save(row: ContributionLimitSetting) {
    const key = `${row.account}:${row.tax_year}`;
    const value = Number(drafts[key] ?? row.new_room);
    if (!Number.isFinite(value) || value < 0) {
      notify("New room must be zero or more.", "error");
      return;
    }
    setSaving(key);
    try {
      await api.put(`/contribution-limits/${row.account}/${row.tax_year}`, { new_room: value });
      notify(`${row.account} ${row.tax_year} room saved.`);
      refresh();
    } catch (error) {
      notify(errorMessage(error, "Contribution limit failed to save."), "error");
    } finally {
      setSaving(undefined);
    }
  }

  return (
    <div className="grid">
      <section className="card s12" aria-labelledby="room-t">
        <div className="card-h">
          <div><h2 className="card-t" id="room-t">Contribution limits</h2><span className="muted">New room is what CRA gives you each year. Unused and total room are calculated.</span></div>
          <div className="seg" role="group" aria-label="Account">
            {ACCOUNT_NAMES.map((name) => <button key={name} type="button" className={account === name ? "on" : ""} aria-pressed={account === name} onClick={() => navigate("/room", { account: name })}>{name}</button>)}
          </div>
        </div>
        {query.error && <p className="form-error" role="alert">{errorMessage(query.error, "Limits failed to load.")}</p>}
        <div className="tbl-wrap">
          <table className="tbl tbl-cards">
            <thead><tr><th>Year</th><th className="r">Unused from before</th><th className="r">New room</th><th className="r">Total room</th><th><span className="sr-only">Save</span></th></tr></thead>
            <tbody>
              {rows.map((row) => {
                const key = `${row.account}:${row.tax_year}`;
                const draft = drafts[key];
                const dirty = draft !== undefined && Number(draft) !== row.new_room;
                return (
                  <tr key={key}>
                    <td data-label="Year"><b>{row.tax_year}</b></td>
                    <td data-label="Unused from before" className="r num money">{money(row.unused_room)}</td>
                    <td data-label="New room" className="r">
                      <label className="sr-only" htmlFor={`room-${key}`}>New room for {row.tax_year}</label>
                      <div className="grp grp-sm">
                        <span className="pre" aria-hidden="true">$</span>
                        <input id={`room-${key}`} type="number" min="0" step="0.01" inputMode="decimal" value={draft ?? String(row.new_room)} onChange={(event) => setDrafts({ ...drafts, [key]: event.target.value })} />
                      </div>
                    </td>
                    <td data-label="Total room" className="r num money">{money(row.total_room)}</td>
                    <td data-label="Save" className="row-actions">
                      <button className={`btn ${dirty ? "btn-p" : "btn-s"} sm`} type="button" disabled={saving === key || !dirty} onClick={() => save(row)}>{saving === key ? "Saving…" : "Save"}</button>
                    </td>
                  </tr>
                );
              })}
              {!query.loading && rows.length === 0 && <tr className="empty-row"><td colSpan={5} className="empty">No limits found for {account}.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
