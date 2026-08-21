import { type ReactNode, useMemo } from "react";
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ActivityRecord } from "../types";

type Variant = "all" | "contributions" | "transactions";

export function TransactionTable<T extends ActivityRecord>({
  data,
  title = "Transaction History",
  onEdit,
  variant = "all",
  showAccount = true,
  controls,
  pagination,
}: {
  data: T[];
  title?: string;
  onEdit?: (transaction: T) => void;
  variant?: Variant;
  showAccount?: boolean;
  controls?: ReactNode;
  pagination?: { page: number; pageSize: number; total: number; onPageChange: (page: number) => void };
}) {
  const isContributionTable = variant === "contributions";
  const isTransactionTable = variant === "transactions";

  const columns = useMemo<ColumnDef<T>[]>(
    () => {
      const baseColumns: ColumnDef<T>[] = [{ header: "Date", accessorKey: "transaction_date" }];

      if (!isContributionTable) {
        baseColumns.push({ header: "Type", accessorKey: "transaction_type" });
      }

      if (showAccount) {
        baseColumns.push({ header: "Account", accessorKey: "account_name" });
      }

      baseColumns.push({ header: "Platform", accessorKey: "platform_name" });

      if (!isContributionTable) {
        baseColumns.push(
          { header: "Symbol", accessorKey: "symbol" },
          { header: "Broad Category", accessorKey: "broad_category" },
          { header: "Precise Category", accessorKey: "precise_category" }
        );
      }

      baseColumns.push({ header: "Amount", accessorKey: "amount" });

      if (isTransactionTable || variant === "all") {
        baseColumns.push({ header: "Fees", accessorKey: "fees" });
      }

      baseColumns.push({ header: "Notes", accessorKey: "notes" });

      if (onEdit) {
        baseColumns.push({
          header: "Actions",
          cell: ({ row }) => (
            <button className="btn btn-secondary table-action" onClick={() => onEdit(row.original)}>
              Edit
            </button>
          ),
        } as ColumnDef<T>);
      }

      return baseColumns;
    },
    [isContributionTable, isTransactionTable, onEdit, showAccount, variant]
  );

  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="panel table-wrap">
      <div className="table-header">
        <h3>{title}</h3>
        {controls}
      </div>
      <table>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {pagination && (
        <div className="pagination">
          <small>Page {pagination.page} of {Math.max(1, Math.ceil(pagination.total / pagination.pageSize))} · {pagination.total} records</small>
          <div>
            <button className="btn btn-secondary table-action" disabled={pagination.page === 1} onClick={() => pagination.onPageChange(pagination.page - 1)}>Previous</button>
            <button className="btn btn-secondary table-action" disabled={pagination.page * pagination.pageSize >= pagination.total} onClick={() => pagination.onPageChange(pagination.page + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  );
}
