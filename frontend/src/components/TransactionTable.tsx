import type { ReactNode } from "react";
import { money, shortDate, TYPE_LABELS } from "../lib/format";
import type { ActivityRecord, TransactionType } from "../types";
import { Icon } from "./Icon";

type Row = ActivityRecord & {
  transaction_type?: TransactionType;
  symbol?: string;
  broad_category?: string;
  precise_category?: string;
  fees?: number;
  fee_currency?: string;
  source_platform_name?: string;
};

const INFLOW = new Set<TransactionType>(["contribution", "dividend_interest", "investment_sell"]);
const OUTFLOW = new Set<TransactionType>(["investment_buy", "withdrawal"]);

export function Pager({ page, pageSize, total, onPageChange }: { page: number; pageSize: number; total: number; onPageChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  return (
    <div className="pager">
      <span className="muted">{total ? `${first} to ${Math.min(page * pageSize, total)} of ${total}` : "No records"}</span>
      <div className="pg">
        <button className="btn btn-s icon-btn sm" type="button" aria-label="Previous page" disabled={page <= 1} onClick={() => onPageChange(page - 1)}><Icon name="left" size={16} /></button>
        <span className="pgn">Page {page} of {pages}</span>
        <button className="btn btn-s icon-btn sm" type="button" aria-label="Next page" disabled={page >= pages} onClick={() => onPageChange(page + 1)}><Icon name="right" size={16} /></button>
      </div>
    </div>
  );
}

interface Props<T extends Row> {
  title: string;
  rows: T[];
  variant?: "all" | "contributions" | "transactions";
  showAccount?: boolean;
  controls?: ReactNode;
  footer?: ReactNode;
  emptyMessage?: string;
  onEdit?: (row: T) => void;
  onDelete?: (row: T) => void;
}

export function TransactionTable<T extends Row>({ title, rows, variant = "all", showAccount = true, controls, footer, emptyMessage, onEdit, onDelete }: Props<T>) {
  const isContributions = variant === "contributions";
  return (
    <section className="card s12">
      <div className="card-h">
        <h2 className="card-t">{title}</h2>
        {controls}
      </div>
      <div className="tbl-wrap">
        <table className="tbl tbl-cards">
          <thead>
            <tr>
              <th>Date</th>
              {!isContributions && <th>Type</th>}
              {showAccount && <th>Account</th>}
              <th>Platform</th>
              {!isContributions && <th>Symbol</th>}
              <th className="r">Amount</th>
              {!isContributions && <th className="r">Fees</th>}
              <th>Notes</th>
              {(onEdit || onDelete) && <th><span className="sr-only">Actions</span></th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const type = row.transaction_type || "contribution";
              const tone = INFLOW.has(type) ? "pos" : OUTFLOW.has(type) ? "" : "dim";
              return (
                <tr key={row.id}>
                  <td data-label="Date" className="nowrap">{shortDate(row.transaction_date)}</td>
                  {!isContributions && (
                    <td data-label="Type"><span className={`type-chip t-${type}`}><Icon name={type} size={14} />{TYPE_LABELS[type]}</span></td>
                  )}
                  {showAccount && <td data-label="Account"><span className="tag">{row.account_name || "–"}</span></td>}
                  <td data-label="Platform">{row.source_platform_name ? `${row.source_platform_name} to ${row.platform_name || "–"}` : row.platform_name || "–"}</td>
                  {!isContributions && (
                    <td data-label="Symbol">
                      <b className="mono">{row.symbol || "–"}</b>
                      {(row.precise_category || row.broad_category) && <div className="muted">{row.precise_category || row.broad_category}</div>}
                    </td>
                  )}
                  <td data-label="Amount" className={`r num money ${tone}`}>{money(row.amount, row.currency)}</td>
                  {!isContributions && <td data-label="Fees" className="r num money">{row.fees ? money(row.fees, row.fee_currency || row.currency) : "–"}</td>}
                  <td data-label="Notes" className="notes">{row.notes || "–"}</td>
                  {(onEdit || onDelete) && (
                    <td data-label="Actions" className="row-actions">
                      {onEdit && <button className="btn btn-g icon-btn sm" type="button" onClick={() => onEdit(row)} aria-label={`Edit ${TYPE_LABELS[type]} on ${row.transaction_date}`}><Icon name="edit" size={16} /></button>}
                      {onDelete && <button className="btn btn-g icon-btn sm danger" type="button" onClick={() => onDelete(row)} aria-label={`Delete ${TYPE_LABELS[type]} on ${row.transaction_date}`}><Icon name="trash" size={16} /></button>}
                    </td>
                  )}
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr className="empty-row">
                <td colSpan={9} className="empty">{emptyMessage || "No records match the current filters."}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {footer}
    </section>
  );
}
