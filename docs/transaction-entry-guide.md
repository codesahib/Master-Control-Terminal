# Transaction Entry Guide

Use this guide to enter future activity from the UI without editing the database.

## Core Rules

- `Amount` is the value added to or removed from the holding.
- `Currency` is the holding currency.
- `Cash Used` is only needed when the cash currency is different from the holding currency, or when recording a zero-cost reinvestment.
- `Cash Currency` is the currency of `Cash Used`.
- Leave `Cash Used` blank when the holding currency and cash currency are the same.
- Use `Manual/custom symbol` for managed portfolios, GICs, or anything that does not trade on an exchange.
- For holdings without quantity, update market value from the P/L table using `Update value`.

## CAD-Traded CAD Holdings

Examples: `XEQT.TO`, `VEQT.TO`, `VBAL.TO`, Canadian ETFs or stocks.

Use `New Account Transaction` -> `Investment Buy`.

| Field | Value |
| --- | --- |
| Amount | Total CAD book cost |
| Currency | CAD |
| Symbol | Actual Canadian ticker, usually `.TO` |
| Quantity | Units bought |
| Fees | CAD fees, if any |
| Cash Used | Blank |

Result:

- CAD cash is deducted.
- Holding book value is CAD.
- P/L uses CAD market prices.

## USD-Traded USD Holdings Bought With USD Cash

Example: Questrade USD holdings after CAD was converted or journaled to USD.

First, if needed, record the currency conversion:

Use `Currency Exchange`.

| Field | Value |
| --- | --- |
| From Amount | CAD spent |
| From Currency | CAD |
| To Amount | USD received |
| To Currency | USD |
| Platform | Questrade |
| Fees | FX/conversion fee, if separate |

Then record the buy:

Use `Investment Buy`.

| Field | Value |
| --- | --- |
| Amount | USD book cost |
| Currency | USD |
| Symbol | US ticker, e.g. `NVDA`, `GOOG`, `TSLA` |
| Quantity | Units bought |
| Cash Used | Blank |
| Fees | USD fees, if any |

Result:

- USD cash is deducted.
- Holding book value is USD.
- P/L uses USD market prices.

## USD-Traded Holdings Bought With CAD Cash

Example: Wealthsimple buying US stocks in a CAD account.

Use `Investment Buy`.

| Field | Value |
| --- | --- |
| Amount | USD value purchased |
| Currency | USD |
| Cash Used | CAD amount charged by Wealthsimple |
| Cash Currency | CAD |
| Symbol | US ticker, e.g. `GOOG`, `NVDA`, `TSLA` |
| Quantity | Units bought |
| Fees | Usually `0` if fee is embedded in FX |
| Notes | Optional WS FX rate |

Result:

- CAD cash is deducted.
- Holding book value is USD.
- P/L uses USD market prices.

## USD Dividend Reinvestment In Wealthsimple CAD Account

Wealthsimple pays the dividend into the CAD account, then reinvests CAD into the USD holding.

Use two records.

First, record the dividend:

Use `Dividend/Interest`.

| Field | Value |
| --- | --- |
| Amount | CAD dividend received |
| Currency | CAD |
| Category | Income / Dividend |
| Notes | Dividend for symbol/date |

Then record the reinvestment:

Use `Dividend Reinvestment`.

| Field | Value |
| --- | --- |
| Amount | USD amount reinvested |
| Currency | USD |
| Cash Used | CAD amount used |
| Cash Currency | CAD |
| Symbol | US ticker |
| Quantity | Fractional units bought |
| Notes | Optional WS FX rate |

Result:

- Dividend income is recorded.
- CAD cash nets to zero after reinvestment.
- Holding book value is USD.

## CAD Dividend Reinvestment Into CAD Holding

Example: Canadian ETF DRIP.

Simple version:

Use `Dividend Reinvestment`.

| Field | Value |
| --- | --- |
| Amount | CAD amount reinvested |
| Currency | CAD |
| Symbol | Canadian ticker |
| Quantity | Units bought |
| Cash Used | Blank |

Detailed version, if you want dividend income tracked:

1. Add `Dividend/Interest` for the CAD dividend received.
2. Add `Dividend Reinvestment` with the same CAD amount and quantity bought.

## GICs

Use original principal as book value. Treat interest as income, not as new cost basis.

Initial purchase:

Use `Investment Buy`.

| Field | Value |
| --- | --- |
| Amount | Principal, e.g. `3000.00` |
| Currency | CAD |
| Symbol | `GIC` |
| Manual/custom symbol | Checked |
| Quantity | Blank |
| Category | Bond / GIC |

When interest is earned and reinvested:

First record income:

Use `Dividend/Interest`.

| Field | Value |
| --- | --- |
| Amount | Interest earned |
| Currency | CAD |
| Category | Income / Interest |
| Notes | GIC interest earned |

Then record reinvestment without increasing book value:

Use `Investment Buy`.

| Field | Value |
| --- | --- |
| Amount | `0` |
| Currency | CAD |
| Cash Used | Interest amount |
| Cash Currency | CAD |
| Symbol | `GIC` |
| Manual/custom symbol | Checked |
| Quantity | Blank |
| Notes | Reinvested GIC interest; book remains principal |

Then update current value:

1. Go to `Current Holdings P/L`.
2. Find `GIC`.
3. Click `Update value`.
4. Enter current GIC value and updated date.

Result:

- Book stays original principal.
- Market value is manually updated.
- P/L shows interest growth.

## Managed Portfolios

Example: `WS-income portfolio`.

Initial purchase:

Use `Investment Buy`.

| Field | Value |
| --- | --- |
| Amount | Principal invested |
| Currency | CAD |
| Symbol | `WS-income portfolio` |
| Manual/custom symbol | Checked |
| Quantity | Blank |
| Category | Your chosen category |

Regular value update:

1. Go to `Current Holdings P/L`.
2. Find `WS-income portfolio`.
3. Click `Update value`.
4. Enter current managed portfolio value and updated date.

Result:

- Book stays principal invested.
- Market value is manual.
- P/L updates from manual value.

## Sells

Use `Investment Sell`.

| Field | Value |
| --- | --- |
| Amount | Sale proceeds |
| Currency | Holding currency |
| Symbol | Symbol sold |
| Quantity | Quantity sold, if applicable |
| Fees | Selling fees |

Result:

- Cash is added in the holding currency.
- Book value is reduced.

## Quantity Adjustments

Use this only for splits, share consolidations, or broker quantity corrections.

Use `Quantity Adjustment`.

| Field | Value |
| --- | --- |
| Amount | `0` |
| Symbol | Affected symbol |
| Quantity | Positive or negative quantity adjustment |
| Currency | Holding currency |
| Notes | Reason for adjustment |

## Manual Value Updates

Use manual values for holdings that do not have exchange prices:

- GICs
- Managed portfolios
- Private/manual instruments
- Holdings without quantity

Steps:

1. Go to `Current Holdings P/L`.
2. Set `Status` to `All` if the row is not visible.
3. Click `Update value`.
4. Enter `Market Value`.
5. Enter `Updated Date`.
6. Save.

The P/L table will show `Manual value updated YYYY-MM-DD`.

## Quick Decision Table

| Case | Transaction Type | Amount Currency | Cash Used |
| --- | --- | --- | --- |
| Canadian ETF bought with CAD | Investment Buy | CAD | Blank |
| US stock bought with USD cash | Investment Buy | USD | Blank |
| US stock bought with CAD cash at WS | Investment Buy | USD | CAD amount charged |
| WS US dividend DRIP | Dividend/Interest + Dividend Reinvestment | CAD income, USD reinvestment | CAD amount used |
| GIC purchase | Investment Buy | CAD principal | Blank |
| GIC interest reinvested | Dividend/Interest + zero Investment Buy | CAD | Interest amount |
| Managed portfolio | Investment Buy + manual valuation | CAD | Blank |
