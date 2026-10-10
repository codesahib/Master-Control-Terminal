import { FormEvent, useId, useState } from "react";
import { api } from "../api/client";
import { errorMessage, money } from "../lib/format";
import { PortfolioPLRow } from "../types";
import { Dialog } from "./Dialog";
import { Field, MoneyInput, Section } from "./form";

interface Props {
  row: PortfolioPLRow;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}

export function ManualValuationModal({ row, onClose, onSaved }: Props) {
  const formId = useId();
  const child = row.children?.[0];
  const accountName = child?.account_name || row.account_name;
  const platformName = row.platform_name || child?.platform_name;
  const [marketValue, setMarketValue] = useState(String(row.market_value ?? row.book_value));
  const [snapshotDate, setSnapshotDate] = useState(row.manual_valuation_date || new Date().toISOString().slice(0, 10));
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSaving(true);
    try {
      await api.post("/manual-valuations", {
        account_name: accountName,
        platform_name: platformName || null,
        instrument_id: row.instrument_id || null,
        symbol: row.symbol,
        instrument_name: row.name || row.symbol,
        broad_category: row.broad_category || null,
        precise_category: row.precise_category || null,
        market_value: Number(marketValue),
        snapshot_date: snapshotDate,
      });
      await onSaved();
      onClose();
    } catch (exc) {
      setError(errorMessage(exc, "Manual value failed to save."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog
      title="Update value"
      subtitle={`${row.name || row.symbol} · ${accountName}${platformName ? ` · ${platformName}` : ""}`}
      size="sm"
      onClose={onClose}
      footer={
        <>
          <span className="grow" />
          <button className="btn btn-s" type="button" onClick={onClose}>Cancel</button>
          <button className="btn btn-p" type="submit" form={formId} disabled={isSaving}>{isSaving ? "Saving…" : "Save value"}</button>
        </>
      }
    >
      <form id={formId} className="form" onSubmit={submit}>
        <p className="sub">For GICs and funds without a live price. Book value is {money(row.book_value, row.currency)}.</p>
        <Section n={1} title="Value">
          <Field label="Market value" htmlFor="manual-value"><MoneyInput id="manual-value" required min="0" value={marketValue} onChange={setMarketValue} currency={row.currency} /></Field>
          <Field label="As of" htmlFor="manual-date"><input id="manual-date" className="inp" type="date" required value={snapshotDate} onChange={(event) => setSnapshotDate(event.target.value)} /></Field>
        </Section>
        {error && <p className="form-error" role="alert">{error}</p>}
      </form>
    </Dialog>
  );
}
