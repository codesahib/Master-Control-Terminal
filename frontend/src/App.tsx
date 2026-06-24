import { ChangeEvent, useEffect, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import { api } from "./api/client";
import { AccountTransactionModal } from "./components/AccountTransactionModal";
import { ContributionModal } from "./components/ContributionModal";
import { DistributionChart } from "./components/DistributionChart";
import { TransactionTable } from "./components/TransactionTable";
import { AccountTransaction, Contribution, ContributionLimitSetting, ContributionRoom, DistributionPoint, Holding, TimeSeriesPoint, Transaction } from "./types";

const YEAR_OPTIONS = [2023, 2024, 2025, 2026];
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
  const currentYear = new Date().getFullYear();
  const [view, setView] = useState<"dashboard" | "account" | "limits">("dashboard");
  const [globalYear, setGlobalYear] = useState<YearFilter>(currentYear);
  const [selectedAccount, setSelectedAccount] = useState<string>("RRSP");
  const [accountYear, setAccountYear] = useState<YearFilter>(currentYear);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [accountContributions, setAccountContributions] = useState<Contribution[]>([]);
  const [accountActivity, setAccountActivity] = useState<AccountTransaction[]>([]);
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
  const [timeline, setTimeline] = useState<TimeSeriesPoint[]>([]);
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

    const responses = await Promise.all(YEAR_OPTIONS.map((optionYear) => api.get<ContributionRoom[]>(`/limits/${optionYear}`)));
    const totals = new Map<string, ContributionRoom>();

    responses.flatMap((response) => response.data).forEach((room) => {
      const current = totals.get(room.account) || {
        account: room.account,
        tax_year: "All",
        total_room: 0,
        used: 0,
        remaining: 0,
      };
      current.total_room += room.total_room;
      current.used += room.used;
      current.remaining += room.remaining;
      totals.set(room.account, current);
    });

    return Array.from(totals.values());
  }

  async function refreshDashboard() {
    const params = yearParams(globalYear);
    const [tx, sector, account, platform, room, series] = await Promise.all([
      api.get<Transaction[]>("/transactions", { params }),
      api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "sector", category_level: categoryLevel, ...params } }),
      api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "account", ...params } }),
      api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "platform", ...params } }),
      fetchContributionRooms(globalYear),
      api.get<TimeSeriesPoint[]>("/analytics/timeseries", { params }),
    ]);

    setTransactions(tx.data);
    setSectorData(sector.data);
    setAccountData(account.data);
    setPlatformData(platform.data);
    setLimits(room);
    setTimeline(series.data);
  }

  async function refreshAccountDetails() {
    const params = { account: selectedAccount, ...yearParams(accountYear) };
    const [contributions, activity, holdings, room] = await Promise.all([
      api.get<Contribution[]>("/contributions", { params }),
      api.get<AccountTransaction[]>("/account-transactions", { params }),
      api.get<Holding[]>("/holdings", { params }),
      fetchContributionRooms(accountYear),
    ]);

    setAccountContributions(contributions.data);
    setAccountActivity(activity.data);
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
    refreshDashboard();
  }, [globalYear, categoryLevel]);

  useEffect(() => {
    if (view === "account") {
      refreshAccountDetails();
    }
  }, [view, selectedAccount, accountYear]);

  const timeSeriesOption = {
    tooltip: { trigger: "axis" },
    legend: { textStyle: { color: "#dbe7ff" } },
    xAxis: { type: "category", data: timeline.map((t) => t.month), axisLabel: { color: "#9aa7cf" } },
    yAxis: { type: "value", axisLabel: { color: "#9aa7cf" } },
    series: [
      { name: "Contributions", type: "line", smooth: true, data: timeline.map((t) => t.contributions) },
      { name: "Investments", type: "line", smooth: true, data: timeline.map((t) => t.investments) },
    ],
  };

  const selectedAccountLimit = accountLimits.find((limit) => limit.account === selectedAccount);

  if (view === "limits") {
    return (
      <div className="app">
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
              <select value={accountYear} onChange={(e) => setAccountYear(e.target.value === "all" ? "all" : Number(e.target.value))}>
                {YEAR_OPTIONS.map((year) => (
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
          />
          <div className="panel table-wrap">
            <h3>{selectedAccount} Holdings Distribution ({yearLabel(accountYear)})</h3>
            <table>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Symbol</th>
                  <th>Broad Category</th>
                  <th>Precise Category</th>
                  <th>Market Value</th>
                  <th>Snapshot Date</th>
                  <th>Holding Date</th>
                </tr>
              </thead>
              <tbody>
                {accountHoldings.map((holding) => (
                  <tr key={holding.id}>
                    <td>{holding.record_type}</td>
                    <td>{holding.symbol || "-"}</td>
                    <td>{holding.broad_category || "-"}</td>
                    <td>{holding.precise_category || "-"}</td>
                    <td>${holding.market_value.toFixed(2)}</td>
                    <td>{holding.snapshot_date}</td>
                    <td>{holding.holding_date || "-"}</td>
                  </tr>
                ))}
                {accountHoldings.length === 0 && (
                  <tr>
                    <td colSpan={7}>No holdings snapshot rows found for this account/year.</td>
                  </tr>
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
              {YEAR_OPTIONS.map((year) => (
                <option key={year} value={year}>{year}</option>
              ))}
              <option value="all">All</option>
            </select>
          </label>
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
          <h3>Contributions vs Investments Trend</h3>
          <ReactECharts option={timeSeriesOption} style={{ height: 300 }} />
        </div>

        <TransactionTable data={transactions} title={`Activity History (${yearLabel(globalYear)})`} />
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
