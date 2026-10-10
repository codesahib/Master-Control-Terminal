import { AccountTransactionModal } from "./components/AccountTransactionModal";
import { ContributionModal } from "./components/ContributionModal";
import { ConfirmDialog, Dialog } from "./components/Dialog";
import { ManualValuationModal } from "./components/ManualValuationModal";
import { ACCOUNT_NAMES, NewItem, Shell } from "./components/Shell";
import { AppProvider, useApp } from "./context";
import { useRecordActions } from "./lib/records";
import { Account } from "./pages/Account";
import { Activity } from "./pages/Activity";
import { Data } from "./pages/Data";
import { Holdings } from "./pages/Holdings";
import { More } from "./pages/More";
import { Overview } from "./pages/Overview";
import { Room } from "./pages/Room";
import { useRoute } from "./router";

function ModalHost() {
  const { modal, closeModal, openModal, refresh, platforms } = useApp();
  const actions = useRecordActions();
  if (!modal) return null;

  switch (modal.kind) {
    case "contribution":
      return (
        <ContributionModal
          onClose={closeModal}
          onSaved={refresh}
          onDelete={modal.contribution ? () => actions.remove(modal.contribution!) : undefined}
          defaultAccount={modal.account}
          contribution={modal.contribution}
          platforms={platforms}
        />
      );
    case "transaction":
      return (
        <AccountTransactionModal
          onClose={closeModal}
          onSaved={refresh}
          onDelete={modal.transaction ? () => actions.remove(modal.transaction!) : undefined}
          defaultAccount={modal.account}
          defaultTransactionType={modal.type}
          transaction={modal.transaction}
          platforms={platforms}
        />
      );
    case "valuation":
      return <ManualValuationModal row={modal.row} onClose={closeModal} onSaved={refresh} />;
    case "confirm":
      return <ConfirmDialog {...modal} onClose={closeModal} />;
    case "new":
      return (
        <Dialog title="Add" size="sm" onClose={closeModal}>
          <div className="sheet-menu" role="menu" aria-label="Create">
            <NewItem icon="transfer" title="Transaction" sub="Buy, sell, dividend, transfer, FX" tone="c2" onClick={() => openModal({ kind: "transaction", account: modal.account })} />
            <NewItem icon="contribution" title="Contribution" sub="Money into RRSP, TFSA or FHSA" tone="c1" onClick={() => openModal({ kind: "contribution", account: modal.account })} />
            <NewItem icon="withdrawal" title="Withdrawal" sub="Cash taken out of an account" tone="c5" onClick={() => openModal({ kind: "transaction", account: modal.account, type: "withdrawal" })} />
          </div>
        </Dialog>
      );
  }
}

function Routes() {
  const { path, parts } = useRoute();
  if (parts[0] === "accounts" && parts[1] && ACCOUNT_NAMES.includes(parts[1].toUpperCase())) {
    const name = parts[1].toUpperCase();
    return <Shell title={name}><Account name={name} /></Shell>;
  }
  switch (path) {
    case "/holdings":
      return <Shell title="Holdings"><Holdings /></Shell>;
    case "/activity":
      return <Shell title="Activity"><Activity /></Shell>;
    case "/room":
      return <Shell title="Contribution room"><Room /></Shell>;
    case "/data":
      return <Shell title="Import and export"><Data /></Shell>;
    case "/more":
      return <Shell title="More"><More /></Shell>;
    default:
      return <Shell title="Overview"><Overview /></Shell>;
  }
}

export default function App() {
  return (
    <AppProvider>
      <Routes />
      <ModalHost />
    </AppProvider>
  );
}
