import { ReactNode, useId } from "react";

export const CURRENCIES = ["CAD", "USD"];

export function Section({ n, title, optional, children }: { n: number; title: string; optional?: boolean; children: ReactNode }) {
  return (
    <section className="fs">
      <h3 className="fs-t">
        <span className="fs-n">{n}</span>
        {title}
        {optional && <span className="muted">optional</span>}
      </h3>
      <div className="fg">{children}</div>
    </section>
  );
}

export function Field({ label, htmlFor, hint, span = 3, children }: { label: string; htmlFor?: string; hint?: ReactNode; span?: 2 | 3 | 6; children: ReactNode }) {
  return (
    <div className={`f c${span}`}>
      <label className="fl" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Segmented<T extends string>({ label, value, options, onChange, span = 3 }: { label: string; value: T; options: readonly T[]; onChange: (value: T) => void; span?: 2 | 3 | 6 }) {
  const id = useId();
  return (
    <div className={`f c${span}`}>
      <span className="fl" id={id}>{label}</span>
      <div className="seg seg-fill" role="radiogroup" aria-labelledby={id}>
        {options.map((option) => (
          <button key={option} type="button" role="radio" aria-checked={value === option} className={value === option ? "on" : ""} onClick={() => onChange(option)}>
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

interface MoneyInputProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  currency: string;
  onCurrencyChange?: (currency: string) => void;
  min?: string;
  step?: string;
  required?: boolean;
  placeholder?: string;
}

export function MoneyInput({ id, value, onChange, currency, onCurrencyChange, min = "0", step = "0.01", required, placeholder }: MoneyInputProps) {
  return (
    <div className="grp">
      <span className="pre" aria-hidden="true">$</span>
      <input id={id} type="number" inputMode="decimal" min={min} step={step} required={required} placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} />
      {onCurrencyChange ? (
        <select className="suf" aria-label="Currency" value={currency} onChange={(event) => onCurrencyChange(event.target.value)}>
          {(CURRENCIES.includes(currency) ? CURRENCIES : [...CURRENCIES, currency]).map((option) => <option key={option}>{option}</option>)}
        </select>
      ) : (
        <span className="suf">{currency}</span>
      )}
    </div>
  );
}

export function PlatformSelect({ id, value, onChange, platforms, required, placeholder = "Select platform" }: { id: string; value: string; onChange: (value: string) => void; platforms: string[]; required?: boolean; placeholder?: string }) {
  return (
    <select id={id} className="inp" required={required} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">{placeholder}</option>
      {platforms.map((platform) => <option key={platform} value={platform}>{platform}</option>)}
    </select>
  );
}
