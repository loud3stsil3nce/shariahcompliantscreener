# Shariah Compliance Screener and Portfolio Optimizer E2E Test Suite Validation

## Test Runner Command
To run the entire suite (new E2E tests + existing unit tests):
```bash
pytest -v tests/
```

To run only the newly created opaque-box E2E test suite (Tiers 1-4):
```bash
pytest -v tests/e2e/
```

To run specific tiers individually:
```bash
pytest -v -m tier1 tests/e2e/
pytest -v -m tier2 tests/e2e/
pytest -v -m tier3 tests/e2e/
pytest -v -m tier4 tests/e2e/
```

## Expected Exit Code
- Expected exit code: **`0`** (All tests passing)

---

## E2E Test Suite Checklist (60 Test Cases)

### Tier 1: Feature Coverage (25 Tests)
- [ ] **F1: Tangibility Screen**
  - [ ] `test_tangibility_pass`: Non-liquid assets exactly 30% of total assets (passes).
  - [ ] `test_tangibility_fail`: Non-liquid assets less than 30% (e.g. 29.9%, fails).
  - [ ] `test_tangibility_liquid_assets_calc`: Verifies liquid assets = Cash + Accounts Receivable.
  - [ ] `test_tangibility_non_liquid_assets_calc`: Verifies non-liquid assets = Total Assets - (Cash + AR).
  - [ ] `test_tangibility_replaces_receivables`: Verifies no hard 45% AR limit is applied when screening.
- [ ] **F2: Doubtful Database Categorization**
  - [ ] `test_doubtful_db_insertion`: Ticker failing only combined haram+doubtful threshold of 5% is written to `doubtful_universe`.
  - [ ] `test_doubtful_db_schema`: Verifies `doubtful_universe` schema matches `halal_universe`.
  - [ ] `test_doubtful_not_in_halal`: Verifies doubtful stock is NOT inserted into `halal_universe`.
  - [ ] `test_doubtful_not_in_rejections`: Verifies doubtful stock is NOT inserted into `halal_rejections` as failed/haram.
  - [ ] `test_doubtful_financial_filters`: Verifies doubtful stock passes tangibility, debt, and cash screens.
- [ ] **F3: Optimizer Doubtful Toggle**
  - [ ] `test_optimizer_exclude_doubtful_default`: `run_optimizer` excludes doubtful stocks by default.
  - [ ] `test_optimizer_include_doubtful_explicit`: `run_optimizer` includes doubtful stocks when toggle is True.
  - [ ] `test_optimizer_get_data_compliance_filter`: `get_data` loads only halal tickers when `include_doubtful=False`.
  - [ ] `test_optimizer_get_data_with_doubtful`: `get_data` loads both halal and doubtful tickers when `include_doubtful=True`.
  - [ ] `test_optimizer_empty_universe_handling`: Verifies optimizer behavior when no compliant stocks exist.
- [ ] **F4: AI Auditor Interest Priority**
  - [ ] `test_ai_auditor_extracts_interest_from_notes`: Verifies AI prompt asks for actual interest income from notes.
  - [ ] `test_ai_auditor_fallback_proxy`: Verifies fallback to 3.0% yield proxy when interest is not disclosed.
  - [ ] `test_ai_auditor_prefer_extracted_to_proxy`: Verifies AI auditor uses extracted interest instead of proxy if both are present/possible.
  - [ ] `test_ai_auditor_parser_valid_interest`: Parser extracts integer/float interest figures in millions.
  - [ ] `test_ai_auditor_zero_interest`: Verifies parser handles explicit zero interest disclosure.
- [ ] **F5: Robust Segment Disaggregation**
  - [ ] `test_segment_disaggregation_system_prompt`: Verifies no hardcoded tickers (AAPL, MSFT, ABBV, SPCX) in prompts.
  - [ ] `test_segment_disaggregation_composite_split`: Verifies disaggregation on mixed/composite segments based on notes.
  - [ ] `test_segment_disaggregation_notes_parsing`: Verifies parsing of tabular sub-disclosures in AI outputs.
  - [ ] `test_segment_disaggregation_doubtful_status`: Verifies disaggregated haram/doubtful ratio calculations.
  - [ ] `test_segment_disaggregation_fallback_behavior`: Verifies behavior when segment details are missing.

### Tier 2: Boundary & Corner Cases (25 Tests)
- [ ] **F1: Tangibility Screen**
  - [ ] `test_tangibility_boundary_exact_30`: Total Assets = 100, Cash = 35, AR = 35, Non-liquid = 30 (passes).
  - [ ] `test_tangibility_boundary_just_below_30`: Total Assets = 100, Cash = 35.1, AR = 35, Non-liquid = 29.9 (fails).
  - [ ] `test_tangibility_zero_assets`: Total Assets is zero or negative (handled gracefully without division by zero crash).
  - [ ] `test_tangibility_negative_cash_or_ar`: Negative values for cash/AR (validation error or handled cleanly).
  - [ ] `test_tangibility_assets_less_than_cash_plus_ar`: Liquid assets > Total Assets (ratio is negative, fails).
- [ ] **F2: Doubtful Database Categorization**
  - [ ] `test_doubtful_revenue_boundary_exact_5`: Haram + Doubtful revenue = exactly 5% (fails combined threshold, category is doubtful).
  - [ ] `test_doubtful_revenue_just_below_5`: Haram + Doubtful revenue = 4.9% (passes combined threshold, category is halal).
  - [ ] `test_doubtful_revenue_extremely_high`: Combined revenue = 90% (exceeds 5%, category is doubtful/haram).
  - [ ] `test_doubtful_override_handling`: Manual override is applied, category updates accordingly in DB.
  - [ ] `test_doubtful_duplicate_insertion`: Multiple screen runs preserve unique records in `doubtful_universe`.
- [ ] **F3: Optimizer Doubtful Toggle**
  - [ ] `test_optimizer_boundary_one_halal_one_doubtful`: Allocates weights correctly between 1 Halal and 1 Doubtful stock.
  - [ ] `test_optimizer_all_doubtful`: Universe contains only doubtful stocks (toggle True vs False).
  - [ ] `test_optimizer_invalid_toggle_value`: Passing non-boolean values to toggle parameter.
  - [ ] `test_optimizer_constraint_bounds`: Weight caps constraints are respected when doubtful is included.
  - [ ] `test_optimizer_purification_calc`: Verifies purification calculations for doubtful stocks.
- [ ] **F4: AI Auditor Interest Priority**
  - [ ] `test_ai_auditor_malformed_json_response`: Parser handles malformed JSON response from LLM gracefully.
  - [ ] `test_ai_auditor_missing_financials`: Filings missing revenue or asset details (handled with default fallback).
  - [ ] `test_ai_auditor_non_numeric_interest`: LLM returns text like "N/A" or "undisclosed" for interest.
  - [ ] `test_ai_auditor_extreme_interest_values`: Interest income exceeds total revenue (handled/flagged).
  - [ ] `test_ai_auditor_multiple_interest_mentions`: AI resolves multiple conflicting interest figures.
- [ ] **F5: Robust Segment Disaggregation**
  - [ ] `test_segment_disaggregation_unclear_text`: Unstructured text with no clear numbers.
  - [ ] `test_segment_disaggregation_rounding`: Segment percentages sum to 99.9% or 100.1% due to rounding.
  - [ ] `test_segment_disaggregation_negative_revenue`: Handles negative segment revenue (e.g. accounting adjustments).
  - [ ] `test_segment_disaggregation_large_segments`: Very large number of segments (e.g., 20+).
  - [ ] `test_segment_disaggregation_unknown_categories`: Handles custom/unknown segment names gracefully.

### Tier 3: Cross-Feature Combinations (5 Tests)
- [ ] 51. `test_tangibility_and_doubtful_interaction`: Stock fails tangibility screen and has 6% haram/doubtful revenue (should fail outright due to tangibility, not categorized as doubtful).
- [ ] 52. `test_doubtful_optimizer_and_db_flow`: Audit inserts doubtful stock -> DB stores it -> Optimizer fetches it with toggle True and allocates weights.
- [ ] 53. `test_ai_auditor_interest_and_revenue_screener`: AI extracts interest income & segments -> Ingestion stores them -> Screener uses them for tangibility and revenue tests.
- [ ] 54. `test_override_and_optimizer_flow`: AI extracts halal segment -> Manual override changes it to doubtful -> Optimizer includes/excludes based on override.
- [ ] 55. `test_extreme_all_features`: Stock with 29.9% tangibility, 5.0% doubtful revenue, and extracted interest income (verifies correct end-to-end routing).

### Tier 4: Real-World Application Scenarios (5 Tests)
- [ ] 56. `test_real_world_spcx_validation`: Opaque-box validation of SPCX parsing. The mock file/filing for SPCX is parsed, and resolves to a doubtful revenue ratio of ~9.31% and interest income ratio of ~4.34% without stock-specific prompts.
- [ ] 57. `test_real_world_aapl_standard_flow`: Standard halal stock flow (Apple Inc) with low debt, high tangibility, low doubtful revenue.
- [ ] 58. `test_real_world_abbv_standard_flow`: AbbVie Inc flow, ensuring general segment disaggregation correctly screens healthcare/aesthetics.
- [ ] 59. `test_real_world_highly_leveraged_financial_institution`: Standard bank flow, failing interest income screening.
- [ ] 60. `test_real_world_conglomerate_disaggregation`: Multi-segment conglomerate disaggregation (e.g., defense, services, entertainment).
