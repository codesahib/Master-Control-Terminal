import { useState } from "react";
import { api } from "../api/client";
import { Contribution } from "../types";
import { platformOptions } from "./transactionFormConfig";

interface Props {
  onClose: () => void;
  onSaved: () => Promise<void>;
  defaultAccount?: string;
  contribution?: Contribution;
}

export function ContributionModal({ onClose, onSaved, defaultAccount = "RRSP", contribution }: Props) {
  const [form, setForm] = useState({
    transaction_date: contribution?.transaction_date || new Date().toISOString().slice(0, 10),
    account_name: contribution?.account_name || defaultAccount,
    platform_name: contribution?.platform_name || "Wealthsimple",
    amount: String(contribution?.amount ?? 0),
    notes: contribution?.notes || "",
  });
  const [error, setError] = useState("");

  async function submit() {
    setError("");
    try {
      const payload = {
        transaction_date: form.transaction_date,
        account_name: form.account_name || null,
        platform_name: form.platform_name || null,
        amount: Number(form.amount),
        notes: form.notes || null,
      };

      if (contribution) {
        await api.put(`/contributions/${contribution.id}`, payload);
      } else {
        await api.post("/contributions", payload);
      }

      await onSaved();
      onClose();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((item) => item.msg).join(", ") : detail?.toString() || "Failed to save contribution");
    }
  }

  return (
    <div className="modal">
      <div className="modal-content panel">
        <div className="header">
          <h3>{contribution ? "Edit Contribution" : "New Contribution"}</h3>
          <button className="btn-secondary btn" onClick={onClose}>Close</button>
        </div>

        <div className="form-grid">
          <div className="field"><label>Date</label><input type="date" value={form.transaction_date} onChange={(e) => setForm({ ...form, transaction_date: e.target.value })} /></div>
          <div className="field"><label>Amount</label><input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
          <div className="field"><label>Account</label><select value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value })}><option>RRSP</option><option>TFSA</option><option>FHSA</option></select></div>
          <div className="field">
            <label>Platform</label>
            <select value={form.platform_name} onChange={(e) => setForm({ ...form, platform_name: e.target.value })}>
              {platformOptions.map((platform) => (
                <option key={platform} value={platform}>{platform}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}><label>Notes</label><textarea value={form.notes} rows={3} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
        </div>
        {error && <small style={{ color: "#ff6b6b" }}>{error}</small>}
        <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
          <button className="btn" onClick={submit}>Save Contribution</button>
        </div>
      </div>
    </div>
  );
}
