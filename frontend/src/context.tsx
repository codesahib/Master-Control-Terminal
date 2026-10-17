import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import { errorMessage } from "./lib/format";
import type { AccountTransaction, AccountTransactionType, Contribution, PortfolioHealth, PortfolioPLRow, PriceRefreshResult } from "./types";

export type ThemePref = "light" | "dark" | "system";
export type YearFilter = number | "all";

export type ModalState =
  | { kind: "contribution"; contribution?: Contribution; account?: string }
  | { kind: "transaction"; transaction?: AccountTransaction; account?: string; type?: AccountTransactionType }
  | { kind: "valuation"; row: PortfolioPLRow }
  | { kind: "gic"; row: PortfolioPLRow }
  | { kind: "new"; account?: string }
  | null;

// Confirms open on top of any modal, so cancelling returns to the modal with its state intact.
export interface ConfirmState {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<void> | void;
}

export interface Toast {
  id: number;
  message: string;
  tone: "ok" | "error";
}

interface AppState {
  year: YearFilter;
  setYear: (year: YearFilter) => void;
  currency: string;
  setCurrency: (currency: string) => void;
  years: number[];
  platforms: string[];
  themePref: ThemePref;
  setThemePref: (pref: ThemePref) => void;
  theme: "light" | "dark";
  privacy: boolean;
  togglePrivacy: () => void;
  version: number;
  refresh: () => void;
  toast: Toast | null;
  notify: (message: string, tone?: Toast["tone"]) => void;
  modal: ModalState;
  openModal: (modal: Exclude<ModalState, null>) => void;
  closeModal: () => void;
  confirm: ConfirmState | null;
  openConfirm: (confirm: ConfirmState) => void;
  closeConfirm: () => void;
  health: PortfolioHealth | null;
  refreshPrices: () => Promise<void>;
  refreshingPrices: boolean;
}

const AppContext = createContext<AppState | null>(null);
const CURRENT_YEAR = new Date().getFullYear();

function stored(key: string, fallback: string) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Private mode or blocked storage: the setting just won't persist.
  }
}

const lightQuery = () => window.matchMedia("(prefers-color-scheme: light)");

export function AppProvider({ children }: { children: ReactNode }) {
  const [year, setYear] = useState<YearFilter>(CURRENT_YEAR);
  const [currency, setCurrency] = useState("CAD");
  const [years, setYears] = useState<number[]>([CURRENT_YEAR]);
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [themePref, setThemePrefState] = useState<ThemePref>(() => stored("mt-theme", "system") as ThemePref);
  const [systemLight, setSystemLight] = useState(() => lightQuery().matches);
  const [privacy, setPrivacy] = useState(() => stored("mt-privacy", "0") === "1");
  const [version, setVersion] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const [modal, setModal] = useState<ModalState>(null);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [health, setHealth] = useState<PortfolioHealth | null>(null);
  const [refreshingPrices, setRefreshingPrices] = useState(false);

  const theme = themePref === "system" ? (systemLight ? "light" : "dark") : themePref;

  useEffect(() => {
    const query = lightQuery();
    const onChange = () => setSystemLight(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  // ponytail: applied during render (idempotent) so charts read the new CSS tokens in the same pass.
  if (document.documentElement.dataset.theme !== theme) document.documentElement.dataset.theme = theme;

  useEffect(() => {
    document.documentElement.classList.toggle("privacy", privacy);
  }, [privacy]);

  useEffect(() => {
    Promise.all([api.get<number[]>("/years"), api.get<string[]>("/platforms")])
      .then(([yearResponse, platformResponse]) => {
        setYears([...new Set([...yearResponse.data, CURRENT_YEAR])].sort((a, b) => b - a));
        setPlatforms(platformResponse.data);
      })
      .catch((error) => notify(errorMessage(error, "Startup data failed. Check the API connection."), "error"));
    // Saves and restores can add years or platforms, so refetch with the data version.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  useEffect(() => {
    api
      .get<PortfolioHealth>("/portfolio/health")
      .then((response) => setHealth(response.data))
      .catch(() => setHealth(null));
  }, [version]);

  const notify = useCallback((message: string, tone: Toast["tone"] = "ok") => {
    const id = Date.now();
    setToast({ id, message, tone });
    window.setTimeout(() => setToast((current) => (current?.id === id ? null : current)), tone === "error" ? 7000 : 4000);
  }, []);

  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  const refreshPrices = useCallback(async () => {
    setRefreshingPrices(true);
    try {
      const response = await api.post<PriceRefreshResult[]>("/market-prices/refresh");
      const failed = response.data.filter((row) => row.status !== "ok");
      const updated = response.data.length - failed.length;
      notify(
        failed.length
          ? `Updated ${updated} prices. ${failed.length} failed: ${failed.slice(0, 4).map((row) => row.symbol).join(", ")}${failed.length > 4 ? "…" : ""}`
          : `Updated ${updated} prices.`,
        failed.length && !updated ? "error" : "ok"
      );
      refresh();
    } catch (error) {
      notify(errorMessage(error, "Price refresh failed. Try again later."), "error");
    } finally {
      setRefreshingPrices(false);
    }
  }, [notify, refresh]);

  const value = useMemo<AppState>(
    () => ({
      year,
      setYear,
      currency,
      setCurrency,
      years,
      platforms,
      themePref,
      setThemePref: (pref) => {
        setThemePrefState(pref);
        store("mt-theme", pref);
      },
      theme,
      privacy,
      togglePrivacy: () =>
        setPrivacy((current) => {
          store("mt-privacy", current ? "0" : "1");
          return !current;
        }),
      version,
      refresh,
      toast,
      notify,
      modal,
      openModal: setModal,
      closeModal: () => setModal(null),
      confirm,
      openConfirm: setConfirm,
      closeConfirm: () => setConfirm(null),
      health,
      refreshPrices,
      refreshingPrices,
    }),
    [year, currency, years, platforms, themePref, theme, privacy, version, refresh, toast, notify, modal, confirm, health, refreshPrices, refreshingPrices]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used inside AppProvider");
  return context;
}

export function yearParams(year: YearFilter) {
  return year === "all" ? {} : { year };
}

export function yearLabel(year: YearFilter) {
  return year === "all" ? "All years" : String(year);
}
