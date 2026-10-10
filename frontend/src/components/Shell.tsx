import { ReactNode, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { isApiLoading, subscribeToApiLoading } from "../api/client";
import { ThemePref, useApp, yearLabel } from "../context";
import { timeAgo } from "../lib/format";
import { href, useRoute } from "../router";
import { Icon, IconName } from "./Icon";

export const ACCOUNT_NAMES = ["RRSP", "TFSA", "FHSA"];

const THEMES: { value: ThemePref; icon: IconName; label: string }[] = [
  { value: "light", icon: "sun", label: "Light" },
  { value: "dark", icon: "moon", label: "Dark" },
  { value: "system", icon: "system", label: "Auto" },
];

function NavLink({ to, icon, label, avatar }: { to: string; icon?: IconName; label: string; avatar?: string }) {
  const { path } = useRoute();
  const active = path === to || (to !== "/overview" && path.startsWith(`${to}/`));
  return (
    <a className={`nav${active ? " on" : ""}`} href={href(to)} aria-current={active ? "page" : undefined} title={label}>
      {avatar ? <span className={`av av-${avatar.toLowerCase()}`} aria-hidden="true">{avatar.slice(0, 2)}</span> : icon && <Icon name={icon} />}
      <span className="lbl">{label}</span>
    </a>
  );
}

export function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const { themePref, setThemePref } = useApp();
  return (
    <div className={`seg${compact ? " seg-col" : ""}`} role="group" aria-label="Theme">
      {THEMES.map((theme) => (
        <button key={theme.value} type="button" className={themePref === theme.value ? "on" : ""} aria-pressed={themePref === theme.value} onClick={() => setThemePref(theme.value)} title={theme.label}>
          <Icon name={theme.icon} size={16} />
          <span className="lbl">{theme.label}</span>
        </button>
      ))}
    </div>
  );
}

function Sidebar() {
  const { health, refreshPrices, refreshingPrices } = useApp();
  return (
    <aside className="side" aria-label="Main navigation">
      <a className="brand" href={href("/overview")}>
        <span className="brand-mark"><Icon name="logo" /></span>
        <span className="lbl">Master Terminal</span>
      </a>
      <NavLink to="/overview" icon="overview" label="Overview" />
      <NavLink to="/holdings" icon="holdings" label="Holdings" />
      <NavLink to="/activity" icon="activity" label="Activity" />
      <div className="nav-sec">Accounts</div>
      {ACCOUNT_NAMES.map((name) => <NavLink key={name} to={`/accounts/${name}`} label={name} avatar={name} />)}
      <div className="nav-sec">Planning</div>
      <NavLink to="/room" icon="room" label="Contribution room" />
      <div className="nav-sec">Data</div>
      <NavLink to="/data" icon="data" label="Import and export" />
      <div className="side-foot">
        <div className="price">
          <span className={`live${health?.stale || health?.missing_price ? " warn" : ""}`} aria-hidden="true" />
          <div className="lbl">
            <div className="price-t">Prices</div>
            <div className="muted">Updated {timeAgo(health?.prices_updated_at)}</div>
          </div>
          <button className="btn btn-g icon-btn sm" type="button" onClick={refreshPrices} disabled={refreshingPrices} aria-label="Refresh prices" title="Refresh prices">
            <Icon name="refresh" size={16} className={refreshingPrices ? "spin" : ""} />
          </button>
        </div>
        <ThemeSwitch />
      </div>
    </aside>
  );
}

export function YearSelect({ id = "year" }: { id?: string }) {
  const { year, setYear, years } = useApp();
  return (
    <label className="select-wrap" htmlFor={id}>
      <span className="sr-only">Tax year</span>
      <select id={id} className="select" value={year} onChange={(event) => setYear(event.target.value === "all" ? "all" : Number(event.target.value))}>
        {years.map((value) => <option key={value} value={value}>{value}</option>)}
        <option value="all">{yearLabel("all")}</option>
      </select>
      <Icon name="chevron" size={16} />
    </label>
  );
}

export function CurrencySwitch() {
  const { currency, setCurrency } = useApp();
  return (
    <div className="seg" role="group" aria-label="Analytics currency">
      {["CAD", "USD"].map((value) => (
        <button key={value} type="button" className={currency === value ? "on" : ""} aria-pressed={currency === value} onClick={() => setCurrency(value)}>{value}</button>
      ))}
    </div>
  );
}

export function PrivacyButton() {
  const { privacy, togglePrivacy } = useApp();
  return (
    <button className="btn btn-s icon-btn" type="button" onClick={togglePrivacy} aria-pressed={privacy} aria-label={privacy ? "Show amounts" : "Hide amounts"} title={privacy ? "Show amounts" : "Hide amounts"}>
      <Icon name={privacy ? "eyeOff" : "eye"} />
    </button>
  );
}

function NewMenu() {
  const { openModal } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function choose(kind: "transaction" | "contribution" | "withdrawal") {
    setOpen(false);
    if (kind === "contribution") openModal({ kind: "contribution" });
    else openModal({ kind: "transaction", type: kind === "withdrawal" ? "withdrawal" : undefined });
  }

  return (
    <div className="new-wrap hide-phone" ref={ref} onKeyDown={(event) => event.key === "Escape" && setOpen(false)}>
      <button className="btn btn-p" type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="plus" />New<Icon name="chevron" size={16} />
      </button>
      {open && (
        <div className="menu" role="menu" aria-label="Create">
          <NewItem icon="transfer" title="Transaction" sub="Buy, sell, dividend, transfer, FX" onClick={() => choose("transaction")} tone="c2" />
          <NewItem icon="contribution" title="Contribution" sub="Money into RRSP, TFSA or FHSA" onClick={() => choose("contribution")} tone="c1" />
          <NewItem icon="withdrawal" title="Withdrawal" sub="Cash taken out of an account" onClick={() => choose("withdrawal")} tone="c5" />
        </div>
      )}
    </div>
  );
}

export function NewItem({ icon, title, sub, onClick, tone }: { icon: IconName; title: string; sub: string; onClick: () => void; tone: string }) {
  return (
    <button className="mi" type="button" role="menuitem" onClick={onClick}>
      <span className={`mi-i tint-${tone}`}><Icon name={icon} /></span>
      <span className="mi-t"><b>{title}</b><span className="muted">{sub}</span></span>
    </button>
  );
}

function TabBar() {
  const { path } = useRoute();
  const { openModal } = useApp();
  const tab = (to: string, icon: IconName, label: string) => {
    const active = path === to || path.startsWith(`${to}/`);
    return (
      <a className={`tab${active ? " on" : ""}`} href={href(to)} aria-current={active ? "page" : undefined}>
        <Icon name={icon} size={20} />{label}
      </a>
    );
  };
  return (
    <nav className="tabbar" aria-label="Primary">
      {tab("/overview", "overview", "Overview")}
      {tab("/holdings", "holdings", "Holdings")}
      <button className="fab" type="button" aria-label="New entry" onClick={() => openModal({ kind: "new" })}><Icon name="plus" size={24} /></button>
      {tab("/activity", "activity", "Activity")}
      {tab("/more", "more", "More")}
    </nav>
  );
}

function LoadingBar() {
  const loading = useSyncExternalStore(subscribeToApiLoading, isApiLoading);
  return <div className={`loading-bar${loading ? " on" : ""}`} role="progressbar" aria-label="Loading" aria-hidden={!loading} />;
}

function ToastHost() {
  const { toast } = useApp();
  return (
    <div className="toast-host" role="status" aria-live="polite">
      {toast && <div key={toast.id} className={`toast toast-${toast.tone}`}>{toast.message}</div>}
    </div>
  );
}

export function Shell({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="shell">
      <LoadingBar />
      <Sidebar />
      <div className="main">
        <header className="top">
          <h1>{title}</h1>
          {actions}
          <YearSelect />
          <div className="hide-phone"><CurrencySwitch /></div>
          <PrivacyButton />
          <NewMenu />
        </header>
        <main className="page" id="main">{children}</main>
        <TabBar />
      </div>
      <ToastHost />
    </div>
  );
}
