# Holdings Plan

## Goal

Build holdings as a snapshot system, separate from trade and contribution history. A holdings snapshot answers "what is my account distribution as of this date/year?" while transactions answer "what happened?"

## Current Scope

- Store one row per account holding/cash/unused line from the workbook distribution tab.
- Support current snapshots and year-wise snapshots.
- Preserve negative unused values because they reflect current contribution-room state.
- Keep source workbook cell references out of persisted holding rows for now.
- Keep row-level dates optional; most rows inherit the snapshot date.

## Data Model

- `holdings_snapshots`
- `snapshot_date`: as-of date for the snapshot batch.
- `snapshot_year`: reporting year, for example `2026`.
- `snapshot_type`: `current` or `year_end`.
- `holding_date`: optional row-level date when a holding has its own date.
- `record_type`: `holding`, `cash`, or `unused`.
- `account_id`: account such as `RRSP`, `TFSA`, `FHSA`.
- `instrument_id`: symbol/name such as `XEQT`, `Cash`, or `Unused`.
- `category_id`: broad/precise allocation bucket.
- `market_value`: CAD value, negative allowed for unused room.

## Import Rules

- Read `Distrubution` first, then `Distribution` if the corrected spelling exists later.
- Treat the distribution tab as holdings distribution, not trade distribution.
- Replace only the current-year/current snapshot rows when rerunning the workbook import.
- For `Unused` rows, use the app's current-year contribution-room calculation from the DB.
- Keep cash rows as `record_type=cash`.
- Keep all non-cash, non-unused rows as `record_type=holding`.
- Allow `market_value < 0` for unused rows.

## Next Tasks

1. Add API endpoints to commit holdings import previews instead of only previewing them.
2. Add `GET /holdings?snapshot_year=&snapshot_type=&account=` for table views.
3. Add UI controls for current snapshot vs year-end snapshot selection.
4. Add a contribution-to-investment linkage model:
   `contribution_allocations(contribution_transaction_id, investment_transaction_id, allocated_amount)`.
5. Add validation that allocations against one contribution do not exceed the contribution amount unless explicitly overridden.
6. Add a holdings snapshot history view so year-wise distribution can be compared over time.
7. Add tests for negative unused room, snapshot replacement, and year filtering.
