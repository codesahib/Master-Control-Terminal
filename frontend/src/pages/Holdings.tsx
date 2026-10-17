import { Fragment, useEffect, useState } from "react";
import { Dialog } from "../components/Dialog";
import { Icon } from "../components/Icon";
import { ACCOUNT_NAMES } from "../components/Shell";
import { Pager } from "../components/TransactionTable";
import { useApp, yearParams } from "../context";
import { errorMessage, money, pct, quantity, signedMoney, STATUS_LABELS, timeAgo } from "../lib/format";
import { useApi } from "../lib/useApi";
import { navigate, useRoute } from "../router";
import type { PaginatedPortfolioPL, PortfolioPLRow } from "../types";

const PAGE_SIZE = 25;
const STATUSES = ["", "ok", "stale", "missing", "missing_quantity", "currency_mismatch", "cash"];
const SORTS = [
  { value: "market_value", label: "Market value" },
  { value: "unrealized_pl", label: "Unrealized $" },
  { value: "unrealized_pl_pct", label: "Unrealized %" },
  { value: "symbol", label: "Symbol" },
];

function StatusChip({ status }: { status: string }) {
  const meta = STATUS_LABELS[status] || { label: status, tone: "n" };
  return <span className={`chip chip-${meta.tone}`}><span className="d" />{meta.label}</span>;
}

function plTone(value?: number | null) {
  return value == null ? "dim" : value < 0 ? "neg" : "pos";
}

export function Holdings() {
  const { year, platforms, openModal } = useApp();
  const { params } = useRoute();
  const status = params.get("status") || "";
  const [account, setAccount] = useState("");
  const [platform, setPlatform] = useState("");
  const [sortBy, setSortBy] = useState("market_value");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [year, status]);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const query = useApi<PaginatedPortfolioPL>("/portfolio/pl", {
    page,
    page_size: PAGE_SIZE,
    sort_by: sortBy,
    sort_direction: direction,
    ...(account ? { account } : {}),
    ...(platform ? { platform } : {}),
    ...(status ? { status } : {}),
    ...yearParams(year),
  });
  const rows = query.data?.items || [];
  const activeFilters = [account, platform, status].filter(Boolean).length;

  function setStatus(value: string) {
    setPage(1);
    navigate("/holdings", { status: value || undefined });
  }

  function toggle(id: string) {
    setExpanded((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  const updateValue = (row: PortfolioPLRow) => openModal({ kind: "valuation", row });
  // GICs are valued at book value, so they get Matured (renew or move to cash) instead of Update value.
  const isGic = (row: PortfolioPLRow) => row.asset_type === "gic";
  const needsValue = (row: PortfolioPLRow) => row.record_type === "holding" && row.quantity == null && !isGic(row);
  const rowAction = (row: PortfolioPLRow, size: string) =>
    isGic(row) ? <button className={`btn btn-s ${size}`} type="button" onClick={() => openModal({ kind: "gic", row })}>Matured</button>
    : needsValue(row) ? <button className={`btn btn-s ${size}`} type="button" onClick={() => updateValue(row)}>Update value</button>
    : null;

  const filters = (
    <>
      <div className="seg" role="group" aria-label="Account">
        {["", ...ACCOUNT_NAMES].map((value) => (
          <button key={value || "all"} type="button" className={account === value ? "on" : ""} aria-pressed={account === value} onClick={() => { setAccount(value); setPage(1); }}>{value || "All"}</button>
        ))}
      </div>
      <label className="select-wrap">
        <span className="sr-only">Platform</span>
        <select className="select" value={platform} onChange={(event) => { setPlatform(event.target.value); setPage(1); }}>
          <option value="">All platforms</option>
          {platforms.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        <Icon name="chevron" size={16} />
      </label>
      <div className="fchips" role="group" aria-label="Price status">
        {STATUSES.map((value) => (
          <button key={value || "all"} type="button" className={`fchip${status === value ? " on" : ""}`} aria-pressed={status === value} onClick={() => setStatus(value)}>
            {value ? STATUS_LABELS[value]?.label || value : "All"}
          </button>
        ))}
      </div>
    </>
  );

  const sortControl = (
    <div className="row">
      <label className="select-wrap">
        <span className="sr-only">Sort by</span>
        <select className="select" value={sortBy} onChange={(event) => { setSortBy(event.target.value); setPage(1); }}>
          {SORTS.map((sort) => <option key={sort.value} value={sort.value}>{sort.label}</option>)}
        </select>
        <Icon name="chevron" size={16} />
      </label>
      <button className="btn btn-s icon-btn" type="button" onClick={() => setDirection(direction === "desc" ? "asc" : "desc")} aria-label={direction === "desc" ? "Sorted high to low. Switch to low to high." : "Sorted low to high. Switch to high to low."}>
        <Icon name="sort" />
      </button>
    </div>
  );

  return (
    <div className="grid">
      <section className="card s12" aria-labelledby="hold-t">
        <div className="card-h">
          <div><h2 className="card-t" id="hold-t">Holdings</h2><span className="muted">{query.data ? `${query.data.total} positions` : "Loading…"}</span></div>
          <div className="row">
            <button className="btn btn-s phone-flex" type="button" onClick={() => setFiltersOpen(true)}><Icon name="filter" size={16} />Filters{activeFilters > 0 && <span className="badge">{activeFilters}</span>}</button>
            {sortControl}
          </div>
        </div>
        <div className="hf desktop-flex">{filters}</div>
        {query.error && <p className="form-error" role="alert">{errorMessage(query.error, "Holdings failed to load.")}</p>}

        <div className="htable tbl-wrap" role="region" aria-label="Holdings table" tabIndex={0}>
          <table className="tbl tbl-sticky">
            <thead>
              <tr>
                <th>Holding</th>
                <th>Account</th>
                <th className="r">Quantity</th>
                <th className="r">Price</th>
                <th className="r">Market value</th>
                <th className="r">Unrealized</th>
                <th>Status</th>
                <th><span className="sr-only">Expand</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const children = row.children || [];
                const canExpand = children.length > 1;
                const open = expanded.includes(row.id);
                return (
                  <Fragment key={row.id}>
                    <tr>
                      <td>
                        <div className="hold">
                          <span className="tk">{row.symbol.slice(0, 4)}</span>
                          <div className="hold-n"><b className="mono ell">{row.provider_symbol || row.symbol}</b><span className="muted ell">{row.name || row.precise_category || row.symbol}</span></div>
                        </div>
                      </td>
                      <td><span className="tag">{row.account_name}</span><div className="muted">{canExpand ? `${children.length} platforms` : row.platform_name || children[0]?.platform_name || "–"}</div></td>
                      <td className="r money"><div className="num">{quantity(row.quantity)}</div><div className="muted num">{row.average_price ? `avg ${money(row.average_price, row.currency, 2)}` : ""}</div></td>
                      <td className="r"><div className="num">{row.current_price ? money(row.current_price, row.price_currency || row.currency) : "–"}</div><div className="muted">{row.manual_valuation_date ? `manual ${row.manual_valuation_date}` : row.priced_at ? timeAgo(row.priced_at) : ""}</div></td>
                      <td className="r"><b className="num money">{money(row.market_value, row.currency)}</b><div className="muted num money">book {money(row.book_value, row.currency)}</div></td>
                      <td className="r"><div className={`num money ${plTone(row.unrealized_pl)}`}>{signedMoney(row.unrealized_pl, row.currency)}</div><div className={`num ${plTone(row.unrealized_pl)}`}>{pct(row.unrealized_pl_pct)}</div></td>
                      <td><div className="stc"><StatusChip status={row.price_status} />{!canExpand && rowAction(row, "xs")}</div></td>
                      <td>{canExpand && <button className={`exp${open ? " open" : ""}`} type="button" aria-expanded={open} aria-label={open ? "Hide platforms" : "Show platforms"} onClick={() => toggle(row.id)}><Icon name="chevron" size={16} /></button>}</td>
                    </tr>
                    {canExpand && open && children.map((child) => (
                      <tr className="kid" key={child.id}>
                        <td><div className="hold-n kid-n"><b>{child.platform_name || "–"}</b><span className="muted">{child.account_name}</span></div></td>
                        <td><span className="tag">{child.account_name}</span></td>
                        <td className="r num money">{quantity(child.quantity)}</td>
                        <td className="r num">{child.current_price ? money(child.current_price, child.price_currency || child.currency) : "–"}</td>
                        <td className="r num money">{money(child.market_value, child.currency)}</td>
                        <td className={`r num money ${plTone(child.unrealized_pl)}`}>{signedMoney(child.unrealized_pl, child.currency)} · {pct(child.unrealized_pl_pct)}</td>
                        <td><div className="stc"><StatusChip status={child.price_status} />{rowAction(child, "xs")}</div></td>
                        <td />
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
              {rows.length === 0 && !query.loading && <tr className="empty-row"><td colSpan={8} className="empty">No holdings match these filters.</td></tr>}
            </tbody>
          </table>
        </div>

        <ul className="hcards" aria-label="Holdings">
          {rows.map((row) => {
            const open = expanded.includes(row.id);
            const children = row.children || [];
            return (
              <li className={`hc${open ? " open" : ""}`} key={row.id}>
                <button className="hc-h" type="button" aria-expanded={open} onClick={() => toggle(row.id)}>
                  <span className="tk">{row.symbol.slice(0, 4)}</span>
                  <span className="hold-n"><b className="mono">{row.provider_symbol || row.symbol}</b><span className="muted ell">{row.account_name} · {children.length > 1 ? `${children.length} platforms` : row.platform_name || children[0]?.platform_name || "–"}</span></span>
                  <span className="hc-r"><b className="num money">{money(row.market_value ?? row.book_value, row.currency)}</b>{row.unrealized_pl_pct != null ? <span className={`chip chip-${row.unrealized_pl_pct < 0 ? "neg" : "pos"}`}>{pct(row.unrealized_pl_pct)}</span> : <StatusChip status={row.price_status} />}</span>
                  <Icon name="chevron" size={16} className="chev" />
                </button>
                {open && (
                  <div className="hc-d">
                    <dl className="det">
                      <div><dt>Quantity</dt><dd className="num money">{quantity(row.quantity)}</dd></div>
                      <div><dt>Avg cost</dt><dd className="num money">{row.average_price ? money(row.average_price, row.currency) : "–"}</dd></div>
                      <div><dt>Price</dt><dd className="num">{row.current_price ? money(row.current_price, row.price_currency || row.currency) : "–"}</dd></div>
                      <div><dt>Book</dt><dd className="num money">{money(row.book_value, row.currency)}</dd></div>
                      <div><dt>Unrealized</dt><dd className={`num money ${plTone(row.unrealized_pl)}`}>{signedMoney(row.unrealized_pl, row.currency)}</dd></div>
                      <div><dt>Status</dt><dd><StatusChip status={row.price_status} /></dd></div>
                    </dl>
                    {children.length > 1 && (
                      <ul className="plat-list">
                        {children.map((child) => (
                          <li key={child.id}>
                            <span><b>{child.platform_name || "–"}</b> <span className="muted money">{quantity(child.quantity)} units</span></span>
                            <span className="num money">{money(child.market_value ?? child.book_value, child.currency)}</span>
                            {rowAction(child, "sm")}
                          </li>
                        ))}
                      </ul>
                    )}
                    {children.length <= 1 && rowAction(row, "")}
                  </div>
                )}
              </li>
            );
          })}
          {rows.length === 0 && !query.loading && <li className="empty">No holdings match these filters.</li>}
        </ul>

        <Pager page={page} pageSize={PAGE_SIZE} total={query.data?.total || 0} onPageChange={setPage} />
      </section>

      {filtersOpen && (
        <Dialog title="Filters" size="sm" onClose={() => setFiltersOpen(false)} footer={<><button className="btn btn-s" type="button" onClick={() => { setAccount(""); setPlatform(""); setStatus(""); }}>Clear</button><span className="grow" /><button className="btn btn-p" type="button" onClick={() => setFiltersOpen(false)}>Show results</button></>}>
          <div className="sheet-filters">{filters}</div>
        </Dialog>
      )}
    </div>
  );
}
