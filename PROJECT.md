# Project: Shariah Compliance Screening and Auditing Alignment

## Architecture
This application is a Shariah compliance screener and portfolio optimizer. It consists of:
1. **Ingestion & Harvesting**: Downloads financial reports (SEC 10-K/10-Q) and parses them.
2. **AI Auditing**: Performs segment disaggregation (extracting haram/doubtful business lines) and extracts gross interest income.
3. **Screening Engine**: Applies compliance checks (Tangibility, Debt/Market Cap, Cash/Market Cap, Haram revenue thresholds) and outputs compliance statuses.
4. **Portfolio Optimizer**: Uses Modern Portfolio Theory (MPT) to optimize portfolio allocation over the compliant universe.
5. **Dashboard UI**: Displays compliance metrics, historical backtests, optimization results, and audit detail panels.

```
[Filings / Web Data] ──> [Harvester/SEC Extractor] ──> [AI Analyst]
                                                           │ (Qualitative overrides)
                                                           ▼
[Market/Financials] ──> [Screener Engine] ──> [Database (halal/doubtful/rejections)]
                                                   │
                                                   ├──> [Portfolio Optimizer]
                                                   │
                                                   ▼
                                            [Streamlit UI]
```

## Code Layout
- `main.py` - Main Streamlit UI frontend dashboard.
- `src/screener.py` - Core screening calculations (including Tangibility, Debt, Cash, and Combined Revenue thresholds).
- `src/optimizer.py` - Portfolio optimizer utilizing SciPy to allocate weight under constraints.
- `src/ai_analyst.py` - AI auditor that disaggregates composite segment revenue and extracts interest income.
- `src/ingestion.py` - Main entrypoint to load stock financials from Yahoo Finance/database and kick off audits.
- `src/utils.py` - Shared database connection utility (`get_db()`).
- `tests/` - Automated unit/integration tests folder.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | Milestone E2E | Design E2E testing framework, test runner, and Tiers 1-4 tests | None | DONE (completed by b7669163-9b36-4f83-ae45-ac990606ccf9) |
| 1 | Milestone 1 | Implement Tangibility Screen (replace Accounts Receivable) | None | DONE (completed by e5fd108f-a1df-4672-90af-77da0e4054d5) |
| 2 | Milestone 2 | Separate Doubtful stock status in DB, Optimizer, and Streamlit UI | Milestone 1 | IN_PROGRESS (Conv ID: 46a4a71b-28ce-4b48-b059-770c868dbc8d) |
| 3 | Milestone 3 | Implement generalizable AI auditing (Interest Income priority + disaggregation rules) | None | PLANNED (Track: 46a4a71b-28ce-4b48-b059-770c868dbc8d) |
| 4 | Milestone 4 | Final integration, verify 100% test pass, White-box hardening (Tier 5), Audit | Milestones E2E, 1, 2, 3 | PLANNED (Track: 46a4a71b-28ce-4b48-b059-770c868dbc8d) |

## Interface Contracts
### `screener.py` ↔ Database
- Output tables: `halal_universe`, `doubtful_universe`, and `halal_rejections`.
- `doubtful_universe` must match the schema of `halal_universe`.
- A stock is placed in `doubtful_universe` if it fails *only* the combined Haram + Doubtful revenue threshold of 5.0%, but passes business activity and other financial screens.

### `optimizer.py` ↔ Database & UI
- `run_optimizer(..., include_doubtful=False)`:
  - If `include_doubtful=True`, the optimizer loads tickers from both `halal_universe` and `doubtful_universe`.
  - If `include_doubtful=False` (default), the optimizer only loads tickers from `halal_universe`.

### `ai_analyst.py` ↔ Ingestion
- `analyze_company_compliance(ticker, name, summary, source_text=None, db_financials=None)`:
  - Returns a JSON response containing extracted financial metrics in millions of USD (such as `haram_revenue_millions`, `doubtful_revenue_millions`, `interest_income_millions`).
  - System prompt must guide the model to locate and extract gross interest income from notes first.
  - The model must perform segment disaggregation without using stock-specific hardcoded rules.
