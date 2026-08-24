import { ChangeEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";
import ReactECharts from "echarts-for-react";
import { api, isApiLoading, subscribeToApiLoading } from "./api/client";
import { AccountTransactionModal } from "./components/AccountTransactionModal";
import { ContributionModal } from "./components/ContributionModal";
import { DistributionChart } from "./components/DistributionChart";
import { TransactionTable } from "./components/TransactionTable";
import { AccountTransaction, Contribution, ContributionLimitSetting, ContributionRoom, DistributionPoint, Holding, PaginatedAccountTransactions, PaginatedTransactions, Transaction, TransactionType } from "./types";

const ACCOUNT_NAMES = ["RRSP", "TFSA", "FHSA"];
type YearFilter = number | "all";
type CategoryLevel = "broad" | "precise";
type ActiveModal = "contribution" | "account-transaction" | null;

function yearParams(year: YearFilter) {
  return year === "all" ? {} : { year };
}

function yearLabel(year: YearFilter) {
  return year === "all" ? "All" : String(year);
}

function App() {
  const isLoading = useSyncExternalStore(subscribeToApiLoading, isApiLoading);
  const currentYear = new Date().getFullYear();
  const [view, setView] = useState<"dashboard" | "account" | "limits">("dashboard");
  const [globalYear, setGlobalYear] = useState<YearFilter>(currentYear);
  const [globalCurrency, setGlobalCurrency] = useState("CAD");
  const [selectedAccount, setSelectedAccount] = useState<string>("RRSP");
  const [accountYear, setAccountYear] = useState<YearFilter>(currentYear);
  const [years, setYears] = useState<number[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyType, setHistoryType] = useState<TransactionType | "">("");
  const [historyPlatform, setHistoryPlatform] = useState("");
  const [historySortDirection, setHistorySortDirection] = useState<"asc" | "desc">("desc");
  const [accountContributions, setAccountContributions] = useState<Contribution[]>([]);
  const [accountActivity, setAccountActivity] = useState<AccountTransaction[]>([]);
  const [accountActivityPage, setAccountActivityPage] = useState(1);
  const [accountActivityTotal, setAccountActivityTotal] = useState(0);
  const [accountActivityType, setAccountActivityType] = useState<TransactionType | "">("");
  const [accountActivityPlatform, setAccountActivityPlatform] = useState("");
  const [accountActivitySortDirection, setAccountActivitySortDirection] = useState<"asc" | "desc">("desc");
  const [accountHoldings, setAccountHoldings] = useState<Holding[]>([]);
  const [editingContribution, setEditingContribution] = useState<Contribution | undefined>();
  const [editingAccountTransaction, setEditingAccountTransaction] = useState<AccountTransaction | undefined>();
  const [modalAccount, setModalAccount] = useState<string | undefined>();
  const [activeModal, setActiveModal] = useState<ActiveModal>(null);
  const [sectorData, setSectorData] = useState<DistributionPoint[]>([]);
  const [categoryLevel, setCategoryLevel] = useState<CategoryLevel>("precise");
  const [accountData, setAccountData] = useState<DistributionPoint[]>([]);
  const [platformData, setPlatformData] = useState<DistributionPoint[]>([]);
  const [limits, setLimits] = useState<ContributionRoom[]>([]);
  const [accountLimits, setAccountLimits] = useState<ContributionRoom[]>([]);
  const [contributionLimitSettings, setContributionLimitSettings] = useState<ContributionLimitSetting[]>([]);
  const [savingLimitKey, setSavingLimitKey] = useState<string | undefined>();
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [backupMessage, setBackupMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function fetchContributionRooms(year: YearFilter) {
    if (year !== "all") {
      const response = await api.get<ContributionRoom[]>(`/limits/${year}`);
      return response.data;
    }

    const response = await api.get<ContributionRoom[]>("/limits");
    return response.data;
  }

  async function refreshDashboard() {
    const params = yearParams(globalYear);
    const historyParams = {
      ...params,
      page: historyPage,
      sort_direction: historySortDirection,
      ...(historyType ? { transaction_type: historyType } : {}),
      ...(historyPlatform ? { platform: historyPlatform } : {}),
    };
    const [tx, sector, account, platform, room] = await Promise.all([
      api.get<PaginatedTransactions>("/transactions", { params: historyParams }),
      api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "sector", category_level: categoryLevel, currency: globalCurrency, ...params } }),
      api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "account", currency: globalCurrency, ...params } }),
      api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "platform", currency: globalCurrency, ...params } }),
      fetchContributionRooms(globalYear),
    ]);

    setTransactions(tx.data.items);
    setHistoryTotal(tx.data.total);
    setSectorData(sector.data);
    setAccountData(account.data);
    setPlatformData(platform.data);
    setLimits(room);
  }

  async function refreshAccountDetails() {
    const params = { account: selectedAccount, ...yearParams(accountYear) };
    const activityParams = {
      ...params,
      page: accountActivityPage,
      sort_direction: accountActivitySortDirection,
      ...(accountActivityType ? { transaction_type: accountActivityType } : {}),
      ...(accountActivityPlatform ? { platform: accountActivityPlatform } : {}),
    };
    const [contributions, activity, holdings, room] = await Promise.all([
      api.get<Contribution[]>("/contributions", { params }),
      api.get<PaginatedAccountTransactions>("/account-transactions", { params: activityParams }),
      api.get<Holding[]>("/holdings", { params }),
      fetchContributionRooms(accountYear),
    ]);

    setAccountContributions(contributions.data);
    setAccountActivity(activity.data.items);
    setAccountActivityTotal(activity.data.total);
    setAccountHoldings(holdings.data);
    setAccountLimits(room);
  }

  async function refreshContributionLimitSettings() {
    const response = await api.get<ContributionLimitSetting[]>("/contribution-limits");
    setContributionLimitSettings(response.data.filter((row) => row.account === selectedAccount));
  }

  function updateContributionLimitDraft(row: ContributionLimitSetting, value: string) {
    const numericValue = Number(value);
    setContributionLimitSettings((current) =>
      current.map((item) =>
        item.account === row.account && item.tax_year === row.tax_year
          ? { ...item, new_room: Number.isNaN(numericValue) ? 0 : numericValue }
          : item
      )
    );
  }

  async function saveContributionLimit(row: ContributionLimitSetting) {
    const key = `${row.account}:${row.tax_year}`;
    setSavingLimitKey(key);
    await api.put(`/contribution-limits/${row.account}/${row.tax_year}`, {
      new_room: row.new_room,
    });
    setSavingLimitKey(undefined);
    await Promise.all([refreshContributionLimitSettings(), refreshDashboard(), refreshAccountDetails()]);
  }

  function openAccount(accountName: string) {
    setSelectedAccount(accountName);
    setAccountYear(globalYear);
    setAccountActivityPage(1);
    setView("account");
  }

  function openNewContribution(accountName?: string) {
    setEditingContribution(undefined);
    setEditingAccountTransaction(undefined);
    setModalAccount(accountName);
    setActiveModal("contribution");
  }

  function openNewAccountTransaction(accountName?: string) {
    setEditingContribution(undefined);
    setEditingAccountTransaction(undefined);
    setModalAccount(accountName);
    setActiveModal("account-transaction");
  }

  function openEditContribution(contribution: Contribution) {
    setEditingContribution(contribution);
    setEditingAccountTransaction(undefined);
    setModalAccount(contribution.account_name);
    setActiveModal("contribution");
  }

  function openEditAccountTransaction(transaction: AccountTransaction) {
    setEditingContribution(undefined);
    setEditingAccountTransaction(transaction);
    setModalAccount(transaction.account_name);
    setActiveModal("account-transaction");
  }

  async function refreshAfterSave() {
    await Promise.all([refreshDashboard(), refreshAccountDetails()]);
  }

  async function openContributionLimits() {
    await refreshContributionLimitSettings();
    setView("limits");
  }

  async function exportData() {
    try {
      setIsExporting(true);
      setBackupError(null);
      setBackupMessage(null);
      const response = await api.get<Blob>("/export", { responseType: "blob" });
      const header = response.headers["content-disposition"] as string | undefined;
      const filenameMatch = header?.match(/filename=\"?([^"]+)\"?/i);
      const filename = filenameMatch?.[1] || `master-control-terminal-export-${new Date().toISOString()}.json`;
      const url = window.URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setBackupMessage("Backup exported successfully.");
    } catch (error) {
      console.error(error);
      setBackupError("Export failed. Please try again.");
    } finally {
      setIsExporting(false);
    }
  }

  function openImportPicker() {
    setBackupError(null);
    setBackupMessage(null);
    fileInputRef.current?.click();
  }

  async function importBackup(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }

    const confirmed = window.confirm(
      "Importing a backup will replace the current app data. Continue?"
    );
    if (!confirmed) {
      return;
    }

    try {
      setIsImporting(true);
      setBackupError(null);
      setBackupMessage(null);
      const formData = new FormData();
      formData.append("file", file);
      await api.post("/import-backup", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await Promise.all([refreshDashboard(), refreshAccountDetails()]);
      if (view === "limits") {
        await refreshContributionLimitSettings();
      }
      setBackupMessage("Backup restored successfully.");
    } catch (error: any) {
      console.error(error);
      setBackupError(error?.response?.data?.detail?.toString() || "Import failed. Please try again.");
    } finally {
      setIsImporting(false);
    }
  }

  useEffect(() => {
    api.get<number[]>("/years").then((response) => setYears(response.data));
  }, []);

  useEffect(() => {
    refreshDashboard();
  }, [globalYear, globalCurrency, categoryLevel, historyPage, historyType, historyPlatform, historySortDirection, years]);

  useEffect(() => {
    if (view === "account") {
      refreshAccountDetails();
    }
  }, [view, selectedAccount, accountYear, accountActivityPage, accountActivityType, accountActivityPlatform, accountActivitySortDirection]);

  const balanceOption = {
    tooltip: { trigger: "axis" },
    legend: { textStyle: { color: "#dbe7ff" } },
    xAxis: { type: "category", data: ACCOUNT_NAMES, axisLabel: { color: "#9aa7cf" } },
    yAxis: { type: "value", axisLabel: { color: "#9aa7cf" } },
    series: [
      { name: "Used", type: "bar", stack: "balance", data: ACCOUNT_NAMES.map((name) => limits.find((limit) => limit.account === name)?.used ?? 0) },
      { name: "Remaining", type: "bar", stack: "balance", data: ACCOUNT_NAMES.map((name) => limits.find((limit) => limit.account === name)?.remaining ?? 0) },
    ],
  };

  const selectedAccountLimit = accountLimits.find((limit) => limit.account === selectedAccount);
  const loadingOverlay = isLoading && (
    <div className="loading-overlay" role="status" aria-live="polite" aria-label="Loading">
      <span className="spinner" aria-hidden="true" />
      Loading…
    </div>
  );

  if (view === "limits") {
    return (
      <div className="app">
        {loadingOverlay}
        <div className="header">
          <div>
            <button className="btn btn-secondary" onClick={() => setView("account")}>Back</button>
            <h1>{selectedAccount} Contribution Limits</h1>
            <small>New room is editable; unused and total room are calculated</small>
          </div>
        </div>
        {backupError && <p className="banner-error">{backupError}</p>}
        {backupMessage && <p className="banner-success">{backupMessage}</p>}

        <div className="panel table-wrap">
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Year</th>
                <th>Unused Room</th>
                <th>New Room</th>
                <th>Total Room</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {contributionLimitSettings.map((row) => {
                const key = `${row.account}:${row.tax_year}`;
                return (
                  <tr key={key}>
                    <td>{row.account}</td>
                    <td>{row.tax_year}</td>
                    <td>${row.unused_room.toFixed(2)}</td>
                    <td>
                      <input
                        className="table-input"
                        type="number"
                        step="0.01"
                        value={row.new_room}
                        onChange={(e) => updateContributionLimitDraft(row, e.target.value)}
                      />
                    </td>
                    <td>${row.total_room.toFixed(2)}</td>
                    <td>
                      <button className="btn table-action" onClick={() => saveContributionLimit(row)} disabled={savingLimitKey === key}>
                        {savingLimitKey === key ? "Saving" : "Save"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (view === "account") {
    return (
      <div className="app">
        {loadingOverlay}
        <div className="header">
          <div>
            <button className="btn btn-secondary" onClick={() => setView("dashboard")}>Back</button>
            <h1>{selectedAccount}</h1>
            <small>Contribution history and in-account activity</small>
          </div>
          <div className="top-controls">
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              onChange={importBackup}
              hidden
            />
            <label>
              Year{" "}
              <select value={accountYear} onChange={(e) => { setAccountYear(e.target.value === "all" ? "all" : Number(e.target.value)); setAccountActivityPage(1); }}>
                {years.map((year) => (
                  <option key={year} value={year}>{year}</option>
                ))}
                <option value="all">All</option>
              </select>
            </label>
            <button className="btn btn-secondary" onClick={openContributionLimits}>Contribution Limits</button>
            <button className="btn btn-secondary" onClick={() => openNewContribution(selectedAccount)}>New Contribution</button>
            <button className="btn" onClick={() => openNewAccountTransaction(selectedAccount)}>New Account Transaction</button>
          </div>
        </div>
        {backupError && <p className="banner-error">{backupError}</p>}
        {backupMessage && <p className="banner-success">{backupMessage}</p>}

        <div className="grid">
          <div className="panel kpi static-card">
            <h3>{selectedAccount} Room ({yearLabel(accountYear)})</h3>
            <p>Total: ${selectedAccountLimit ? selectedAccountLimit.total_room.toFixed(2) : "0.00"}</p>
            <p>Used: ${selectedAccountLimit ? selectedAccountLimit.used.toFixed(2) : "0.00"}</p>
            <p>Remaining: ${selectedAccountLimit ? selectedAccountLimit.remaining.toFixed(2) : "0.00"}</p>
          </div>
          <TransactionTable
            data={accountContributions}
            title={`${selectedAccount} Contributions (${yearLabel(accountYear)})`}
            onEdit={openEditContribution}
            variant="contributions"
            showAccount={false}
          />
          <TransactionTable
            data={accountActivity}
            title={`${selectedAccount} Account Transactions (${yearLabel(accountYear)})`}
            onEdit={openEditAccountTransaction}
            variant="transactions"
            showAccount={false}
            controls={
              <div className="table-controls">
                <label>Sort <select value={accountActivitySortDirection} onChange={(e) => { setAccountActivitySortDirection(e.target.value as "asc" | "desc"); setAccountActivityPage(1); }}><option value="desc">Date: newest</option><option value="asc">Date: oldest</option></select></label>
                <label>Type <select value={accountActivityType} onChange={(e) => { setAccountActivityType(e.target.value as TransactionType | ""); setAccountActivityPage(1); }}><option value="">All</option>{["investment_buy", "investment_sell", "transfer", "dividend_interest", "dividend_reinvestment", "quantity_adjustment", "currency_exchange"].map((type) => <option key={type} value={type}>{type.replace(/_/g, " ")}</option>)}</select></label>
                <label>Platform <input value={accountActivityPlatform} placeholder="All" onChange={(e) => { setAccountActivityPlatform(e.target.value); setAccountActivityPage(1); }} /></label>
              </div>
            }
            pagination={{ page: accountActivityPage, pageSize: 10, total: accountActivityTotal, onPageChange: setAccountActivityPage }}
          />
          <div className="panel table-wrap">
            <h3>{selectedAccount} Derived Holdings ({yearLabel(accountYear)})</h3>
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Symbol</th>
                  <th>Broad Category</th>
                  <th>Precise Category</th>
                  <th>Quantity</th>
                  <th>Book Value</th>
                  <th>Currency</th>
                  <th>As Of</th>
                </tr>
              </thead>
              <tbody>
                {accountHoldings.map((holding) => (
                  <tr key={holding.id}>
                    <td>{holding.record_type}</td>
                    <td>{holding.symbol}</td>
                    <td>{holding.broad_category || "-"}</td>
                    <td>{holding.precise_category || "-"}</td>
                    <td>{holding.quantity ?? "-"}</td>
                    <td>{holding.book_value.toFixed(2)}</td>
                    <td>{holding.currency}</td>
                    <td>{holding.as_of_date}</td>
                  </tr>
                ))}
                {accountHoldings.length === 0 && (
                  <tr><td colSpan={8}>No transactions recorded for this account/year.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {activeModal === "contribution" && (
          <ContributionModal
            onClose={() => setActiveModal(null)}
            onSaved={refreshAfterSave}
            defaultAccount={modalAccount || selectedAccount}
            contribution={editingContribution}
          />
        )}

        {activeModal === "account-transaction" && (
          <AccountTransactionModal
            onClose={() => setActiveModal(null)}
            onSaved={refreshAfterSave}
            defaultAccount={modalAccount || selectedAccount}
            transaction={editingAccountTransaction}
          />
        )}
      </div>
    );
  }

  return (
    <div className="app">
      {loadingOverlay}
      <div className="header">
        <div>
          <h1>Master Terminal</h1>
          <small>Finance console for RRSP, TFSA, FHSA</small>
        </div>
        <div className="top-controls">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            onChange={importBackup}
            hidden
          />
          <label>
            Year{" "}
            <select value={globalYear} onChange={(e) => setGlobalYear(e.target.value === "all" ? "all" : Number(e.target.value))}>
              {years.map((year) => (
                <option key={year} value={year}>{year}</option>
              ))}
              <option value="all">All</option>
            </select>
          </label>
          <label>Analytics Currency <select value={globalCurrency} onChange={(e) => setGlobalCurrency(e.target.value)}><option>CAD</option><option>USD</option></select></label>
          <button className="btn btn-secondary" onClick={openImportPicker} disabled={isImporting}>
            {isImporting ? "Importing..." : "Import Backup"}
          </button>
          <button className="btn btn-secondary" onClick={exportData} disabled={isExporting}>
            {isExporting ? "Exporting..." : "Export Data"}
          </button>
          <button className="btn btn-secondary" onClick={() => openNewContribution()}>New Contribution</button>
          <button className="btn" onClick={() => openNewAccountTransaction()}>New Account Transaction</button>
        </div>
      </div>
      {backupError && <p className="banner-error">{backupError}</p>}
      {backupMessage && <p className="banner-success">{backupMessage}</p>}

      <div className="grid">
        {ACCOUNT_NAMES.map((accountName) => {
          const limit = limits.find((item) => item.account === accountName);
          return (
            <button className="panel kpi account-card" key={accountName} onClick={() => openAccount(accountName)}>
              <h3>{accountName} Room ({yearLabel(globalYear)})</h3>
              <small>Open account details</small>
              <p>Total: ${limit ? limit.total_room.toFixed(2) : "0.00"}</p>
              <p>Used: ${limit ? limit.used.toFixed(2) : "0.00"}</p>
              <p>Remaining: ${limit ? limit.remaining.toFixed(2) : "0.00"}</p>
            </button>
          );
        })}

        <DistributionChart
          title="Sector Distribution"
          data={sectorData}
          actions={
            <div className="segmented-control" aria-label="Category level">
              <button
                className={categoryLevel === "broad" ? "active" : ""}
                onClick={() => setCategoryLevel("broad")}
                type="button"
              >
                Broad
              </button>
              <button
                className={categoryLevel === "precise" ? "active" : ""}
                onClick={() => setCategoryLevel("precise")}
                type="button"
              >
                Precise
              </button>
            </div>
          }
        />
        <DistributionChart title="Account Distribution" data={accountData} />
        <DistributionChart title="Platform Distribution" data={platformData} />

        <div className="panel chart" style={{ gridColumn: "span 12" }}>
          <h3>Used vs Remaining Balance</h3>
          <ReactECharts option={balanceOption} style={{ height: 300 }} />
        </div>

        <TransactionTable
          data={transactions}
          title={`Activity History (${yearLabel(globalYear)})`}
          controls={
            <div className="table-controls">
              <label>Sort <select value={historySortDirection} onChange={(e) => { setHistorySortDirection(e.target.value as "asc" | "desc"); setHistoryPage(1); }}><option value="desc">Date: newest</option><option value="asc">Date: oldest</option></select></label>
              <label>Type <select value={historyType} onChange={(e) => { setHistoryType(e.target.value as TransactionType | ""); setHistoryPage(1); }}><option value="">All</option>{["contribution", "investment_buy", "investment_sell", "transfer", "dividend_interest", "dividend_reinvestment", "quantity_adjustment", "currency_exchange"].map((type) => <option key={type} value={type}>{type.replace(/_/g, " ")}</option>)}</select></label>
              <label>Platform <input value={historyPlatform} placeholder="All" onChange={(e) => { setHistoryPlatform(e.target.value); setHistoryPage(1); }} /></label>
            </div>
          }
          pagination={{ page: historyPage, pageSize: 10, total: historyTotal, onPageChange: setHistoryPage }}
        />
      </div>

      {activeModal === "contribution" && (
        <ContributionModal
          onClose={() => setActiveModal(null)}
          onSaved={refreshAfterSave}
          defaultAccount={modalAccount}
          contribution={editingContribution}
        />
      )}

      {activeModal === "account-transaction" && (
        <AccountTransactionModal
          onClose={() => setActiveModal(null)}
          onSaved={refreshAfterSave}
          defaultAccount={modalAccount}
          transaction={editingAccountTransaction}
        />
      )}
    </div>
  );
}

export default App;
