import { AccountTransactionType } from "../types";

export const platformOptions = ["Wealthsimple", "EQ Bank", "CIBC", "Quest Trade", "Sun Life"];

export const accountTransactionOptions: { label: string; value: AccountTransactionType }[] = [
  { label: "Buy", value: "investment_buy" },
  { label: "Sell", value: "investment_sell" },
  { label: "Transfer", value: "transfer" },
  { label: "Dividend", value: "dividend_interest" },
  { label: "Reinvest", value: "dividend_reinvestment" },
  { label: "Adjust units", value: "quantity_adjustment" },
  { label: "Exchange", value: "currency_exchange" },
  { label: "Withdrawal", value: "withdrawal" },
];

export const categoryOptions: Record<string, string[]> = {
  Cash: ["Cash"],
  Bond: ["Bond", "GIC", "Money Market"],
  Balanced: ["Balanced", "Target Date Fund"],
  "All Equity": [
    "All Equity",
    "Canadian Equity",
    "US Equity",
    "International Equity",
    "Emerging Markets",
    "Stock",
    "REIT",
    "Gold ETF",
    "Crypto",
  ],
  Income: ["Dividend", "Interest"],
  Other: ["Other"],
};

export function preciseOptionsFor(broadCategory: string) {
  return categoryOptions[broadCategory] || [];
}
