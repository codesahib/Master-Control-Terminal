import { ChangeEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";
import ReactECharts from "echarts-for-react";
import { api, isApiLoading, subscribeToApiLoading } from "./api/client";
import { AccountTransactionModal } from "./components/AccountTransactionModal";
import { ContributionModal } from "./components/ContributionModal";
import { DistributionChart } from "./components/DistributionChart";
import { ManualValuationModal } from "./components/ManualValuationModal";
import { TransactionTable } from "./components/TransactionTable";
import { AccountPLSummary, AccountTransaction, Contribution, ContributionLimitSetting, ContributionRoom, DistributionPoint, Holding, PaginatedAccountTransactions, PaginatedPortfolioPL, PaginatedTransactions, PortfolioPLRow, PortfolioSummary, Transaction, TransactionType } from "./types";

const ACCOUNT_NAMES = ["RRSP", "TFSA", "FHSA"];
const PRICE_STATUSES = ["ok", "stale", "missing", "missing_quantity", "currency_mismatch", "cash"];
type YearFilter = number | "all";
type CategoryLevel = "broad" | "precise";
type ActiveModal = "contribution" | "account-transaction" | "manual-valuation" | null;

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
  const [platforms, setPlatforms] = useState<string[]>([]);
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
  const [expandedHoldings, setExpandedHoldings] = useState<string[]>([]);
  const [editingContribution, setEditingContribution] = useState<Contribution | undefined>();
  const [editingAccountTransaction, setEditingAccountTransaction] = useState<AccountTransaction | undefined>();
  const [manualValuationRow, setManualValuationRow] = useState<PortfolioPLRow | undefined>();
  const [modalAccount, setModalAccount] = useState<string | undefined>();
  const [activeModal, setActiveModal] = useState<ActiveModal>(null);
  const [sectorData, setSectorData] = useState<DistributionPoint[]>([]);
  const [categoryLevel, setCategoryLevel] = useState<CategoryLevel>("precise");
  const [accountData, setAccountData] = useState<DistributionPoint[]>([]);
  const [platformData, setPlatformData] = useState<DistributionPoint[]>([]);
  const [portfolioPL, setPortfolioPL] = useState<PortfolioPLRow[]>([]);
  const [investableCash, setInvestableCash] = useState<PortfolioPLRow[]>([]);
  const [allocationRows, setAllocationRows] = useState<DistributionPoint[]>([]);
  const [accountPLRows, setAccountPLRows] = useState<AccountPLSummary[]>([]);
  const [portfolioPLPage, setPortfolioPLPage] = useState(1);
  const [portfolioPLTotal, setPortfolioPLTotal] = useState(0);
  const [portfolioPLAccount, setPortfolioPLAccount] = useState("");
  const [portfolioPLPlatform, setPortfolioPLPlatform] = useState("");
  const [portfolioPLStatus, setPortfolioPLStatus] = useState("ok");
  const [portfolioPLSortDirection, setPortfolioPLSortDirection] = useState<"asc" | "desc">("desc");
  const [expandedPortfolioPL, setExpandedPortfolioPL] = useState<string[]>([]);
  const [limits, setLimits] = useState<ContributionRoom[]>([]);
  const [accountLimits, setAccountLimits] = useState<ContributionRoom[]>([]);
  const [contributionLimitSettings, setContributionLimitSettings] = useState<ContributionLimitSetting[]>([]);
  const [savingLimitKey, setSavingLimitKey] = useState<string | undefined>();
  const [isExporting, setIsExporting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isRefreshingPrices, setIsRefreshingPrices] = useState(false);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [backupMessage, setBackupMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
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
    try {
      setLoadError(null);
      const params = yearParams(globalYear);
      const historyParams = {
        ...params,
        page: historyPage,
        sort_direction: historySortDirection,
        ...(historyType ? { transaction_type: historyType } : {}),
        ...(historyPlatform ? { platform: historyPlatform } : {}),
      };
      const plParams = {
        ...params,
        page: portfolioPLPage,
        page_size: 10,
        sort_direction: portfolioPLSortDirection,
        ...(portfolioPLAccount ? { account: portfolioPLAccount } : {}),
        ...(portfolioPLPlatform ? { platform: portfolioPLPlatform } : {}),
        ...(portfolioPLStatus ? { status: portfolioPLStatus } : {}),
      };
      const [tx, sector, account, platform, pl, summary, room] = await Promise.all([
        api.get<PaginatedTransactions>("/transactions", { params: historyParams }),
        api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "sector", category_level: categoryLevel, currency: globalCurrency, ...params } }),
        api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "account", currency: globalCurrency, ...params } }),
        api.get<DistributionPoint[]>("/analytics/distribution", { params: { group_by: "platform", currency: globalCurrency, ...params } }),
        api.get<PaginatedPortfolioPL>("/portfolio/pl", { params: plParams }),
        api.get<PortfolioSummary>("/portfolio/summary", { params }),
        fetchContributionRooms(globalYear),
      ]);

      setTransactions(tx.data.items);
      setHistoryTotal(tx.data.total);
      setSectorData(sector.data);
      setAccountData(account.data);
      setPlatformData(platform.data);
      setPortfolioPL(pl.data.items);
      setPortfolioPLTotal(pl.data.total);
      setInvestableCash(summary.data.investable_cash);
      setAllocationRows(summary.data.allocation);
      setAccountPLRows(summary.data.account_pl);
      setLimits(room);
    } catch (error) {
      console.error(error);
      setLoadError("Dashboard data failed. Check API and filters.");
    }
  }

  async function refreshAccountDetails() {
    try {
      setLoadError(null);
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
    } catch (error) {
      console.error(error);
      setLoadError("Account data failed. Check API and filters.");
    }
  }

  async function refreshContributionLimitSettings() {
    try {
      setLoadError(null);
      const response = await api.get<ContributionLimitSetting[]>("/contribution-limits");
      setContributionLimitSettings(response.data.filter((row) => row.account === selectedAccount));
    } catch (error) {
      console.error(error);
      setLoadError("Contribution limits failed. Check API connection.");
    }
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
    setLoadError(null);
    try {
      await api.put(`/contribution-limits/${row.account}/${row.tax_year}`, {
        new_room: row.new_room,
      });
      await Promise.all([refreshContributionLimitSettings(), refreshDashboard(), refreshAccountDetails()]);
    } catch (error) {
      console.error(error);
      setLoadError("Contribution limit failed to save.");
    } finally {
      setSavingLimitKey(undefined);
    }
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

  function openManualValuation(row: PortfolioPLRow) {
    setEditingContribution(undefined);
    setEditingAccountTransaction(undefined);
    setManualValuationRow(row);
    setActiveModal("manual-valuation");
  }

  function toggleExpanded(id: string, setExpanded: (updater: (current: string[]) => string[]) => void) {
    setExpanded((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  async function refreshAfterSave() {
    await Promise.all([refreshDashboard(), refreshAccountDetails()]);
  }

  async function refreshMarketPrices() {
    try {
      setIsRefreshingPrices(true);
      setLoadError(null);
      await api.post("/market-prices/refresh");
      await refreshDashboard();
    } catch (error) {
      console.error(error);
      setLoadError("Price refresh failed. Try again later.");
    } finally {
      setIsRefreshingPrices(false);
    }
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
    Promise.all([api.get<number[]>("/years"), api.get<string[]>("/platforms")])
      .then(([yearResponse, platformResponse]) => {
        setYears(yearResponse.data);
        setPlatforms(platformResponse.data);
      })
      .catch((error) => {
        console.error(error);
        setLoadError("Startup data failed. Check API connection.");
      });
  }, []);

  useEffect(() => {
    refreshDashboard();
  }, [
    globalYear,
    globalCurrency,
    categoryLevel,
    historyPage,
    historyType,
    historyPlatform,
    historySortDirection,
    portfolioPLPage,
    portfolioPLAccount,
    portfolioPLPlatform,
    portfolioPLStatus,
    portfolioPLSortDirection,
    years,
  ]);

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
  const totalPortfolioValue = allocationRows.reduce((sum, row) => sum + row.value, 0);
  const loadingOverlay = isLoading && (
    <div className="loading-overlay" role="status" aria-live="polite" aria-label="Loading">
      <span className="spinner" aria-hidden="true" />
      Loading…
    </div>
  );
  function renderPLStatus(row: PortfolioPLRow) {
    return (
      <>
        {row.price_status}
        {row.manual_valuation_date && <><br /><small>Manual value updated {row.manual_valuation_date}</small></>}
        {row.record_type === "holding" && row.quantity == null && (
          <><br /><button className="btn btn-secondary table-action" type="button" onClick={() => openManualValuation(row)}>Update value</button></>
        )}
      </>
    );
  }

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
        {loadError && <p className="banner-error">{loadError}</p>}
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
                    <td data-label="Account">{row.account}</td>
                    <td data-label="Year">{row.tax_year}</td>
                    <td data-label="Unused Room">${row.unused_room.toFixed(2)}</td>
                    <td data-label="New Room">
                      <input
                        className="table-input"
                        type="number"
                        min="0"
                        step="0.01"
                        inputMode="decimal"
                        value={row.new_room}
                        onChange={(e) => updateContributionLimitDraft(row, e.target.value)}
                      />
                    </td>
                    <td data-label="Total Room">${row.total_room.toFixed(2)}</td>
                    <td data-label="Actions">
                      <button className="btn table-action" onClick={() => saveContributionLimit(row)} disabled={savingLimitKey === key}>
                        {savingLimitKey === key ? "Saving" : "Save"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {contributionLimitSettings.length === 0 && (
                <tr><td className="empty-state" colSpan={6}>No contribution limit settings found for this account.</td></tr>
              )}
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
        {loadError && <p className="banner-error">{loadError}</p>}
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
            emptyMessage="No contributions recorded for this account/year."
          />
          <TransactionTable
            data={accountActivity}
            title={`${selectedAccount} Account Transactions (${yearLabel(accountYear)})`}
            onEdit={openEditAccountTransaction}
            variant="transactions"
            showAccount={false}
            emptyMessage="No account transactions match the current filters."
            controls={
              <div className="table-controls">
                <label>Sort <select value={accountActivitySortDirection} onChange={(e) => { setAccountActivitySortDirection(e.target.value as "asc" | "desc"); setAccountActivityPage(1); }}><option value="desc">Date: newest</option><option value="asc">Date: oldest</option></select></label>
                <label>Type <select value={accountActivityType} onChange={(e) => { setAccountActivityType(e.target.value as TransactionType | ""); setAccountActivityPage(1); }}><option value="">All</option>{["investment_buy", "investment_sell", "transfer", "dividend_interest", "dividend_reinvestment", "quantity_adjustment", "currency_exchange"].map((type) => <option key={type} value={type}>{type.replace(/_/g, " ")}</option>)}</select></label>
                <label>Platform <select value={accountActivityPlatform} onChange={(e) => { setAccountActivityPlatform(e.target.value); setAccountActivityPage(1); }}><option value="">All</option>{platforms.map((platform) => <option key={platform} value={platform}>{platform}</option>)}</select></label>
              </div>
            }
            pagination={{ page: accountActivityPage, pageSize: 10, total: accountActivityTotal, onPageChange: setAccountActivityPage }}
          />
          <div className="panel table-wrap">
            <h3>{selectedAccount} Derived Holdings ({yearLabel(accountYear)})</h3>
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Quantity</th>
                  <th>Book Avg</th>
                  <th>Book Value</th>
                  <th>Currency</th>
                  <th>Category</th>
                  <th>As Of</th>
                  <th aria-label="Expand row"></th>
                </tr>
              </thead>
              <tbody>
                {accountHoldings.flatMap((holding) => {
                  const childRows = holding.children || [];
                  const canExpand = childRows.length > 1;
                  const isExpanded = expandedHoldings.includes(holding.id);
                  return [
                    <tr key={holding.id} className="group-row">
                      <td data-label="Symbol">
                        <strong>{holding.symbol}</strong>
                      </td>
                      <td data-label="Quantity">{holding.quantity ?? "-"}</td>
                      <td data-label="Book Avg">{holding.average_price ? holding.average_price.toFixed(4) : "-"}</td>
                      <td data-label="Book Value">{holding.book_value.toFixed(2)}</td>
                      <td data-label="Currency">{holding.currency}</td>
                      <td data-label="Category">{holding.precise_category || holding.broad_category || "-"}</td>
                      <td data-label="As Of">{holding.as_of_date}</td>
                      <td className="expand-cell" data-label="Expand">
                        {canExpand && (
                          <button className="expand-button" type="button" aria-label={isExpanded ? "Collapse row" : "Expand row"} onClick={() => toggleExpanded(holding.id, setExpandedHoldings)}>
                            {isExpanded ? "▼" : "▶"}
                          </button>
                        )}
                      </td>
                    </tr>,
                    ...(canExpand && isExpanded ? childRows.map((child) => (
                      <tr key={child.id} className="sub-row">
                        <td data-label="Platform">{child.account_name} / {child.platform_name || "-"}</td>
                        <td data-label="Quantity">{child.quantity ?? "-"}</td>
                        <td data-label="Book Avg">{child.average_price ? child.average_price.toFixed(4) : "-"}</td>
                        <td data-label="Book Value">{child.book_value.toFixed(2)}</td>
                        <td data-label="Currency">{child.currency}</td>
                        <td data-label="Category">{child.precise_category || child.broad_category || "-"}</td>
                        <td data-label="As Of">{child.as_of_date}</td>
                        <td></td>
                      </tr>
                    )) : []),
                  ];
                })}
                {accountHoldings.length === 0 && (
                  <tr><td className="empty-state" colSpan={8}>No holdings derived for this account/year.</td></tr>
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
            platforms={platforms}
          />
        )}

        {activeModal === "account-transaction" && (
          <AccountTransactionModal
            onClose={() => setActiveModal(null)}
            onSaved={refreshAfterSave}
            defaultAccount={modalAccount || selectedAccount}
            transaction={editingAccountTransaction}
            platforms={platforms}
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
            <select value={globalYear} onChange={(e) => { setGlobalYear(e.target.value === "all" ? "all" : Number(e.target.value)); setHistoryPage(1); setPortfolioPLPage(1); }}>
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
          <button className="btn btn-secondary" onClick={refreshMarketPrices} disabled={isRefreshingPrices}>
            {isRefreshingPrices ? "Refreshing..." : "Refresh Prices"}
          </button>
          <button className="btn btn-secondary" onClick={() => openNewContribution()}>New Contribution</button>
          <button className="btn" onClick={() => openNewAccountTransaction()}>New Account Transaction</button>
        </div>
      </div>
      {backupError && <p className="banner-error">{backupError}</p>}
      {loadError && <p className="banner-error">{loadError}</p>}
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

        <div className="panel table-wrap">
          <div className="table-header">
            <h3>Account P/L</h3>
            <small>Only status=ok holdings; totals converted to CAD</small>
          </div>
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Book</th>
                <th>Market</th>
                <th>P/L</th>
                <th>P/L %</th>
              </tr>
            </thead>
            <tbody>
              {accountPLRows.map((row) => (
                <tr key={row.account}>
                  <td data-label="Account">{row.account}</td>
                  <td data-label="Book">{row.bookReporting.toFixed(2)} CAD</td>
                  <td data-label="Market">{row.marketReporting.toFixed(2)} CAD</td>
                  <td data-label="P/L" className={row.plReporting < 0 ? "negative" : "positive"}>{row.plReporting.toFixed(2)} CAD</td>
                  <td data-label="P/L %">{row.plPct != null ? `${row.plPct.toFixed(2)}%` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel table-wrap">
          <div className="table-header">
            <h3>Current Holdings P/L</h3>
            <div className="table-controls">
              <label>Account <select value={portfolioPLAccount} onChange={(e) => { setPortfolioPLAccount(e.target.value); setPortfolioPLPage(1); }}><option value="">All</option>{ACCOUNT_NAMES.map((accountName) => <option key={accountName} value={accountName}>{accountName}</option>)}</select></label>
              <label>Platform <select value={portfolioPLPlatform} onChange={(e) => { setPortfolioPLPlatform(e.target.value); setPortfolioPLPage(1); }}><option value="">All</option>{platforms.map((platform) => <option key={platform} value={platform}>{platform}</option>)}</select></label>
              <label>Status <select value={portfolioPLStatus} onChange={(e) => { setPortfolioPLStatus(e.target.value); setPortfolioPLPage(1); }}><option value="">All</option>{PRICE_STATUSES.map((status) => <option key={status} value={status}>{status.replace(/_/g, " ")}</option>)}</select></label>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>
                  <button
                    className="sort-button"
                    type="button"
                    onClick={() => {
                      setPortfolioPLSortDirection(portfolioPLSortDirection === "desc" ? "asc" : "desc");
                      setPortfolioPLPage(1);
                    }}
                  >
                    Symbol {portfolioPLSortDirection === "desc" ? "↓" : "↑"}
                  </button>
                </th>
                <th>Qty</th>
                <th>Book Avg</th>
                <th>Book</th>
                <th>Price</th>
                <th>Market</th>
                <th>P/L</th>
                <th>P/L %</th>
                <th>Status</th>
                <th aria-label="Expand row"></th>
              </tr>
            </thead>
            <tbody>
              {portfolioPL.flatMap((row) => {
                const childRows = row.children || [];
                const canExpand = childRows.length > 1;
                const isExpanded = expandedPortfolioPL.includes(row.id);
                return [
                  <tr key={row.id} className="group-row">
                    <td data-label="Account">{row.account_name}</td>
                    <td data-label="Symbol">
                      <strong>{row.provider_symbol || row.symbol}</strong><br /><small>{row.name || row.symbol}</small>
                    </td>
                    <td data-label="Qty">{row.quantity ?? "-"}</td>
                    <td data-label="Book Avg">{row.average_price ? row.average_price.toFixed(4) : "-"}</td>
                    <td data-label="Book">{row.book_value.toFixed(2)} {row.currency}</td>
                    <td data-label="Price">{row.current_price ? `${row.current_price.toFixed(2)} ${row.price_currency || row.currency}` : "-"}</td>
                    <td data-label="Market">{row.market_value ? `${row.market_value.toFixed(2)} ${row.currency}` : "-"}</td>
                    <td data-label="P/L" className={(row.unrealized_pl || 0) < 0 ? "negative" : "positive"}>{row.unrealized_pl !== undefined && row.unrealized_pl !== null ? row.unrealized_pl.toFixed(2) : "-"}</td>
                    <td data-label="P/L %">{row.unrealized_pl_pct !== undefined && row.unrealized_pl_pct !== null ? `${row.unrealized_pl_pct.toFixed(2)}%` : "-"}</td>
                    <td data-label="Status">{renderPLStatus(row)}</td>
                    <td className="expand-cell" data-label="Expand">
                      {canExpand && (
                        <button className="expand-button" type="button" aria-label={isExpanded ? "Collapse row" : "Expand row"} onClick={() => toggleExpanded(row.id, setExpandedPortfolioPL)}>
                          {isExpanded ? "▼" : "▶"}
                        </button>
                      )}
                    </td>
                  </tr>,
                  ...(canExpand && isExpanded ? childRows.map((child) => (
                    <tr key={child.id} className="sub-row">
                      <td data-label="Account">{child.account_name}</td>
                      <td data-label="Platform">{child.platform_name || "-"}</td>
                      <td data-label="Qty">{child.quantity ?? "-"}</td>
                      <td data-label="Book Avg">{child.average_price ? child.average_price.toFixed(4) : "-"}</td>
                      <td data-label="Book">{child.book_value.toFixed(2)} {child.currency}</td>
                      <td data-label="Price">{child.current_price ? `${child.current_price.toFixed(2)} ${child.price_currency || child.currency}` : "-"}</td>
                      <td data-label="Market">{child.market_value ? `${child.market_value.toFixed(2)} ${child.currency}` : "-"}</td>
                      <td data-label="P/L" className={(child.unrealized_pl || 0) < 0 ? "negative" : "positive"}>{child.unrealized_pl !== undefined && child.unrealized_pl !== null ? child.unrealized_pl.toFixed(2) : "-"}</td>
                      <td data-label="P/L %">{child.unrealized_pl_pct !== undefined && child.unrealized_pl_pct !== null ? `${child.unrealized_pl_pct.toFixed(2)}%` : "-"}</td>
                      <td data-label="Status">{renderPLStatus(child)}</td>
                      <td></td>
                    </tr>
                  )) : []),
                ];
              })}
              {portfolioPL.length === 0 && (
                <tr><td className="empty-state" colSpan={11}>No holdings available for P/L.</td></tr>
              )}
            </tbody>
          </table>
          <div className="pagination">
            <small>Page {portfolioPLPage} of {Math.max(1, Math.ceil(portfolioPLTotal / 10))} · {portfolioPLTotal} records</small>
            <div>
              <button className="btn btn-secondary table-action" disabled={portfolioPLPage === 1} onClick={() => setPortfolioPLPage(portfolioPLPage - 1)}>Previous</button>
              <button className="btn btn-secondary table-action" disabled={portfolioPLPage * 10 >= portfolioPLTotal} onClick={() => setPortfolioPLPage(portfolioPLPage + 1)}>Next</button>
            </div>
          </div>
        </div>

        <div className="panel table-wrap planning-grid">
          <div>
            <h3>Investable Cash</h3>
            <table>
              <thead><tr><th>Account</th><th>Platform</th><th>Cash</th></tr></thead>
              <tbody>
                {investableCash.map((row) => (
                  <tr key={row.id}>
                    <td data-label="Account">{row.account_name}</td>
                    <td data-label="Platform">{row.platform_name || "-"}</td>
                    <td data-label="Cash">{row.book_value.toFixed(2)} {row.currency}</td>
                  </tr>
                ))}
                {investableCash.length === 0 && <tr><td className="empty-state" colSpan={3}>No investable cash found.</td></tr>}
              </tbody>
            </table>
          </div>
          <div>
            <h3>Current Allocation</h3>
            <table>
              <thead><tr><th>Category</th><th>Value</th><th>Weight</th></tr></thead>
              <tbody>
                {allocationRows.map((row) => (
                  <tr key={row.label}>
                    <td data-label="Category">{row.label}</td>
                    <td data-label="Value">{row.value.toFixed(2)}</td>
                    <td data-label="Weight">{totalPortfolioValue ? `${((row.value / totalPortfolioValue) * 100).toFixed(1)}%` : "-"}</td>
                  </tr>
                ))}
                {allocationRows.length === 0 && <tr><td className="empty-state" colSpan={3}>No allocation data found.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel chart chart-wide">
          <h3>Used vs Remaining Balance</h3>
          <ReactECharts className="chart-canvas chart-canvas-short" option={balanceOption} />
        </div>

        <TransactionTable
          data={transactions}
          title={`Activity History (${yearLabel(globalYear)})`}
          emptyMessage="No activity matches the current filters."
          controls={
            <div className="table-controls">
              <label>Sort <select value={historySortDirection} onChange={(e) => { setHistorySortDirection(e.target.value as "asc" | "desc"); setHistoryPage(1); }}><option value="desc">Date: newest</option><option value="asc">Date: oldest</option></select></label>
              <label>Type <select value={historyType} onChange={(e) => { setHistoryType(e.target.value as TransactionType | ""); setHistoryPage(1); }}><option value="">All</option>{["contribution", "investment_buy", "investment_sell", "transfer", "dividend_interest", "dividend_reinvestment", "quantity_adjustment", "currency_exchange"].map((type) => <option key={type} value={type}>{type.replace(/_/g, " ")}</option>)}</select></label>
              <label>Platform <select value={historyPlatform} onChange={(e) => { setHistoryPlatform(e.target.value); setHistoryPage(1); }}><option value="">All</option>{platforms.map((platform) => <option key={platform} value={platform}>{platform}</option>)}</select></label>
            </div>
          }
          pagination={{ page: historyPage, pageSize: 10, total: historyTotal, onPageChange: setHistoryPage }}
        />
      </div>
      {activeModal === "manual-valuation" && manualValuationRow && (
        <ManualValuationModal
          row={manualValuationRow}
          onClose={() => setActiveModal(null)}
          onSaved={refreshAfterSave}
        />
      )}

      {activeModal === "contribution" && (
        <ContributionModal
          onClose={() => setActiveModal(null)}
          onSaved={refreshAfterSave}
          defaultAccount={modalAccount}
          contribution={editingContribution}
          platforms={platforms}
        />
      )}

      {activeModal === "account-transaction" && (
        <AccountTransactionModal
          onClose={() => setActiveModal(null)}
          onSaved={refreshAfterSave}
          defaultAccount={modalAccount}
          transaction={editingAccountTransaction}
          platforms={platforms}
        />
      )}
    </div>
  );
}

export default App;
