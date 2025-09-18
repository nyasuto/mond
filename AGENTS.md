 # Repository Guidelines

* 可能な限り日本語で会話

 ## Project Structure & Module Organization
 - `schema.sql`: SQLite schema for `fx_rates`, `assets`, `snapshots`, `cashflows` and views (e.g., `v_valuation`).
 - `views/`: Reusable view definitions (`.sql`), one file per view.
 - `scripts/`: Small utilities for import/export and checks (bash or python).
 - `data/`: Local CSVs for imports/exports (keep out of git).
 - `tests/`: SQL checks and expected CSVs for simple verification.
 - `README.md`: Product overview and quickstart. This file: contributor guide.

 ## Build, Test, and Development Commands
 - Initialize DB: `sqlite3 money_diary.db < schema.sql`
 - Run ad‑hoc query: `sqlite3 money_diary.db "SELECT * FROM v_valuation WHERE date='2025-09-15';"`
 - Import CSV (example): `sqlite3 -cmd ".mode csv" -cmd ".import data/fx_rates.csv fx_rates" money_diary.db`
 - Export query to CSV: `sqlite3 -header -csv money_diary.db "SELECT * FROM snapshots" > data/snapshots.csv`
 - Reset DB (destructive): `rm -f money_diary.db && sqlite3 money_diary.db < schema.sql`

 ## Coding Style & Naming Conventions
 - SQL: UPPERCASE keywords, 2‑space indent, one clause per line.
 - Tables: plural snake_case (e.g., `fx_rates`, `cashflows`). Columns: snake_case; dates as `TEXT` `YYYY-MM-DD`.
 - Migrations: `migrations/YYYY-MM-DD_short-name.sql`; keep schema changes idempotent when feasible.
 - Views: name with `v_` prefix; match business terms used in README.

 ## Testing Guidelines
 - Store tests in `tests/`. Pattern: write a `.sql` that prepares minimal rows, runs the view/query, and emits CSV.
 - Golden files: save expected output in `tests/expected/<test-name>.csv`.
 - Run a test: `sqlite3 -csv -header money_diary.db < tests/<test-name>.sql > tests/out/<test-name>.csv && diff -u tests/expected/<test-name>.csv tests/out/<test-name>.csv`
 - Aim for coverage of views (e.g., price vs. FX attribution), foreign keys, and NOT NULL constraints.

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- One logical change per commit; include schema and view updates together with minimal seed data for reproduction.
- PRs include: purpose, schema diffs, example queries/outputs, and any migration steps. Link issues if applicable; add screenshots for visualization changes.
- Do **not** merge your own pull requests. Always request review/approval from another contributor.

## PR 記述スタイル（日本語）
- 見出し構成: `概要`, `変更点`, `背景/目的`, `使い方/確認方法`, `関連Issue`, `チェックリスト`。
- 箇条書きは簡潔に、コマンドはコードブロックで示す。
- ひな型: `.github/PULL_REQUEST_TEMPLATE.md`（自動適用）。

 ## Security & Configuration Tips
 - Keep personal data local. Do not commit `money_diary.db` or private CSVs; add them to `.gitignore`.
 - Store API keys (if added later) in a local `.env` file, never in git.
 - Back up your DB periodically; migrations should be reversible when practical.
