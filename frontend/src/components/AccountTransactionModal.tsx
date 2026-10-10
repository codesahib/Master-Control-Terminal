import { FormEvent, useEffect, useId, useState } from "react";
import { api } from "../api/client";
import { errorMessage, money, TYPE_LABELS } from "../lib/format";
import { AccountTransaction, AccountTransactionType, ContributionFunding, FundingCashSource, SymbolSearchResult } from "../types";
import { Dialog } from "./Dialog";
import { Field, MoneyInput, PlatformSelect, Section, Segmented } from "./form";
import { Icon } from "./Icon";
import { SymbolPicker } from "./SymbolPicker";
import { ACCOUNT_NAMES } from "./Shell";
import { accountTransactionOptions, categoryOptions, platformOptions, preciseOptionsFor } from "./transactionFormConfig";

interface Props {
  onClose: () => void;
  onSaved: () => Promise<void> | void;
  onDelete?: () => void;
  defaultAccount?: string;
  transaction?: AccountTransaction;
  defaultTransactionType?: AccountTransactionType;
  platforms?: string[];
}

const AMOUNT_LABELS: Partial<Record<AccountTransactionType, string>> = {
  investment_buy: "Total cost",
  investment_sell: "Proceeds",
  dividend_interest: "Amount received",
  dividend_reinvestment: "Dividend used",
  transfer: "Amount moved",
  withdrawal: "Amount withdrawn",
};

export function AccountTransactionModal({
  onClose,
  onSaved,
  onDelete,
  defaultAccount = "RRSP",
  transaction,
  defaultTransactionType = "investment_buy",
  platforms = platformOptions,
}: Props) {
  const formId = useId();
  const defaultPlatform = platforms[0] || "";
  const [transactionType, setTransactionType] = useState<AccountTransactionType>(transaction?.transaction_type || defaultTransactionType);
  const [form, setForm] = useState({
    transaction_date: transaction?.transaction_date || new Date().toISOString().slice(0, 10),
    account_name: transaction?.account_name || defaultAccount,
    platform_name: transaction ? transaction.platform_name || "" : defaultPlatform,
    source_platform_name: transaction?.source_platform_name || "",
    broad_category: transaction?.broad_category || "",
    precise_category: transaction?.precise_category || "",
    instrument_id: transaction?.instrument_id || undefined,
    symbol: transaction?.symbol || "",
    instrument_name: "",
    is_custom_symbol: false,
    amount: String(transaction?.amount ?? ""),
    currency: transaction?.currency || "CAD",
    source_amount: transaction?.source_amount ? String(transaction.source_amount) : "",
    source_currency: transaction?.source_currency || "CAD",
    quantity: transaction?.quantity ? String(transaction.quantity) : "",
    fees: String(transaction?.fees ?? 0),
    fee_currency: transaction?.fee_currency || transaction?.currency || "CAD",
    notes: transaction?.notes || "",
  });
  const platformChoices = transaction?.platform_name && !platforms.includes(transaction.platform_name) ? [transaction.platform_name, ...platforms] : platforms;
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState(transaction?.symbol || "");
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

  const requiresSymbol = ["investment_buy", "investment_sell", "dividend_reinvestment", "quantity_adjustment"].includes(transactionType);
  const requiresFunding = ["investment_buy", "transfer"].includes(transactionType);
  const isCurrencyExchange = transactionType === "currency_exchange";
  const isWithdrawal = transactionType === "withdrawal";
  const isAdjustment = transactionType === "quantity_adjustment";
  const isTransfer = transactionType === "transfer";
  const supportsSourceCash = ["investment_buy", "dividend_reinvestment"].includes(transactionType);
  const showCategories = !isCurrencyExchange && !isWithdrawal && !isTransfer;
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));

  useEffect(() => {
    if (!transaction && defaultPlatform) {
      setForm((current) => (current.platform_name ? current : { ...current, platform_name: defaultPlatform }));
    }
  }, [defaultPlatform, transaction]);

  useEffect(() => {
    if (!requiresFunding) {
      setContributions([]);
      return;
    }
    api
      .get<ContributionFunding[]>("/available-contributions", { params: { account: form.account_name, exclude_transaction_id: transaction?.id } })
      .then((response) => setContributions(response.data))
      .catch(() => setContributions([]));
  }, [form.account_name, requiresFunding, transaction?.id]);

  function selectSymbol(symbol: SymbolSearchResult) {
    set({ instrument_id: symbol.id, symbol: symbol.symbol, currency: symbol.currency || form.currency, instrument_name: symbol.name || form.instrument_name });
    setSymbolQuery(symbol.provider_symbol);
  }

  function toggleFundingCashSource(contribution: ContributionFunding) {
    setFundingCashSources((current) =>
      current.some((funding) => funding.platform_name === contribution.platform_name)
        ? current.filter((funding) => funding.platform_name !== contribution.platform_name)
        : [...current, { platform_name: contribution.platform_name, amount: 0 }]
    );
  }

  function updateFundingAmount(platformName: string, amount: string) {
    setFundingCashSources((current) => current.map((funding) => (funding.platform_name === platformName ? { ...funding, amount: Number(amount) || 0 } : funding)));
  }

  const cashNeeded = Number((supportsSourceCash && form.source_amount) || form.amount || 0) + Number(form.fees || 0);
  const fundingTotal = fundingCashSources.reduce((sum, funding) => sum + funding.amount, 0);

  function useRemainingAmount(contribution: ContributionFunding) {
    const allocatedElsewhere = fundingCashSources.filter((funding) => funding.platform_name !== contribution.platform_name).reduce((sum, funding) => sum + funding.amount, 0);
    const amount = Math.max(0, Math.min(contribution.remaining_amount, cashNeeded - allocatedElsewhere));
    updateFundingAmount(contribution.platform_name, String(Math.round(amount * 100) / 100));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!form.transaction_date || !form.account_name || !form.platform_name || (!isAdjustment && form.amount === "")) {
      setError("Amount, date, account, and platform are required.");
      return;
    }
    if (requiresFunding && fundingCashSources.some((funding) => funding.amount <= 0)) {
      setError("Funding source amounts must be greater than zero.");
      return;
    }
    if (isTransfer && !form.source_platform_name) {
      setError("Source platform is required for transfers.");
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        transaction_type: transactionType,
        transaction_date: form.transaction_date,
        account_name: form.account_name || null,
        platform_name: form.platform_name || null,
        source_platform_name: isTransfer ? form.source_platform_name : null,
        broad_category: showCategories ? form.broad_category || null : null,
        precise_category: showCategories ? form.precise_category || null : null,
        instrument_id: requiresSymbol ? form.instrument_id || null : null,
        symbol: requiresSymbol ? form.symbol || null : null,
        instrument_name: requiresSymbol || showCategories ? form.instrument_name || null : null,
        amount: isAdjustment ? 0 : Number(form.amount),
        currency: form.currency,
        source_amount: (isCurrencyExchange || supportsSourceCash) && form.source_amount ? Number(form.source_amount) : null,
        source_currency: (isCurrencyExchange || supportsSourceCash) && form.source_amount ? form.source_currency : null,
        quantity: requiresSymbol && form.quantity ? Number(form.quantity) : null,
        fees: isAdjustment || isWithdrawal ? 0 : Number(form.fees || 0),
        fee_currency: form.fee_currency || form.currency,
        notes: form.notes || null,
        is_custom_symbol: requiresSymbol ? form.is_custom_symbol : false,
        funding_cash_sources: requiresFunding ? fundingCashSources : [],
      };
      if (transaction) await api.put(`/account-transactions/${transaction.id}`, payload);
      else await api.post("/account-transactions", payload);
      await onSaved();
      onClose();
    } catch (exc) {
      setError(errorMessage(exc, "Failed to save the transaction."));
    } finally {
      setIsSaving(false);
    }
  }

  let step = 1;
  const amount = Number(form.amount || 0);
  const qty = Number(form.quantity || 0);
  const fees = Number(form.fees || 0);
  const summary = (
    <>
      <span className="sum-k">Summary</span>
      <div>
        <div className="sum-head">
          {TYPE_LABELS[transactionType]}
          {requiresSymbol && (qty ? ` ${qty}` : "")}
          {requiresSymbol && form.symbol ? ` ${form.symbol}` : ""}
        </div>
        <div className="sub">{form.account_name} · {isTransfer ? `${form.source_platform_name || "?"} to ${form.platform_name || "?"}` : form.platform_name || "No platform"}</div>
      </div>
      <dl className="sum-rows">
        {isCurrencyExchange ? (
          <>
            <div><dt>You give</dt><dd className="num">{money(Number(form.source_amount || 0), form.source_currency)}</dd></div>
            <div><dt>You get</dt><dd className="num">{money(amount, form.currency)}</dd></div>
            {Number(form.source_amount) > 0 && <div><dt>Rate</dt><dd className="num">{(amount / Number(form.source_amount)).toFixed(4)}</dd></div>}
          </>
        ) : (
          <>
            {!isAdjustment && <div><dt>Amount</dt><dd className="num">{money(amount, form.currency)}</dd></div>}
            {!isAdjustment && !isWithdrawal && <div><dt>Fees</dt><dd className="num">{money(fees, form.fee_currency)}</dd></div>}
            {requiresSymbol && qty > 0 && amount > 0 && <div><dt>Per unit</dt><dd className="num">{money(amount / qty, form.currency, 4)}</dd></div>}
          </>
        )}
      </dl>
      {requiresFunding && fundingCashSources.length > 0 && (
        <div className={`sum-check ${Math.abs(fundingTotal - cashNeeded) < 0.005 ? "ok" : "warn"}`}>
          <Icon name={Math.abs(fundingTotal - cashNeeded) < 0.005 ? "check" : "warn"} size={16} />
          Funding {money(fundingTotal)} of {money(cashNeeded)} needed
        </div>
      )}
      {requiresSymbol && !form.symbol && <div className="sum-check warn"><Icon name="warn" size={16} />Pick a symbol</div>}
    </>
  );

  return (
    <Dialog
      title={transaction ? "Edit transaction" : "New transaction"}
      subtitle="Pick a type. The form only shows the fields that type needs."
      size="lg"
      onClose={onClose}
      aside={summary}
      footer={
        <>
          {transaction && onDelete && (
            <button className="btn btn-danger-g" type="button" onClick={onDelete}><Icon name="trash" size={16} />Delete</button>
          )}
          <span className="grow" />
          <button className="btn btn-s" type="button" onClick={onClose}>Cancel</button>
          <button className="btn btn-p" type="submit" form={formId} disabled={isSaving}>{isSaving ? "Saving…" : "Save transaction"}</button>
        </>
      }
    >
      <form id={formId} className="form" onSubmit={submit}>
        <div className="types" role="radiogroup" aria-label="Transaction type">
          {accountTransactionOptions.map((option) => (
            <button key={option.value} type="button" role="radio" aria-checked={transactionType === option.value} className={`type${transactionType === option.value ? " on" : ""}`} onClick={() => setTransactionType(option.value)}>
              <Icon name={option.value} />
              {option.label}
            </button>
          ))}
        </div>

        <Section n={step++} title="Where">
          <Segmented label="Account" value={form.account_name} options={ACCOUNT_NAMES} onChange={(account_name) => { set({ account_name }); setFundingCashSources([]); }} />
          <Field label="Date" htmlFor="tx-date"><input id="tx-date" className="inp" type="date" required value={form.transaction_date} onChange={(event) => set({ transaction_date: event.target.value })} /></Field>
          {isTransfer ? (
            <>
              <Field label="From platform" htmlFor="tx-from"><PlatformSelect id="tx-from" required value={form.source_platform_name} platforms={platformChoices} onChange={(source_platform_name) => { set({ source_platform_name }); setFundingCashSources([]); }} /></Field>
              <Field label="To platform" htmlFor="tx-platform"><PlatformSelect id="tx-platform" required value={form.platform_name} platforms={platformChoices} onChange={(platform_name) => set({ platform_name })} /></Field>
            </>
          ) : (
            <Field label="Platform" htmlFor="tx-platform" span={6}><PlatformSelect id="tx-platform" required value={form.platform_name} platforms={platformChoices} onChange={(platform_name) => set({ platform_name })} /></Field>
          )}
        </Section>

        {(requiresSymbol || showCategories) && (
          <Section n={step++} title="What">
            {requiresSymbol && (
              <Field label="Symbol" htmlFor="tx-symbol" span={6}>
                <SymbolPicker
                  query={symbolQuery}
                  onQueryChange={(value) => { setSymbolQuery(value); set({ instrument_id: undefined, symbol: value }); }}
                  isCustom={form.is_custom_symbol}
                  onCustomChange={(is_custom_symbol) => set({ is_custom_symbol })}
                  selected={Boolean(form.instrument_id)}
                  selectedName={form.instrument_name}
                  onSelect={selectSymbol}
                />
              </Field>
            )}
            {showCategories && (
              <>
                <Field label="Broad category" htmlFor="tx-broad">
                  <select id="tx-broad" className="inp" value={form.broad_category} onChange={(event) => set({ broad_category: event.target.value, precise_category: preciseOptionsFor(event.target.value)[0] || "" })}>
                    <option value="">None</option>
                    {Object.keys(categoryOptions).map((category) => <option key={category} value={category}>{category}</option>)}
                  </select>
                </Field>
                <Field label="Precise category" htmlFor="tx-precise">
                  <select id="tx-precise" className="inp" value={form.precise_category} onChange={(event) => set({ precise_category: event.target.value })}>
                    <option value="">None</option>
                    {preciseOptionsFor(form.broad_category).map((category) => <option key={category} value={category}>{category}</option>)}
                  </select>
                </Field>
                {!requiresSymbol && (
                  <Field label="Instrument name" htmlFor="tx-name" span={6}><input id="tx-name" className="inp" placeholder="For example: EQ Bank 1-year GIC" value={form.instrument_name} onChange={(event) => set({ instrument_name: event.target.value })} /></Field>
                )}
              </>
            )}
          </Section>
        )}

        <Section n={step++} title="How much">
          {isCurrencyExchange ? (
            <>
              <Field label="You give" htmlFor="tx-from-amount"><MoneyInput id="tx-from-amount" required min="0.01" value={form.source_amount} onChange={(source_amount) => set({ source_amount })} currency={form.source_currency} onCurrencyChange={(source_currency) => set({ source_currency })} /></Field>
              <Field label="You get" htmlFor="tx-amount"><MoneyInput id="tx-amount" required min="0.000001" step="0.000001" value={form.amount} onChange={(value) => set({ amount: value })} currency={form.currency} onCurrencyChange={(currency) => set({ currency })} /></Field>
            </>
          ) : (
            <>
              {requiresSymbol && (
                <Field label={isAdjustment ? "Units to add (negative removes)" : "Quantity"} htmlFor="tx-qty" span={isAdjustment ? 6 : 2}>
                  <input id="tx-qty" className="inp num" type="number" inputMode="decimal" step="0.000001" min={isAdjustment ? undefined : "0"} value={form.quantity} onChange={(event) => set({ quantity: event.target.value })} />
                </Field>
              )}
              {!isAdjustment && (
                <Field label={AMOUNT_LABELS[transactionType] || "Amount"} htmlFor="tx-amount" span={requiresSymbol ? 2 : isWithdrawal ? 6 : 3}>
                  <MoneyInput id="tx-amount" required min={transactionType === "investment_buy" ? "0" : "0.000001"} step="0.000001" value={form.amount} onChange={(value) => set({ amount: value })} currency={form.currency} onCurrencyChange={(currency) => set({ currency })} />
                </Field>
              )}
              {!isAdjustment && !isWithdrawal && (
                <Field label="Fees" htmlFor="tx-fees" span={requiresSymbol ? 2 : 3}>
                  <MoneyInput id="tx-fees" min="0" step="0.000001" value={form.fees} onChange={(value) => set({ fees: value })} currency={form.fee_currency} onCurrencyChange={(fee_currency) => set({ fee_currency })} />
                </Field>
              )}
              {supportsSourceCash && (
                <Field label="Cash used (optional)" htmlFor="tx-cash" hint="Only when you paid in another currency." span={6}>
                  <MoneyInput id="tx-cash" min="0.000001" step="0.000001" value={form.source_amount} onChange={(source_amount) => set({ source_amount })} currency={form.source_currency} onCurrencyChange={(source_currency) => set({ source_currency })} />
                </Field>
              )}
            </>
          )}
        </Section>

        {requiresFunding && (
          <Section n={step++} title="Paid from" optional>
            <div className="f c6">
              {contributions.filter((contribution) => !isTransfer || contribution.platform_name.toLowerCase() === form.source_platform_name.toLowerCase()).map((contribution) => {
                const funding = fundingCashSources.find((item) => item.platform_name === contribution.platform_name);
                return (
                  <div className={`fund${funding ? " on" : ""}`} key={contribution.platform_name}>
                    <label className="fund-l">
                      <input className="cb" type="checkbox" checked={Boolean(funding)} onChange={() => toggleFundingCashSource(contribution)} />
                      <span className="fund-b">
                        <b>{contribution.source_label} · {contribution.platform_name}</b>
                        <span className="muted">{money(contribution.remaining_amount)} available</span>
                      </span>
                    </label>
                    {funding && (
                      <div className="fund-amt">
                        <MoneyInput id={`fund-${contribution.platform_name.replace(/\s+/g, "-")}`} required min="0.01" value={funding.amount ? String(funding.amount) : ""} onChange={(value) => updateFundingAmount(contribution.platform_name, value)} currency="CAD" />
                        <button className="btn btn-g sm" type="button" onClick={() => useRemainingAmount(contribution)}>Use all</button>
                      </div>
                    )}
                  </div>
                );
              })}
              {contributions.length === 0 && <p className="muted">No cash available to fund this from.</p>}
            </div>
          </Section>
        )}

        <Section n={step++} title="Note" optional>
          <div className="f c6">
            <label className="sr-only" htmlFor="tx-notes">Note</label>
            <textarea id="tx-notes" className="inp" rows={2} placeholder="For example: monthly auto-invest" value={form.notes} onChange={(event) => set({ notes: event.target.value })} />
          </div>
        </Section>

        {error && <p className="form-error" role="alert">{error}</p>}
      </form>
    </Dialog>
  );
}
