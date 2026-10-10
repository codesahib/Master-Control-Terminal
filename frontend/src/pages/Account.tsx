import { Fragment, useState } from "react";
import { Icon } from "../components/Icon";
import { Pager, TransactionTable } from "../components/TransactionTable";
import { useApp, yearLabel, yearParams } from "../context";
import { errorMessage, money, quantity, shortDate } from "../lib/format";
import { useRecordActions } from "../lib/records";
import { useApi } from "../lib/useApi";
import { href } from "../router";
import type { Contribution, ContributionRoom, Holding, PaginatedAccountTransactions, TransactionType } from "../types";
import { ActivityFilters } from "./Activity";
import { rrspDeadline } from "./Overview";

const PAGE_SIZE = 20;
const ACCOUNT_TYPES: TransactionType[] = ["investment_buy", "investment_sell", "transfer", "dividend_interest", "dividend_reinvestment", "quantity_adjustment", "currency_exchange", "withdrawal"];

export function Account({ name }: { name: string }) {
  const { year, openModal } = useApp();
  const actions = useRecordActions();
  const [type, setType] = useState<TransactionType | "">("");
  const [platform, setPlatform] = useState("");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<string[]>([]);
  const yp = yearParams(year);

  const roomQ = useApi<ContributionRoom[]>(year === "all" ? "/limits" : `/limits/${year}`);
  const contributionsQ = useApi<Contribution[]>("/contributions", { account: name, ...yp });
  const activityQ = useApi<PaginatedAccountTransactions>("/account-transactions", {
    account: name,
    page,
    page_size: PAGE_SIZE,
    sort_direction: direction,
    ...(type ? { transaction_type: type } : {}),
    ...(platform ? { platform } : {}),
    ...yp,
  });
  const holdingsQ = useApi<Holding[]>("/holdings", { account: name, ...yp });
  const room = roomQ.data?.find((row) => row.account === name);
  const used = room && room.total_room > 0 ? Math.min(100, (room.used / room.total_room) * 100) : 0;
  const reset = <T,>(setter: (value: T) => void) => (value: T) => { setter(value); setPage(1); };
  const error = contributionsQ.error || activityQ.error || holdingsQ.error;

  return (
    <div className="grid">
      <section className="card s12 acct-head" aria-labelledby="acct-title">
        <div className="card-h">
          <div>
            <h2 className="card-t" id="acct-title">{name} · {yearLabel(year)}</h2>
            <span className="muted">Contributions, account activity and derived holdings</span>
          </div>
          <div className="row">
            <a className="btn btn-s" href={href("/room", { account: name })}><Icon name="room" size={16} />Limits</a>
            <button className="btn btn-s" type="button" onClick={() => openModal({ kind: "contribution", account: name })}><Icon name="contribution" size={16} />Contribution</button>
            <button className="btn btn-p" type="button" onClick={() => openModal({ kind: "transaction", account: name })}><Icon name="plus" size={16} />Transaction</button>
          </div>
        </div>
        {room ? (
          <div className="room-block">
            <div className="room-nums">
              <div><span className="muted">Total room</span><b className="num money">{money(room.total_room)}</b></div>
              <div><span className="muted">Used</span><b className="num money">{money(room.used)}</b></div>
              <div><span className="muted">Remaining</span><b className={`num money ${room.remaining < 0 ? "neg" : ""}`}>{money(room.remaining)}</b></div>
              {name === "RRSP" && typeof year === "number" && <div><span className="muted">Deadline</span><b>{shortDate(rrspDeadline(year).toISOString().slice(0, 10))}</b></div>}
            </div>
            <span className="bar bar-lg" role="img" aria-label={`${used.toFixed(0)}% of room used`}><span className={room.remaining < 0 ? "fill-neg" : "fill-c1"} style={{ width: `${used}%` }} /></span>
          </div>
        ) : (
          <p className="muted">No contribution room set for {yearLabel(year)}. <a className="link" href={href("/room", { account: name })}>Set limits</a></p>
        )}
      </section>

      {error && <p className="form-error s12" role="alert">{errorMessage(error, "Account data failed to load.")}</p>}

      <TransactionTable
        title="Contributions"
        rows={contributionsQ.data || []}
        variant="contributions"
        showAccount={false}
        onEdit={actions.edit}
        onDelete={actions.remove}
        emptyMessage={contributionsQ.loading ? "Loading…" : `No contributions for ${name} in ${yearLabel(year)}.`}
      />

      <TransactionTable
        title="Account transactions"
        rows={activityQ.data?.items || []}
        variant="transactions"
        showAccount={false}
        onEdit={actions.edit}
        onDelete={actions.remove}
        controls={<ActivityFilters type={type} onType={reset(setType)} platform={platform} onPlatform={reset(setPlatform)} direction={direction} onDirection={reset(setDirection)} types={ACCOUNT_TYPES} />}
        footer={<Pager page={page} pageSize={activityQ.data?.page_size || PAGE_SIZE} total={activityQ.data?.total || 0} onPageChange={setPage} />}
        emptyMessage={activityQ.loading ? "Loading…" : "No account transactions match these filters."}
      />

      <section className="card s12" aria-labelledby="derived-t">
        <div className="card-h"><h2 className="card-t" id="derived-t">Derived holdings</h2><span className="muted">Built from your transactions, at book value</span></div>
        <div className="tbl-wrap">
          <table className="tbl tbl-sticky compact">
            <thead>
              <tr><th>Symbol</th><th className="r">Quantity</th><th className="r">Avg cost</th><th className="r">Book value</th><th>Category</th><th>As of</th><th><span className="sr-only">Expand</span></th></tr>
            </thead>
            <tbody>
              {(holdingsQ.data || []).map((holding) => {
                const children = holding.children || [];
                const canExpand = children.length > 1;
                const open = expanded.includes(holding.id);
                return (
                  <Fragment key={holding.id}>
                    <tr>
                      <td><b className="mono">{holding.symbol}</b><div className="muted">{canExpand ? `${children.length} platforms` : holding.platform_name || children[0]?.platform_name || "–"}</div></td>
                      <td className="r num">{quantity(holding.quantity)}</td>
                      <td className="r num">{holding.average_price ? money(holding.average_price, holding.currency, 4) : "–"}</td>
                      <td className="r num money">{money(holding.book_value, holding.currency)}</td>
                      <td>{holding.precise_category || holding.broad_category || "–"}</td>
                      <td className="nowrap">{shortDate(holding.as_of_date)}</td>
                      <td>{canExpand && <button className={`exp${open ? " open" : ""}`} type="button" aria-expanded={open} aria-label={open ? "Hide platforms" : "Show platforms"} onClick={() => setExpanded((current) => (open ? current.filter((id) => id !== holding.id) : [...current, holding.id]))}><Icon name="chevron" size={16} /></button>}</td>
                    </tr>
                    {open && children.map((child) => (
                      <tr className="kid" key={child.id}>
                        <td><span className="kid-n">{child.platform_name || "–"}</span></td>
                        <td className="r num">{quantity(child.quantity)}</td>
                        <td className="r num">{child.average_price ? money(child.average_price, child.currency, 4) : "–"}</td>
                        <td className="r num money">{money(child.book_value, child.currency)}</td>
                        <td>{child.precise_category || child.broad_category || "–"}</td>
                        <td className="nowrap">{shortDate(child.as_of_date)}</td>
                        <td />
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
              {!holdingsQ.loading && (holdingsQ.data || []).length === 0 && <tr className="empty-row"><td colSpan={7} className="empty">No holdings for {name} in {yearLabel(year)}.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
