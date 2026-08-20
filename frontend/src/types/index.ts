export type TransactionType =
  | "contribution"
  | "investment_buy"
  | "investment_sell"
  | "transfer"
  | "dividend_interest";

export type AccountTransactionType = Exclude<TransactionType, "contribution">;

export interface ActivityRecord {
  id: number;
  transaction_date: string;
  account_name?: string;
  platform_name?: string;
  amount: number;
  notes?: string;
}

export interface Contribution extends ActivityRecord {}

export interface AccountTransaction extends ActivityRecord {
  transaction_type: AccountTransactionType;
  symbol?: string;
  broad_category?: string;
  precise_category?: string;
  quantity?: number;
  fees?: number;
}

export interface Holding {
  id: string;
  as_of_date: string;
  account_name: string;
  platform_name?: string;
  symbol: string;
  broad_category?: string;
  precise_category?: string;
  record_type: "holding" | "cash" | "unused" | string;
  quantity?: number;
  book_value: number;
}

export type Transaction = Omit<AccountTransaction, "transaction_type"> & {
  transaction_type: TransactionType;
};

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

export interface TimeSeriesPoint {
  month: string;
  contributions: number;
  investments: number;
}
