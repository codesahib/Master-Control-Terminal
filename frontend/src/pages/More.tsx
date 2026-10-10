import { Icon } from "../components/Icon";
import { ACCOUNT_NAMES, CurrencySwitch, ThemeSwitch, YearSelect } from "../components/Shell";
import { useApp } from "../context";
import { href } from "../router";
import { DataActions } from "./Data";

export function More() {
  const { privacy, togglePrivacy } = useApp();
  return (
    <div className="grid">
      <section className="card s12 narrow" aria-labelledby="more-view">
        <h2 className="sec-t" id="more-view">View</h2>
        <ul className="list">
          <li className="list-row"><span className="li"><Icon name="calendar" size={16} /></span><span className="grow">Tax year</span><YearSelect id="more-year" /></li>
          <li className="list-row"><span className="li"><Icon name="currency_exchange" size={16} /></span><span className="grow">Analytics currency</span><CurrencySwitch /></li>
        </ul>

        <h2 className="sec-t">Accounts</h2>
        <ul className="list">
          {ACCOUNT_NAMES.map((name, index) => (
            <li key={name}><a className="list-row" href={href(`/accounts/${name}`)}><span className={`av tint-c${index + 1}`}>{name.slice(0, 2)}</span><span className="grow">{name}</span><Icon name="right" size={16} /></a></li>
          ))}
          <li><a className="list-row" href={href("/room")}><span className="li"><Icon name="room" size={16} /></span><span className="grow">Contribution limits</span><Icon name="right" size={16} /></a></li>
        </ul>

        <h2 className="sec-t">Data</h2>
        <DataActions />

        <h2 className="sec-t">Appearance</h2>
        <ul className="list">
          <li className="list-row"><span className="li"><Icon name="sun" size={16} /></span><span className="grow">Theme</span><ThemeSwitch /></li>
          <li className="list-row">
            <span className="li"><Icon name="eyeOff" size={16} /></span>
            <span className="grow">Privacy mode<span className="muted block">Blur amounts when sharing your screen</span></span>
            <button className={`switch${privacy ? " on" : ""}`} type="button" role="switch" aria-checked={privacy} aria-label="Privacy mode" onClick={togglePrivacy} />
          </li>
        </ul>
      </section>
    </div>
  );
}
