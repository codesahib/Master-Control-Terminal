import { FormEvent, useId, useState } from "react";
import { api } from "../api/client";
import { errorMessage, money } from "../lib/format";
import { Contribution } from "../types";
import { Dialog } from "./Dialog";
import { Field, MoneyInput, PlatformSelect, Section, Segmented } from "./form";
import { Icon } from "./Icon";
import { ACCOUNT_NAMES } from "./Shell";
import { platformOptions } from "./transactionFormConfig";

interface Props {
  onClose: () => void;
  onSaved: () => Promise<void> | void;
  onDelete?: () => void;
  defaultAccount?: string;
  contribution?: Contribution;
  platforms?: string[];
}

export function ContributionModal({ onClose, onSaved, onDelete, defaultAccount = "RRSP", contribution, platforms = platformOptions }: Props) {
  const formId = useId();
  const [form, setForm] = useState({
    transaction_date: contribution?.transaction_date?.slice(0, 10) || new Date().toISOString().slice(0, 10),
    account_name: contribution?.account_name || defaultAccount,
    platform_name: contribution ? contribution.platform_name || "" : platforms[0] || "",
    amount: contribution ? String(contribution.amount) : "",
    notes: contribution?.notes || "",
  });
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const platformChoices = contribution?.platform_name && !platforms.includes(contribution.platform_name) ? [contribution.platform_name, ...platforms] : platforms;
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }));

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
      if (contribution) await api.put(`/contributions/${contribution.id}`, payload);
      else await api.post("/contributions", payload);
      await onSaved();
      onClose();
    } catch (exc) {
      setError(errorMessage(exc, "Failed to save the contribution."));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog
      title={contribution ? "Edit contribution" : "New contribution"}
      subtitle="Money you put into a registered account. It uses contribution room."
      size="sm"
      onClose={onClose}
      footer={
        <>
          {contribution && onDelete && (
            <button className="btn btn-danger-g" type="button" onClick={onDelete}><Icon name="trash" size={16} />Delete</button>
          )}
          <span className="grow" />
          <button className="btn btn-s" type="button" onClick={onClose}>Cancel</button>
          <button className="btn btn-p" type="submit" form={formId} disabled={isSaving}>{isSaving ? "Saving…" : "Save contribution"}</button>
        </>
      }
    >
      <form id={formId} className="form" onSubmit={submit}>
        <Section n={1} title="Where">
          <Segmented label="Account" value={form.account_name} options={ACCOUNT_NAMES} onChange={(account_name) => set({ account_name })} span={6} />
          <Field label="Platform" htmlFor="contribution-platform"><PlatformSelect id="contribution-platform" value={form.platform_name} platforms={platformChoices} placeholder="No platform" onChange={(platform_name) => set({ platform_name })} /></Field>
          <Field label="Date" htmlFor="contribution-date"><input id="contribution-date" className="inp" type="date" required value={form.transaction_date} onChange={(event) => set({ transaction_date: event.target.value })} /></Field>
        </Section>
        <Section n={2} title="How much">
          <Field label="Amount" htmlFor="contribution-amount" span={6} hint={Number(form.amount) > 0 ? `${money(Number(form.amount))} toward ${form.account_name} room` : undefined}>
            <MoneyInput id="contribution-amount" required min="0.01" value={form.amount} onChange={(amount) => set({ amount })} currency="CAD" />
          </Field>
        </Section>
        <Section n={3} title="Note" optional>
          <div className="f c6">
            <label className="sr-only" htmlFor="contribution-notes">Note</label>
            <textarea id="contribution-notes" className="inp" rows={2} value={form.notes} onChange={(event) => set({ notes: event.target.value })} />
          </div>
        </Section>
        {error && <p className="form-error" role="alert">{error}</p>}
      </form>
    </Dialog>
  );
}
