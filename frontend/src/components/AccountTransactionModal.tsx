import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { AccountTransaction, AccountTransactionType, ContributionFunding } from "../types";
import {
  accountTransactionOptions,
  categoryOptions,
  platformOptions,
  preciseOptionsFor,
} from "./transactionFormConfig";

interface Props {
  onClose: () => void;
  onSaved: () => Promise<void>;
  defaultAccount?: string;
  transaction?: AccountTransaction;
  defaultTransactionType?: AccountTransactionType;
}

export function AccountTransactionModal({
  onClose,
  onSaved,
  defaultAccount = "RRSP",
  transaction,
  defaultTransactionType = "investment_buy",
}: Props) {
  const [transactionType, setTransactionType] = useState<AccountTransactionType>(
    transaction?.transaction_type || defaultTransactionType
  );
  const [form, setForm] = useState({
    transaction_date: transaction?.transaction_date || new Date().toISOString().slice(0, 10),
    account_name: transaction?.account_name || defaultAccount,
    platform_name: transaction?.platform_name || "Wealthsimple",
    broad_category: transaction?.broad_category || "",
    precise_category: transaction?.precise_category || "",
    symbol: transaction?.symbol || "",
    instrument_name: "",
    amount: String(transaction?.amount ?? 0),
    quantity: transaction?.quantity ? String(transaction.quantity) : "",
    fees: String(transaction?.fees ?? 0),
    notes: transaction?.notes || "",
    contribution_id: transaction?.contribution_id ? String(transaction.contribution_id) : "",
  });
  const [error, setError] = useState("");
  const [contributions, setContributions] = useState<ContributionFunding[]>([]);

  const requiresSymbol = useMemo(
    () => ["investment_buy", "investment_sell", "dividend_interest"].includes(transactionType),
    [transactionType]
  );
  const requiresContribution = transactionType === "investment_buy";

  useEffect(() => {
    if (!requiresContribution) {
      setContributions([]);
      return;
    }
    api
      .get<ContributionFunding[]>("/available-contributions", {
        params: { account: form.account_name, include_contribution_id: transaction?.contribution_id },
      })
      .then((response) => setContributions(response.data));
  }, [form.account_name, requiresContribution, transaction?.contribution_id]);

  async function submit() {
    setError("");
    if (!form.transaction_date || !form.account_name || !form.platform_name || form.amount === "") {
      setError("Amount, date, account, and platform are required");
      return;
    }
    if (requiresContribution && !form.contribution_id) {
      setError("Select a contribution before recording an investment buy");
      return;
    }

    try {
      const payload = {
        transaction_type: transactionType,
        transaction_date: form.transaction_date,
        account_name: form.account_name || null,
        platform_name: form.platform_name || null,
        broad_category: form.broad_category || null,
        precise_category: form.precise_category || null,
        symbol: requiresSymbol ? form.symbol || null : null,
        instrument_name: form.instrument_name || null,
        amount: Number(form.amount),
        quantity: requiresSymbol && form.quantity ? Number(form.quantity) : null,
        fees: Number(form.fees || 0),
        notes: form.notes || null,
        contribution_id: requiresContribution ? Number(form.contribution_id) : null,
      };

      if (transaction) {
        await api.put(`/account-transactions/${transaction.id}`, payload);
      } else {
        await api.post("/account-transactions", payload);
      }

      await onSaved();
      onClose();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((item) => item.msg).join(", ") : detail?.toString() || "Failed to save account transaction");
    }
  }

  return (
    <div className="modal">
      <div className="modal-content panel">
        <div className="header">
          <h3>{transaction ? "Edit Account Transaction" : "New Account Transaction"}</h3>
          <button className="btn-secondary btn" onClick={onClose}>Close</button>
        </div>

        <div className="field" style={{ marginBottom: 12 }}>
          <label>What transaction are you recording?</label>
          <select value={transactionType} onChange={(e) => setTransactionType(e.target.value as AccountTransactionType)}>
            {accountTransactionOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div className="form-grid">
          <div className="field"><label>Date</label><input type="date" value={form.transaction_date} onChange={(e) => setForm({ ...form, transaction_date: e.target.value })} /></div>
          <div className="field"><label>Amount</label><input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
          <div className="field"><label>Account</label><select value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value, contribution_id: "" })}><option>RRSP</option><option>TFSA</option><option>FHSA</option></select></div>
          <div className="field">
            <label>Platform</label>
            <select value={form.platform_name} onChange={(e) => setForm({ ...form, platform_name: e.target.value })}>
              {platformOptions.map((platform) => (
                <option key={platform} value={platform}>{platform}</option>
              ))}
            </select>
          </div>
          {requiresContribution && <div className="field"><label>Funding Contribution</label><select value={form.contribution_id} onChange={(e) => setForm({ ...form, contribution_id: e.target.value })}><option value="">Select a contribution</option>{contributions.map((contribution) => <option key={contribution.id} value={contribution.id}>{contribution.transaction_date} · {contribution.platform_name || "No platform"} · ${contribution.remaining_amount.toFixed(2)} remaining</option>)}</select></div>}
          <div className="field">
            <label>Broad Category</label>
            <select
              value={form.broad_category}
              onChange={(e) => {
                const broadCategory = e.target.value;
                setForm({
                  ...form,
                  broad_category: broadCategory,
                  precise_category: preciseOptionsFor(broadCategory)[0] || "",
                });
              }}
            >
              <option value="">None</option>
              {Object.keys(categoryOptions).map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Precise Category</label>
            <select value={form.precise_category} onChange={(e) => setForm({ ...form, precise_category: e.target.value })}>
              <option value="">None</option>
              {preciseOptionsFor(form.broad_category).map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
          </div>
          {requiresSymbol && <div className="field"><label>Symbol</label><input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} /></div>}
          {requiresSymbol && <div className="field"><label>Quantity</label><input type="number" step="0.0001" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></div>}
          <div className="field"><label>Fees</label><input type="number" step="0.01" value={form.fees} onChange={(e) => setForm({ ...form, fees: e.target.value })} /></div>
          <div className="field"><label>Instrument Name</label><input value={form.instrument_name} onChange={(e) => setForm({ ...form, instrument_name: e.target.value })} /></div>
          <div className="field" style={{ gridColumn: "1 / -1" }}><label>Notes</label><textarea value={form.notes} rows={3} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
        </div>
        {error && <small style={{ color: "#ff6b6b" }}>{error}</small>}
        <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
          <button className="btn" onClick={submit}>Save Account Transaction</button>
        </div>
      </div>
    </div>
  );
}
