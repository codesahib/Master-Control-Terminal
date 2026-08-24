import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { AccountTransaction, AccountTransactionType, ContributionFunding, FundingCashSource } from "../types";
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
  platforms?: string[];
}

export function AccountTransactionModal({
  onClose,
  onSaved,
  defaultAccount = "RRSP",
  transaction,
  defaultTransactionType = "investment_buy",
  platforms = platformOptions,
}: Props) {
  const defaultPlatform = platforms[0] || "";
  const [transactionType, setTransactionType] = useState<AccountTransactionType>(
    transaction?.transaction_type || defaultTransactionType
  );
  const [form, setForm] = useState({
    transaction_date: transaction?.transaction_date || new Date().toISOString().slice(0, 10),
    account_name: transaction?.account_name || defaultAccount,
    platform_name: transaction ? transaction.platform_name || "" : defaultPlatform,
    source_platform_name: transaction?.source_platform_name || "",
    broad_category: transaction?.broad_category || "",
    precise_category: transaction?.precise_category || "",
    symbol: transaction?.symbol || "",
    instrument_name: "",
    amount: String(transaction?.amount ?? 0),
    currency: transaction?.currency || "CAD",
    source_amount: transaction?.source_amount ? String(transaction.source_amount) : "",
    source_currency: transaction?.source_currency || "CAD",
    quantity: transaction?.quantity ? String(transaction.quantity) : "",
    fees: String(transaction?.fees ?? 0),
    fee_currency: transaction?.fee_currency || transaction?.currency || "CAD",
    notes: transaction?.notes || "",
  });
  const platformChoices = transaction?.platform_name && !platforms.includes(transaction.platform_name)
    ? [transaction.platform_name, ...platforms]
    : platforms;
  const [error, setError] = useState("");
  const [contributions, setContributions] = useState<ContributionFunding[]>([]);
  const [fundingCashSources, setFundingCashSources] = useState<FundingCashSource[]>(() => {
    const sources = new Map<string, FundingCashSource>();
    transaction?.funding_contributions?.forEach((funding) => {
      if (!funding.platform_name) return;
      const key = funding.platform_name.toLowerCase();
      const current = sources.get(key) || { platform_name: funding.platform_name, amount: 0 };
      current.amount += funding.amount;
      sources.set(key, current);
    });
    return [...sources.values()];
  });

  const requiresSymbol = useMemo(
    () => ["investment_buy", "investment_sell", "dividend_reinvestment", "quantity_adjustment"].includes(transactionType),
    [transactionType]
  );
  const requiresFunding = ["investment_buy", "transfer"].includes(transactionType);
  const isCurrencyExchange = transactionType === "currency_exchange";

  useEffect(() => {
    if (!transaction && defaultPlatform) {
      setForm((current) => current.platform_name ? current : { ...current, platform_name: defaultPlatform });
    }
  }, [defaultPlatform, transaction]);

  useEffect(() => {
    if (!requiresFunding) {
      setContributions([]);
      return;
    }
    api
      .get<ContributionFunding[]>("/available-contributions", { params: { account: form.account_name, exclude_transaction_id: transaction?.id } })
      .then((response) => setContributions(response.data));
  }, [form.account_name, requiresFunding]);

  function toggleFundingCashSource(contribution: ContributionFunding) {
    setFundingCashSources((current) =>
      current.some((funding) => funding.platform_name === contribution.platform_name)
        ? current.filter((funding) => funding.platform_name !== contribution.platform_name)
        : [...current, { platform_name: contribution.platform_name, amount: 0 }]
    );
  }

  function updateFundingAmount(platformName: string, amount: string) {
    setFundingCashSources((current) =>
      current.map((funding) =>
        funding.platform_name === platformName ? { ...funding, amount: Number(amount) || 0 } : funding
      )
    );
  }

  function useRemainingAmount(contribution: ContributionFunding) {
    const total = Number(form.amount || 0) + Number(form.fees || 0);
    const allocatedElsewhere = fundingCashSources
      .filter((funding) => funding.platform_name !== contribution.platform_name)
      .reduce((sum, funding) => sum + funding.amount, 0);
    const amount = Math.max(0, Math.min(contribution.remaining_amount, total - allocatedElsewhere));
    updateFundingAmount(contribution.platform_name, String(Math.round(amount * 100) / 100));
  }

  async function submit() {
    setError("");
    if (!form.transaction_date || !form.account_name || !form.platform_name || form.amount === "") {
      setError("Amount, date, account, and platform are required");
      return;
    }
    if (requiresFunding && fundingCashSources.some((funding) => funding.amount <= 0)) {
      setError("Funding source amounts must be greater than zero");
      return;
    }
    if (transactionType === "transfer" && !form.source_platform_name) {
      setError("Source platform is required for transfers");
      return;
    }

    try {
      const payload = {
        transaction_type: transactionType,
        transaction_date: form.transaction_date,
        account_name: form.account_name || null,
        platform_name: form.platform_name || null,
        source_platform_name: transactionType === "transfer" ? form.source_platform_name : null,
        broad_category: form.broad_category || null,
        precise_category: form.precise_category || null,
        symbol: requiresSymbol ? form.symbol || null : null,
        instrument_name: form.instrument_name || null,
        amount: Number(form.amount),
        currency: form.currency,
        source_amount: isCurrencyExchange && form.source_amount ? Number(form.source_amount) : null,
        source_currency: isCurrencyExchange ? form.source_currency : null,
        quantity: requiresSymbol && form.quantity ? Number(form.quantity) : null,
        fees: Number(form.fees || 0),
        fee_currency: form.fee_currency || form.currency,
        notes: form.notes || null,
        funding_cash_sources: requiresFunding ? fundingCashSources : [],
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
      console.error("Failed to save account transaction", { detail, error: e });
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
          <div className="field"><label>{isCurrencyExchange ? "To Amount" : "Amount"}</label><input type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
          <div className="field"><label>{isCurrencyExchange ? "To Currency" : "Currency"}</label><select value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}><option>CAD</option><option>USD</option></select></div>
          <div className="field"><label>Account</label><select value={form.account_name} onChange={(e) => { setForm({ ...form, account_name: e.target.value }); setFundingCashSources([]); }}><option>RRSP</option><option>TFSA</option><option>FHSA</option></select></div>
          <div className="field">
            <label>{transactionType === "transfer" ? "To Platform" : "Platform"}</label>
            <select value={form.platform_name} onChange={(e) => setForm({ ...form, platform_name: e.target.value })}>
              <option value="">No platform</option>
              {platformChoices.map((platform) => (
                <option key={platform} value={platform}>{platform}</option>
              ))}
            </select>
          </div>
          {transactionType === "transfer" && <div className="field"><label>From Platform</label><select value={form.source_platform_name} onChange={(e) => { setForm({ ...form, source_platform_name: e.target.value }); setFundingCashSources([]); }}><option value="">Select source platform</option>{platformChoices.map((platform) => <option key={platform} value={platform}>{platform}</option>)}</select></div>}
          {isCurrencyExchange && <>
            <div className="field"><label>From Amount</label><input type="number" step="0.01" value={form.source_amount} onChange={(e) => setForm({ ...form, source_amount: e.target.value })} /></div>
            <div className="field"><label>From Currency</label><select value={form.source_currency} onChange={(e) => setForm({ ...form, source_currency: e.target.value })}><option>CAD</option><option>USD</option></select></div>
          </>}
          {requiresFunding && (
            <div className="field" style={{ gridColumn: "1 / -1" }}>
              <label>Funding Sources (optional)</label>
              {contributions.filter((contribution) => transactionType !== "transfer" || contribution.platform_name.toLowerCase() === form.source_platform_name.toLowerCase()).map((contribution) => {
                const funding = fundingCashSources.find((item) => item.platform_name === contribution.platform_name);
                return (
                  <div key={contribution.id} style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <label>
                      <input type="checkbox" checked={Boolean(funding)} onChange={() => toggleFundingCashSource(contribution)} />
                      {" "}{contribution.platform_name} · {contribution.source_label} · ${contribution.remaining_amount.toFixed(2)} remaining
                    </label>
                    {funding && <>
                      <input aria-label={`Funding amount for ${contribution.platform_name}`} type="number" min="0.01" step="0.01" value={funding.amount || ""} onChange={(e) => updateFundingAmount(contribution.platform_name, e.target.value)} />
                      <button type="button" className="btn-secondary btn" onClick={() => useRemainingAmount(contribution)}>Use remaining amount</button>
                    </>}
                  </div>
                );
              })}
            </div>
          )}
          {!isCurrencyExchange && <div className="field">
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
          </div>}
          {!isCurrencyExchange && <div className="field">
            <label>Precise Category</label>
            <select value={form.precise_category} onChange={(e) => setForm({ ...form, precise_category: e.target.value })}>
              <option value="">None</option>
              {preciseOptionsFor(form.broad_category).map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
          </div>}
          {requiresSymbol && <div className="field"><label>Symbol</label><input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} /></div>}
          {requiresSymbol && <div className="field"><label>Quantity</label><input type="number" step="0.0001" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></div>}
          <div className="field"><label>Fees</label><input type="number" step="0.01" value={form.fees} onChange={(e) => setForm({ ...form, fees: e.target.value })} /></div>
          <div className="field"><label>Fee Currency</label><select value={form.fee_currency} onChange={(e) => setForm({ ...form, fee_currency: e.target.value })}><option>CAD</option><option>USD</option></select></div>
          {!isCurrencyExchange && <div className="field"><label>Instrument Name</label><input value={form.instrument_name} onChange={(e) => setForm({ ...form, instrument_name: e.target.value })} /></div>}
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
