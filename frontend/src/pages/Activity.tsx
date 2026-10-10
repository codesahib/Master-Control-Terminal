import { useEffect, useState } from "react";
import { Icon } from "../components/Icon";
import { ACCOUNT_NAMES } from "../components/Shell";
import { Pager, TransactionTable } from "../components/TransactionTable";
import { useApp, yearLabel, yearParams } from "../context";
import { errorMessage, TYPE_LABELS } from "../lib/format";
import { useRecordActions } from "../lib/records";
import { useApi } from "../lib/useApi";
import type { PaginatedTransactions, TransactionType } from "../types";

const PAGE_SIZE = 20;

export function ActivityFilters({ type, onType, platform, onPlatform, direction, onDirection, types }: {
  type: string;
  onType: (value: TransactionType | "") => void;
  platform: string;
  onPlatform: (value: string) => void;
  direction: "asc" | "desc";
  onDirection: (value: "asc" | "desc") => void;
  types: TransactionType[];
}) {
  const { platforms } = useApp();
  return (
    <div className="row filters">
      <label className="select-wrap">
        <span className="sr-only">Type</span>
        <select className="select" value={type} onChange={(event) => onType(event.target.value as TransactionType | "")}>
          <option value="">All types</option>
          {types.map((value) => <option key={value} value={value}>{TYPE_LABELS[value]}</option>)}
        </select>
        <Icon name="chevron" size={16} />
      </label>
      <label className="select-wrap">
        <span className="sr-only">Platform</span>
        <select className="select" value={platform} onChange={(event) => onPlatform(event.target.value)}>
          <option value="">All platforms</option>
          {platforms.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
        <Icon name="chevron" size={16} />
      </label>
      <label className="select-wrap">
        <span className="sr-only">Sort</span>
        <select className="select" value={direction} onChange={(event) => onDirection(event.target.value as "asc" | "desc")}>
          <option value="desc">Newest first</option>
          <option value="asc">Oldest first</option>
        </select>
        <Icon name="chevron" size={16} />
      </label>
    </div>
  );
}

export function Activity() {
  const { year } = useApp();
  const actions = useRecordActions();
  const [account, setAccount] = useState("");
  const [type, setType] = useState<TransactionType | "">("");
  const [platform, setPlatform] = useState("");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [year]);
  const query = useApi<PaginatedTransactions>("/transactions", {
    page,
    page_size: PAGE_SIZE,
    sort_direction: direction,
    ...(account ? { account } : {}),
    ...(type ? { transaction_type: type } : {}),
    ...(platform ? { platform } : {}),
    ...yearParams(year),
  });
  const pageSize = query.data?.page_size || PAGE_SIZE;
  const reset = <T,>(setter: (value: T) => void) => (value: T) => { setter(value); setPage(1); };

  return (
    <div className="grid">
      <div className="seg s12 seg-scroll" role="group" aria-label="Account">
        {["", ...ACCOUNT_NAMES].map((value) => (
          <button key={value || "all"} type="button" className={account === value ? "on" : ""} aria-pressed={account === value} onClick={() => reset(setAccount)(value)}>{value || "All accounts"}</button>
        ))}
      </div>
      {query.error && <p className="form-error s12" role="alert">{errorMessage(query.error, "Activity failed to load.")}</p>}
      <TransactionTable
        title={`Activity · ${yearLabel(year)}`}
        rows={query.data?.items || []}
        onEdit={actions.edit}
        onDelete={actions.remove}
        controls={<ActivityFilters type={type} onType={reset(setType)} platform={platform} onPlatform={reset(setPlatform)} direction={direction} onDirection={reset(setDirection)} types={Object.keys(TYPE_LABELS) as TransactionType[]} />}
        footer={<Pager page={page} pageSize={pageSize} total={query.data?.total || 0} onPageChange={setPage} />}
        emptyMessage={query.loading ? "Loading…" : "No activity matches these filters."}
      />
    </div>
  );
}
