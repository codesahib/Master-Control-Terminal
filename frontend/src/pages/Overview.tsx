import { useMemo, useState } from "react";
import { Donut, FlowChart, ValueChart } from "../components/Charts";
import { Icon, IconName } from "../components/Icon";
import { ACCOUNT_NAMES, CurrencySwitch } from "../components/Shell";
import { useApp, yearLabel, yearParams } from "../context";
import { errorMessage, money, pct, shortDate, signedMoney, timeAgo, TYPE_LABELS } from "../lib/format";
import { useApi } from "../lib/useApi";
import { href } from "../router";
import type { ContributionRoom, HistoryPoint, PaginatedTransactions, PortfolioOverview, TimeSeriesPoint } from "../types";

type Tab = "sector" | "account" | "platform";
const RANGES = ["1M", "3M", "YTD", "1Y", "All"] as const;

export function rrspDeadline(taxYear: number) {
  const deadline = new Date(taxYear + 1, 0, 1 + 59);
  if (deadline.getDay() === 6) deadline.setDate(deadline.getDate() + 2);
  if (deadline.getDay() === 0) deadline.setDate(deadline.getDate() + 1);
  return deadline;
}

function daysUntil(date: Date) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((date.getTime() - today.getTime()) / 86400000);
}

function cutoff(range: (typeof RANGES)[number]) {
  const date = new Date();
  if (range === "1M") date.setMonth(date.getMonth() - 1);
  else if (range === "3M") date.setMonth(date.getMonth() - 3);
  else if (range === "YTD") return `${date.getFullYear()}-01-01`;
  else if (range === "1Y") date.setFullYear(date.getFullYear() - 1);
  else return "0000-00-00";
  return date.toISOString().slice(0, 10);
}

interface Attention {
  tone: "neg" | "warn" | "info" | "acc";
  icon: IconName;
  title: string;
  sub: string;
  action: { label: string; href?: string; onClick?: () => void };
}

export function Overview() {
  const { year, currency, health: apiHealth, refreshPrices, openModal } = useApp();
  const [tab, setTab] = useState<Tab>("sector");
  const [categoryLevel, setCategoryLevel] = useState<"broad" | "precise">("precise");
  const [range, setRange] = useState<(typeof RANGES)[number]>("1Y");
  const yp = yearParams(year);

  const overview = useApi<PortfolioOverview>("/portfolio/overview", { ...yp, category_level: categoryLevel });
  const roomQ = useApi<ContributionRoom[]>(year === "all" ? "/limits" : `/limits/${year}`);
  const historyQ = useApi<HistoryPoint[]>("/portfolio/history", { days: 400 });
  const flowQ = useApi<TimeSeriesPoint[]>("/analytics/timeseries", { ...yp, currency });
  const recentQ = useApi<PaginatedTransactions>("/transactions", { page: 1, page_size: 5, sort_direction: "desc", ...yp });

  const summary = overview.data?.summary;
  const totals = overview.data?.totals;
  const health = apiHealth || overview.data?.health;
  const distribution = overview.data?.distribution?.[tab] || [];
  const room = roomQ.data || [];

  const history = useMemo(() => {
    const from = cutoff(range);
    return (historyQ.data || []).filter((point) => point.date >= from).map((point) => ({ date: point.date, market: point.market_value, book: point.book_value }));
  }, [historyQ.data, range]);
  const historyChange = history.length > 1 ? history[history.length - 1].market - history[0].market : null;

  const flow = (flowQ.data || []).slice(-12);
  const flowTotals = flow.reduce((sum, point) => ({ contributions: sum.contributions + point.contributions, investments: sum.investments + point.investments }), { contributions: 0, investments: 0 });

  const allocation = useMemo(() => {
    const sorted = [...distribution].filter((row) => row.value > 0).sort((a, b) => b.value - a.value);
    const top = sorted.slice(0, 7);
    const rest = sorted.slice(7).reduce((sum, row) => sum + row.value, 0);
    return rest > 0 ? [...top, { label: "Everything else", value: rest }] : top;
  }, [distribution]);
  const allocationTotal = allocation.reduce((sum, row) => sum + row.value, 0);

  const attention: Attention[] = [];
  if (health?.missing_price) attention.push({ tone: "neg", icon: "warn", title: `${health.missing_price} holding${health.missing_price > 1 ? "s have" : " has"} no live price`, sub: "Market value and P/L are hidden for these.", action: { label: "Review", href: href("/holdings", { status: "missing" }) } });
  if (health?.missing_quantity) attention.push({ tone: "warn", icon: "edit", title: `${health.missing_quantity} holding${health.missing_quantity > 1 ? "s need" : " needs"} a value`, sub: "No quantity recorded. Add a manual value.", action: { label: "Update", href: href("/holdings", { status: "missing_quantity" }) } });
  if (health?.stale) attention.push({ tone: "warn", icon: "clock", title: `${health.stale} price${health.stale > 1 ? "s are" : " is"} older than 24 hours`, sub: `Last refresh ${timeAgo(health.prices_updated_at)}.`, action: { label: "Refresh", onClick: refreshPrices } });
  if (health?.fx_missing) attention.push({ tone: "warn", icon: "currency_exchange", title: `${health.fx_missing} USD row${health.fx_missing > 1 ? "s have" : " has"} no exchange rate`, sub: "They are left out of CAD totals until prices refresh.", action: { label: "Refresh", onClick: refreshPrices } });
  health?.negative_cash.forEach((row) => attention.push({ tone: "neg", icon: "cash", title: `Negative cash in ${row.account_name}${row.platform_name ? ` · ${row.platform_name}` : ""}`, sub: `${money(row.amount, row.currency)}. A contribution or transfer may be missing.`, action: { label: "Check", href: href(`/accounts/${row.account_name}`) } }));
  const idleCad = (health?.idle_cash || []).filter((row) => row.currency === "CAD").reduce((sum, row) => sum + row.amount, 0);
  if (idleCad > 1) attention.push({ tone: "info", icon: "cash", title: `${money(idleCad)} cash is not invested`, sub: (health?.idle_cash || []).slice(0, 2).map((row) => `${row.account_name} ${row.platform_name || ""} ${money(row.amount, row.currency)}`).join(" · "), action: { label: "View", href: href("/holdings", { status: "cash" }) } });
  room.filter((row) => row.remaining < -0.005).forEach((row) => attention.push({ tone: "neg", icon: "warn", title: `Over-contributed in ${row.account} by ${money(-row.remaining)}`, sub: "Over-contributions can be taxed. Check your limits.", action: { label: "Limits", href: href("/room", { account: row.account }) } }));
  const rrsp = room.find((row) => row.account === "RRSP");
  if (typeof year === "number" && rrsp && rrsp.remaining > 0) {
    const deadline = rrspDeadline(year);
    const days = daysUntil(deadline);
    if (days >= 0 && days < 400) attention.push({ tone: "acc", icon: "clock", title: `RRSP deadline in ${days} days`, sub: `${money(rrsp.remaining, "CAD", 0)} of ${year} room left · ${shortDate(deadline.toISOString().slice(0, 10))}`, action: { label: "Contribute", onClick: () => openModal({ kind: "contribution", account: "RRSP" }) } });
  }

  const roomLeft = room.reduce((sum, row) => sum + Math.max(0, row.remaining), 0);
  const recent = (recentQ.data?.items || []).slice(0, 5);

  return (
    <div className="grid">
      {overview.error && <p className="form-error s12" role="alert">{errorMessage(overview.error, "Portfolio data failed to load.")}</p>}
      <div className="phone-only filter-chips s12">
        <CurrencySwitch />
        <button className="chip-btn" type="button" onClick={refreshPrices}>
          <span className="live" aria-hidden="true" />Prices {timeAgo(health?.prices_updated_at)}<Icon name="refresh" size={14} />
        </button>
      </div>

      <section className="card hero s8" aria-labelledby="pv-label">
        <div className="hero-h">
          <div>
            <div className="sub" id="pv-label">Portfolio value · CAD</div>
            <div className="big num money">{totals ? money(totals.market_value) : "–"}</div>
            <div className="row">
              {historyChange !== null ? (
                <span className={`chip ${historyChange < 0 ? "chip-neg" : "chip-pos"}`}>{historyChange < 0 ? "▼" : "▲"} <span className="money">{signedMoney(historyChange)}</span></span>
              ) : (
                totals && <span className={`chip ${totals.unrealized_pl < 0 ? "chip-neg" : "chip-pos"}`}>{totals.unrealized_pl < 0 ? "▼" : "▲"} <span className="money">{signedMoney(totals.unrealized_pl)}</span> · {pct(totals.unrealized_pl_pct)}</span>
              )}
              <span className="sub">{historyChange !== null ? `over ${range === "All" ? "all time" : range}` : "unrealized, all time"}</span>
            </div>
          </div>
          {history.length > 1 && (
            <div className="seg" role="group" aria-label="Chart range">
              {RANGES.map((value) => <button key={value} type="button" className={range === value ? "on" : ""} aria-pressed={range === value} onClick={() => setRange(value)}>{value}</button>)}
            </div>
          )}
        </div>
        {history.length > 1 ? (
          <ValueChart points={history} />
        ) : (
          <div className="empty-chart">
            <Icon name="activity" size={22} />
            <p>Value history starts with your next price refresh. One point is saved per day.</p>
          </div>
        )}
      </section>

      <section className="card s4" aria-labelledby="attn-t">
        <div className="card-h"><h2 className="card-t" id="attn-t">Needs attention</h2>{attention.length > 0 && <span className="chip chip-warn">{attention.length}</span>}</div>
        {attention.length === 0 ? (
          <div className="all-clear"><Icon name="check" size={22} /><p>All clear. Prices, cash and room look fine.</p></div>
        ) : (
          <ul className="attn-list">
            {attention.slice(0, 6).map((item) => (
              <li className="attn" key={item.title}>
                <span className={`ai ai-${item.tone}`}><Icon name={item.icon} /></span>
                <div className="attn-b"><div className="attn-t">{item.title}</div><div className="muted">{item.sub}</div></div>
                {item.action.href ? <a className="link" href={item.action.href}>{item.action.label}</a> : <button className="link" type="button" onClick={item.action.onClick}>{item.action.label}</button>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="kpis s12" aria-label="Key figures">
        <div className="card kpi"><span className="sub">Net invested</span><span className="kpi-v num money">{money(totals?.book_value)}</span><span className="muted">Book value across accounts</span></div>
        <div className="card kpi">
          <span className="sub">Unrealized gain</span>
          <span className={`kpi-v num money ${(totals?.unrealized_pl || 0) < 0 ? "neg" : "pos"}`}>{signedMoney(totals?.unrealized_pl)}</span>
          <div className="row"><span className={`chip ${(totals?.unrealized_pl || 0) < 0 ? "chip-neg" : "chip-pos"}`}>{pct(totals?.unrealized_pl_pct)}</span><span className="muted">on priced holdings</span></div>
        </div>
        <div className="card kpi"><span className="sub">Cash ready to invest</span><span className="kpi-v num money">{money(totals?.investable_cash)}</span><a className="link" href={href("/holdings", { status: "cash" })}>See cash</a></div>
        <div className="card kpi">
          <span className="sub">Room left · {yearLabel(year)}</span>
          <span className="kpi-v num money">{money(roomLeft)}</span>
          <span className="muted">{room.map((row) => `${row.account} ${row.remaining > 0 ? money(row.remaining, "CAD", 0) : row.remaining < 0 ? "over" : "maxed"}`).join(" · ")}</span>
        </div>
      </section>

      <section className="card s5" aria-labelledby="acct-t">
        <div className="card-h"><h2 className="card-t" id="acct-t">Accounts</h2><a className="link" href={href("/room")}>Contribution limits</a></div>
        <div className="accts">
          {ACCOUNT_NAMES.map((name, index) => {
            const limit = room.find((row) => row.account === name);
            const pl = summary?.account_pl.find((row) => row.account === name);
            const used = limit && limit.total_room > 0 ? Math.min(100, (limit.used / limit.total_room) * 100) : 0;
            const chip = !limit
              ? null
              : limit.remaining < -0.005
                ? { cls: "chip-neg", text: `Over by ${money(-limit.remaining, "CAD", 0)}` }
                : limit.remaining <= 0.005 && limit.total_room > 0
                  ? { cls: "chip-n", text: `Maxed for ${yearLabel(year)}` }
                  : name === "RRSP" && typeof year === "number"
                    ? { cls: "chip-info", text: `Deadline ${shortDate(rrspDeadline(year).toISOString().slice(0, 10))}` }
                    : { cls: "chip-pos", text: `${money(limit.remaining, "CAD", 0)} left to use` };
            return (
              <a className="acct" key={name} href={href(`/accounts/${name}`)}>
                <div className="acct-top">
                  <span className={`acct-av tint-c${index + 1}`}>{name.slice(0, 2)}</span>
                  <div className="acct-n"><b>{name}</b><span className="muted">Invested value</span></div>
                  <div className="acct-v"><b className="num money">{money(pl?.marketReporting)}</b><span className={`num ${(pl?.plReporting || 0) < 0 ? "neg" : "pos"}`}>{pct(pl?.plPct)}</span></div>
                </div>
                {limit && (
                  <>
                    <div className="room"><span className="sub">{yearLabel(year)} room</span><span className="num money"><b>{money(Math.max(limit.remaining, 0), "CAD", 0)}</b> <span className="sub">left of {money(limit.total_room, "CAD", 0)}</span></span></div>
                    <span className="bar" role="img" aria-label={`${name} room ${used.toFixed(0)}% used`}><span className={`fill-c${index + 1}`} style={{ width: `${used}%` }} /></span>
                  </>
                )}
                {chip && <div className="row"><span className={`chip ${chip.cls}`}>{chip.text}</span></div>}
              </a>
            );
          })}
        </div>
      </section>

      <section className="card s7" aria-labelledby="alloc-t">
        <div className="card-h">
          <h2 className="card-t" id="alloc-t">Allocation</h2>
          <div className="row">
            {tab === "sector" && (
              <div className="seg seg-sm" role="group" aria-label="Category level">
                {(["broad", "precise"] as const).map((level) => <button key={level} type="button" className={categoryLevel === level ? "on" : ""} aria-pressed={categoryLevel === level} onClick={() => setCategoryLevel(level)}>{level === "broad" ? "Broad" : "Precise"}</button>)}
              </div>
            )}
            <div className="seg" role="group" aria-label="Group allocation by">
              {(["sector", "account", "platform"] as const).map((value) => <button key={value} type="button" className={tab === value ? "on" : ""} aria-pressed={tab === value} onClick={() => setTab(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}
            </div>
          </div>
        </div>
        {allocation.length === 0 ? (
          <p className="empty">No allocation data for these filters.</p>
        ) : (
          <div className="alloc">
            <div className="donut">
              <Donut data={allocation} />
              <div className="donut-c"><span className="muted">Total</span><b className="num money">{money(allocationTotal, "CAD", 0)}</b><span className="muted">{allocation.length} groups</span></div>
            </div>
            <ul className="lgl">
              {allocation.map((row, index) => {
                const share = allocationTotal ? (row.value / allocationTotal) * 100 : 0;
                return (
                  <li className="lgr" key={row.label}>
                    <span className={`d fill-c${index + 1}`} />
                    <span className="ell">{row.label}</span>
                    <span className="lgb"><span className={`fill-c${index + 1}`} style={{ width: `${Math.min(100, (row.value / allocation[0].value) * 100)}%` }} /></span>
                    <span className="lgv num money">{money(row.value, "CAD", 0)}</span>
                    <span className="lgp num">{share.toFixed(1)}%</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      <section className="card s7" aria-labelledby="flow-t">
        <div className="card-h">
          <div><h2 className="card-t" id="flow-t">Money in vs invested</h2><span className="muted">Monthly{year === "all" ? ", last 12 months" : `, ${year}`}</span></div>
          <div className="ftot">
            <div><span className="sub"><i className="d fill-c1" />Contributed</span><b className="num money">{money(flowTotals.contributions, "CAD", 0)}</b></div>
            <div><span className="sub"><i className="d fill-c2" />Invested (net)</span><b className="num money">{money(flowTotals.investments, "CAD", 0)}</b></div>
          </div>
        </div>
        {flow.length ? <FlowChart data={flow} /> : <p className="empty">No contributions or trades in this period.</p>}
      </section>

      <section className="card s5" aria-labelledby="act-t">
        <div className="card-h"><h2 className="card-t" id="act-t">Recent activity</h2><a className="link" href={href("/activity")}>View all</a></div>
        {recent.length === 0 ? (
          <p className="empty">No activity yet.</p>
        ) : (
          <ul className="acts">
            {recent.map((row) => (
              <li className="act" key={row.id}>
                <span className={`act-i t-${row.transaction_type}`}><Icon name={row.transaction_type} /></span>
                <div className="act-b"><b>{TYPE_LABELS[row.transaction_type]}{row.symbol ? ` · ${row.symbol}` : ""}</b><span className="muted ell">{[row.account_name, row.platform_name].filter(Boolean).join(" · ")}</span></div>
                <div className="act-r"><b className={`num money ${["contribution", "dividend_interest", "investment_sell"].includes(row.transaction_type) ? "pos" : ""}`}>{money(row.amount, row.currency)}</b><span className="muted">{shortDate(row.transaction_date)}</span></div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
