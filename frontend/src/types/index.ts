export type TransactionType =
  | "contribution"
  | "investment_buy"
  | "investment_sell"
  | "transfer"
  | "dividend_interest"
  | "dividend_reinvestment"
  | "quantity_adjustment"
  | "currency_exchange";

export type AccountTransactionType = Exclude<TransactionType, "contribution">;

export interface ActivityRecord {
  id: number;
  transaction_date: string;
  account_name?: string;
  platform_name?: string;
  amount: number;
  currency: string;
  notes?: string;
}

export interface Contribution extends ActivityRecord {}

export interface AccountTransaction extends ActivityRecord {
  transaction_type: AccountTransactionType;
  source_platform_name?: string;
  instrument_id?: number;
  symbol?: string;
  broad_category?: string;
  precise_category?: string;
  quantity?: number;
  fees?: number;
  fee_currency?: string;
  source_amount?: number;
  source_currency?: string;
  contribution_id?: number;
  funding_contributions?: FundingContribution[];
}

export interface FundingContribution {
  contribution_id: number;
  amount: number;
  platform_name?: string;
}

export interface ContributionFunding {
  id: number;
  platform_name: string;
  source_label: string;
  remaining_amount: number;
}

export interface FundingCashSource {
  platform_name: string;
  amount: number;
}

export interface Holding {
  id: string;
  as_of_date: string;
  account_name: string;
  platform_name?: string;
  instrument_id?: number;
  symbol: string;
  broad_category?: string;
  precise_category?: string;
  record_type: "holding" | "cash" | "unused" | string;
  quantity?: number;
  book_value: number;
  currency: string;
  average_price?: number;
  children?: Holding[];
}

export type Transaction = Omit<AccountTransaction, "transaction_type"> & {
  transaction_type: TransactionType;
};

export interface PaginatedTransactions {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaginatedAccountTransactions {
  items: AccountTransaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaginatedPortfolioPL {
  items: PortfolioPLRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface DistributionPoint {
  label: string;
  value: number;
}

export interface ContributionRoom {
  account: string;
  tax_year: string;
  total_room: number;
  used: number;
  remaining: number;
}

export interface ContributionLimitSetting {
  account: string;
  tax_year: string;
  unused_room: number;
  new_room: number;
  total_room: number;
}

export interface SymbolSearchResult {
  id: number;
  symbol: string;
  provider_symbol: string;
  name?: string;
  exchange?: string;
  currency?: string;
  asset_type?: string;
  provider: string;
}

export interface PortfolioPLRow extends Holding {
  provider_symbol?: string;
  name?: string;
  current_price?: number;
  price_currency?: string;
  priced_at?: string;
  market_value?: number;
  unrealized_pl?: number;
  unrealized_pl_pct?: number;
  reporting_currency: string;
  fx_rate_to_reporting?: number;
  book_value_reporting?: number;
  market_value_reporting?: number;
  unrealized_pl_reporting?: number;
  price_status: string;
  manual_valuation_date?: string;
  children?: PortfolioPLRow[];
}

export interface ManualValuationPayload {
  account_name: string;
  platform_name?: string;
  instrument_id?: number;
  symbol?: string;
  instrument_name?: string;
  broad_category?: string;
  precise_category?: string;
  market_value: number;
  snapshot_date: string;
}
