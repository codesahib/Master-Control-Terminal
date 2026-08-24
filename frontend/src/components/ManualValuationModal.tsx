import { FormEvent, useState } from "react";
import { api } from "../api/client";
import { PortfolioPLRow } from "../types";

interface Props {
  row: PortfolioPLRow;
  onClose: () => void;
  onSaved: () => Promise<void>;
}

export function ManualValuationModal({ row, onClose, onSaved }: Props) {
  const child = row.children?.[0];
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
        account_name: child?.account_name || row.account_name,
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
    } catch (e: any) {
      setError(e?.response?.data?.detail?.toString() || "Manual valuation failed to save.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="manual-valuation-title">
      <div className="modal-content panel">
        <div className="header">
          <h3 id="manual-valuation-title">Update Manual Value</h3>
          <button className="btn-secondary btn" type="button" onClick={onClose}>Close</button>
        </div>
        <form onSubmit={submit}>
          <div className="form-grid">
            <div className="field"><label>Symbol</label><input value={row.symbol} disabled /></div>
            <div className="field"><label>Account</label><input value={child?.account_name || row.account_name} disabled /></div>
            <div className="field"><label>Platform</label><input value={platformName || ""} disabled /></div>
            <div className="field"><label htmlFor="manual-market-value">Market Value</label><input id="manual-market-value" type="number" min="0" step="0.01" inputMode="decimal" required value={marketValue} onChange={(e) => setMarketValue(e.target.value)} /></div>
            <div className="field"><label htmlFor="manual-snapshot-date">Updated Date</label><input id="manual-snapshot-date" type="date" required value={snapshotDate} onChange={(e) => setSnapshotDate(e.target.value)} /></div>
          </div>
          {error && <small className="field-error">{error}</small>}
          <div className="form-actions">
            <button className="btn" type="submit" disabled={isSaving}>{isSaving ? "Saving" : "Save Manual Value"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
