import { FormEvent, useId, useState } from "react";
import { api } from "../api/client";
import { errorMessage, money, today } from "../lib/format";
import { PortfolioPLRow } from "../types";
import { Dialog } from "./Dialog";
import { Field, MoneyInput, Section } from "./form";

interface Props {
  row: PortfolioPLRow;
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}

export function GicMaturityModal({ row, onClose, onSaved }: Props) {
  const formId = useId();
  // Opened for a single platform row; a grouped row with one child carries its platform on that child.
  const child = row.children?.length === 1 ? row.children[0] : undefined;
  const accountName = child?.account_name || row.account_name;
  const platformName = row.platform_name || child?.platform_name;
  const [reinvest, setReinvest] = useState(true);
  const [interest, setInterest] = useState("");
  const [maturityDate, setMaturityDate] = useState(today());
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSaving(true);
    try {
      await api.post("/gic-maturities", {
        account_name: accountName,
        platform_name: platformName,
        instrument_id: row.instrument_id,
        transaction_date: maturityDate,
        interest: Number(interest),
        currency: row.currency,
        reinvest,
      });
      await onSaved();
      onClose();
    } catch (exc) {
      setError(errorMessage(exc, "GIC maturity failed to save."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog
      title="GIC matured"
      subtitle={`${row.name || row.symbol} · ${accountName}${platformName ? ` · ${platformName}` : ""}`}
      size="sm"
      busy={isSaving}
      onClose={onClose}
      footer={
        <>
          <span className="grow" />
          <button className="btn btn-s" type="button" onClick={onClose} disabled={isSaving}>Cancel</button>
          <button className="btn btn-p" type="submit" form={formId} disabled={isSaving}>{isSaving ? "Saving…" : reinvest ? "Renew" : "Move to cash"}</button>
        </>
      }
    >
      <form id={formId} className="form" onSubmit={submit}>
        <div className="seg" role="group" aria-label="What happened at maturity">
          <button type="button" className={reinvest ? "on" : ""} aria-pressed={reinvest} onClick={() => setReinvest(true)}>Renew</button>
          <button type="button" className={reinvest ? "" : "on"} aria-pressed={!reinvest} onClick={() => setReinvest(false)}>Move to cash</button>
        </div>
        <p className="sub">
          {reinvest
            ? "The interest is saved as income, then added to the principal."
            : `The interest is saved as income. Principal and interest become ${platformName || "platform"} cash. Buy a new GIC later for any amount.`}
        </p>
        <Section n={1} title="Maturity">
          <Field label="Interest earned" htmlFor="gic-interest"><MoneyInput id="gic-interest" required min="0.01" value={interest} onChange={setInterest} currency={row.currency} /></Field>
          <Field label="Maturity date" htmlFor="gic-date"><input id="gic-date" className="inp" type="date" required value={maturityDate} onChange={(event) => setMaturityDate(event.target.value)} /></Field>
        </Section>
        <p className="sub">{reinvest ? "New principal" : "Cash after"}: <b className="num money">{money(row.book_value + (Number(interest) || 0), row.currency)}</b></p>
        {error && <p className="form-error" role="alert">{error}</p>}
      </form>
    </Dialog>
  );
}
