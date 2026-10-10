import { api } from "../api/client";
import { useApp } from "../context";
import type { AccountTransaction, Contribution, TransactionType } from "../types";
import { money, shortDate, TYPE_LABELS } from "./format";

type EditableRow = (Contribution | AccountTransaction) & { transaction_type?: TransactionType };

// Edit and delete for any activity row; contributions and account transactions use different endpoints.
export function useRecordActions() {
  const { openModal, refresh, notify } = useApp();

  function edit(row: EditableRow) {
    if (!row.transaction_type || row.transaction_type === "contribution") openModal({ kind: "contribution", contribution: row as Contribution });
    else openModal({ kind: "transaction", transaction: row as AccountTransaction });
  }

  function remove(row: EditableRow) {
    const type = row.transaction_type || "contribution";
    const path = type === "contribution" ? `/contributions/${row.id}` : `/account-transactions/${row.id}`;
    openModal({
      kind: "confirm",
      title: `Delete this ${TYPE_LABELS[type].toLowerCase()}?`,
      message: `${TYPE_LABELS[type]} on ${shortDate(row.transaction_date)} for ${money(row.amount, row.currency)} in ${row.account_name || "no account"}. This cannot be undone here; the audit log keeps a copy.`,
      confirmLabel: "Delete",
      danger: true,
      onConfirm: async () => {
        await api.delete(path);
        notify("Deleted.");
        refresh();
      },
    });
  }

  return { edit, remove };
}
