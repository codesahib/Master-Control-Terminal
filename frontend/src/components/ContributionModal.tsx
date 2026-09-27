import { FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { Contribution } from "../types";
import { platformOptions } from "./transactionFormConfig";

interface Props {
  onClose: () => void;
  onSaved: () => Promise<void>;
  defaultAccount?: string;
  contribution?: Contribution;
  platforms?: string[];
}

function contributionForm(contribution: Contribution | undefined, defaultAccount: string, defaultPlatform: string) {
  return {
    transaction_date: contribution?.transaction_date?.slice(0, 10) || new Date().toISOString().slice(0, 10),
    account_name: contribution?.account_name || defaultAccount,
    platform_name: contribution ? contribution.platform_name || "" : defaultPlatform,
    amount: String(contribution?.amount ?? 0),
    notes: contribution?.notes || "",
  };
}

export function ContributionModal({ onClose, onSaved, defaultAccount = "RRSP", contribution, platforms = platformOptions }: Props) {
  const defaultPlatform = platforms[0] || "";
  const [form, setForm] = useState(() => contributionForm(contribution, defaultAccount, defaultPlatform));
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const platformChoices = contribution?.platform_name && !platforms.includes(contribution.platform_name)
    ? [contribution.platform_name, ...platforms]
    : platforms;

  useEffect(() => {
    setForm(contributionForm(contribution, defaultAccount, defaultPlatform));
  }, [contribution, defaultAccount]);

  useEffect(() => {
    if (!contribution && defaultPlatform) {
      setForm((current) => current.platform_name ? current : { ...current, platform_name: defaultPlatform });
    }
  }, [contribution, defaultPlatform]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSaving(true);
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
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="contribution-modal-title">
      <div className="modal-content panel">
        <div className="header">
          <h3 id="contribution-modal-title">{contribution ? "Edit Contribution" : "New Contribution"}</h3>
          <button className="btn-secondary btn" type="button" onClick={onClose}>Close</button>
        </div>

        <form onSubmit={submit}>
          <div className="form-grid">
            <div className="field"><label htmlFor="contribution-date">Date</label><input id="contribution-date" type="date" required value={form.transaction_date} onChange={(e) => setForm({ ...form, transaction_date: e.target.value })} /></div>
            <div className="field"><label htmlFor="contribution-amount">Amount</label><input id="contribution-amount" type="number" min="0.01" step="0.01" inputMode="decimal" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
            <div className="field"><label htmlFor="contribution-account">Account</label><select id="contribution-account" required value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value })}><option>RRSP</option><option>TFSA</option><option>FHSA</option></select></div>
            <div className="field">
              <label htmlFor="contribution-platform">Platform</label>
              <select id="contribution-platform" value={form.platform_name} onChange={(e) => setForm({ ...form, platform_name: e.target.value })}>
                <option value="">No platform</option>
                {platformChoices.map((platform) => (
                  <option key={platform} value={platform}>{platform}</option>
                ))}
              </select>
            </div>
            <div className="field field-span"><label htmlFor="contribution-notes">Notes</label><textarea id="contribution-notes" value={form.notes} rows={3} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
          </div>
          {error && <small className="field-error">{error}</small>}
          <div className="form-actions">
            <button className="btn" type="submit" disabled={isSaving}>{isSaving ? "Saving" : "Save Contribution"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
