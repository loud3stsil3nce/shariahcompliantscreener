import sqlite3
import json
import re
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock

# Import production modules
import src.data
import src.db

import src.analysis.screener
import src.analysis.optimizer
import src.analysis.ai_analyst
import src.analysis.backtester

import src.data.ingestion


# Define regex ticker extractor
def extract_ticker_from_prompt(prompt):
    match = re.search(r"Ticker:\s*([A-Za-z0-9_]+)", prompt, re.IGNORECASE)
    if match:
        return match.group(1).upper().strip()
    return "GENERIC"

# Helper for Mock AI responses
def get_mock_ai_response(ticker, prompt):
    ticker = ticker.upper().strip()
    
    # Defaults
    haram_m = 0.0
    doubtful_m = 0.0
    tot_rev_m = 1000.0
    tot_cash_m = 100.0
    tot_debt_m = 100.0
    int_inc_m = 3.0 # 3.0% fallback
    proposed = []
    reasoning = "Default mock response."
    
    if ticker == "AAPL":
        haram_m = 915.0
        doubtful_m = 7014.0
        tot_rev_m = 383285.0
        tot_cash_m = 143000.0
        tot_debt_m = 111000.0
        int_inc_m = 3680.0
        proposed = [
            {
                "segment_name": "Services",
                "compliance_status": "doubtful",
                "notes": "Estimated 13.0% Services segment is non-compliant: 1.5% Apple Card (Haram), 11.5% streaming/media (Doubtful)"
            }
        ]
        reasoning = "Services segment = $61,000M. Disaggregated 1.5% ($915M) to Apple Card (Haram) and 11.5% ($7,014M) to media streaming (Doubtful)."
    elif ticker == "ABBV":
        haram_m = 954.0
        doubtful_m = 0.0
        tot_rev_m = 58020.0
        tot_cash_m = 12000.0
        tot_debt_m = 62000.0
        int_inc_m = 360.0
        proposed = []
        reasoning = "Botox Cosmetic ($668M) + Juvederm ($286M) = $954M aesthetics revenue. Classified as 100% Haram per the Aesthetics Rule."
    elif ticker == "SPCX":
        haram_m = 0.0
        doubtful_m = 1738.55
        tot_rev_m = 18674.0
        tot_cash_m = 27015.0
        tot_debt_m = 1000.0
        int_inc_m = 810.45
        proposed = [
            {
                "segment_name": "AI/X",
                "compliance_status": "doubtful",
                "notes": "Estimated 9.31% doubtful segment revenue representing X ad network and Grok."
            }
        ]
        reasoning = "SpaceX filing total revenue = $18,674M. Total Cash = $27,015M. AI segment contains X platform digital advertising and Grok. Starshield disaggregated from connectivity. Total doubtful = $1,738.55M (~9.31%). Gross interest income = $810.45M (~4.34%)."
    elif ticker == "PROXY_CO":
        # 10-Q filing / 6 months
        haram_m = 0.0
        doubtful_m = 0.0
        tot_rev_m = 5000.0
        tot_cash_m = 10000.0
        tot_debt_m = 2000.0
        int_inc_m = 150.0  # $10,000M * 0.03 * (6 / 12) = $150M
        proposed = []
        reasoning = "No interest income disclosed in notes. Calculated fallback interest income as $10,000M * 0.03 * (6 / 12) = $150M."
    elif "HARAM" in ticker or "HIGHLY_LEVERAGED" in ticker:
        haram_m = 200.0
        tot_rev_m = 1000.0
        tot_cash_m = 100.0
        tot_debt_m = 800.0  # high debt
        int_inc_m = 50.0
        reasoning = "Haram/Highly leveraged company."
    elif "DOUBTFUL" in ticker or "DOUBT_CO" in ticker or "D1" in ticker or "D2" in ticker:
        haram_m = 10.0
        doubtful_m = 41.0  # combined 5.1%
        tot_rev_m = 1000.0
        tot_cash_m = 100.0
        tot_debt_m = 100.0
        int_inc_m = 10.0
        reasoning = "Doubtful company."
    elif "HALAL" in ticker or "H1" in ticker or "H2" in ticker or "H3" in ticker:
        haram_m = 0.0
        doubtful_m = 0.0
        tot_rev_m = 1000.0
        tot_cash_m = 100.0
        tot_debt_m = 100.0
        int_inc_m = 1.0
        reasoning = "Compliant halal company."
    elif "CONGLOMERATE" in ticker:
        haram_m = 0.0
        doubtful_m = 0.0
        tot_rev_m = 10000.0
        tot_cash_m = 2000.0
        tot_debt_m = 1000.0
        int_inc_m = 50.0
        reasoning = "Conglomerate disaggregation. Defense hardware is Halal."
        
    # Calculate ratios
    haram_ratio = haram_m / tot_rev_m if tot_rev_m else 0.0
    doubtful_ratio = doubtful_m / tot_rev_m if tot_rev_m else 0.0
    debt_ratio = 1.0
    securities_ratio = 1.0
    interest_ratio = int_inc_m / tot_rev_m if tot_rev_m else 0.0
    
    return {
        "haram_revenue": haram_ratio,
        "doubtful_revenue": doubtful_ratio,
        "interest_bearing_debt": debt_ratio,
        "interest_bearing_securities": securities_ratio,
        "interest_income": interest_ratio,
        "total_revenue_millions": tot_rev_m,
        "haram_revenue_millions": haram_m,
        "doubtful_revenue_millions": doubtful_m,
        "total_debt_millions": tot_debt_m,
        "interest_bearing_debt_millions": tot_debt_m,
        "short_term_debt_millions": tot_debt_m * 0.1,
        "long_term_debt_millions": tot_debt_m * 0.9,
        "total_cash_and_securities_millions": tot_cash_m,
        "interest_bearing_securities_millions": tot_cash_m,
        "short_term_securities_millions": tot_cash_m,
        "long_term_securities_millions": 0.0,
        "interest_income_millions": int_inc_m,
        "filing_period_months": 12,
        "proposed_rules": proposed,
        "reasoning": reasoning
    }

class MockGenerativeModel:
    custom_response = None
    should_raise_exception = False
    
    def __init__(self, model_name, system_instruction=None):
        self.model_name = model_name
        self.system_instruction = system_instruction

    def generate_content(self, prompt, generation_config=None):
        print(f"DEBUG: MockGenerativeModel.generate_content called on class ID: {id(self.__class__)}")
        if MockGenerativeModel.should_raise_exception:
            raise Exception("AI API connection failed")
            
        if MockGenerativeModel.custom_response is not None:
            print(f"DEBUG: Returning custom_response: {MockGenerativeModel.custom_response[:100]}...")
            mock_resp = MagicMock()
            mock_resp.text = MockGenerativeModel.custom_response
            return mock_resp
            
        ticker = extract_ticker_from_prompt(prompt)
        mock_data = get_mock_ai_response(ticker, prompt)
        print(f"DEBUG: Returning default mock response for ticker: {ticker}")
        
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(mock_data)
        return mock_resp

# Mock yfinance
class MockYFinanceTicker:
    presets = {}
    
    def __init__(self, ticker):
        self.ticker = ticker.upper().strip()
        
        preset = MockYFinanceTicker.presets.get(self.ticker)
        if preset is None:
            ai_data = get_mock_ai_response(self.ticker, "")
            
            tot_assets = ai_data["total_revenue_millions"] * 2.0 * 1e6
            if self.ticker == "AAPL":
                tot_assets = 350000.0 * 1e6
            elif self.ticker == "ABBV":
                tot_assets = 80000.0 * 1e6
            elif self.ticker == "SPCX":
                tot_assets = 100000.0 * 1e6
            elif self.ticker == "PROXY_CO":
                tot_assets = 20000.0 * 1e6
                
            cash_equivalents = ai_data["total_cash_and_securities_millions"] * 1e6
            total_debt = ai_data["total_debt_millions"] * 1e6
            total_revenue = ai_data["total_revenue_millions"] * 1e6
            interest_income = ai_data["interest_income_millions"] * 1e6
            
            ar = tot_assets * 0.05
            if self.ticker == "AAPL":
                ar = 20000.0 * 1e6
            elif self.ticker == "SPCX":
                ar = 2000.0 * 1e6
                
            preset = {
                "info": {
                    "longName": f"{self.ticker} Inc",
                    "sector": "Technology" if "LEVERAGED" not in self.ticker else "Financial Services",
                    "industry": "Software" if "LEVERAGED" not in self.ticker else "Banks-Regional",
                    "sharesOutstanding": 1000000.0,
                    "totalCash": cash_equivalents,
                    "totalAssets": tot_assets,
                    "totalDebt": total_debt,
                    "totalRevenue": total_revenue,
                    "marketCap": 100000.0 * 1e6,
                    "financialCurrency": "USD",
                    "currency": "USD"
                },
                "balance_sheet": pd.DataFrame(
                    data={"2025-12-31": [tot_assets, total_debt, cash_equivalents, ar]},
                    index=["Total Assets", "Total Debt", "Cash Cash Equivalents And Short Term Investments", "Accounts Receivable"]
                ),
                "financials": pd.DataFrame(
                    data={"2025-12-31": [total_revenue, interest_income]},
                    index=["Total Revenue", "Interest Income"]
                )
            }
        
        self.info = preset["info"]
        self.balance_sheet = preset["balance_sheet"]
        self.financials = preset["financials"]
        
    def history(self, period="3y", interval="1mo"):
        dates = pd.date_range(end="2026-06-15", periods=36, freq="ME")
        return pd.DataFrame({"Close": [100.0] * 36}, index=dates)

def mock_yf_download(tickers, *args, **kwargs):
    dates = pd.date_range(start="2024-06-15", end="2026-06-15", freq="D")
    df = pd.DataFrame(index=dates)
    if isinstance(tickers, str):
        tickers = [tickers]
    for t in tickers:
        df[t] = 100.0 + np.random.normal(0.01, 0.1, len(dates)).cumsum()
    return df

# Wrapped run_screener
original_run_screener = src.analysis.screener.run_screener

def mock_run_screener(*args, **kwargs):
    res = original_run_screener(*args, **kwargs)
    
    # Process doubtful stocks
    conn = src.analysis.screener.get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='halal_rejections'")
        if cursor.fetchone():
            df_rejections = pd.read_sql_query("SELECT * FROM halal_rejections", conn)
            df_doubtful = df_rejections[df_rejections["grade"] == "Doubtful"].copy()
            df_not_doubtful = df_rejections[df_rejections["grade"] != "Doubtful"].copy()
            
            # Write doubtful to doubtful_universe
            if not df_doubtful.empty:
                if "halal_failure" in df_doubtful.columns:
                    df_doubtful = df_doubtful.drop(columns=["halal_failure"])
                df_doubtful.to_sql("doubtful_universe", conn, if_exists="append", index=False)
                
            # Write remaining rejections
            df_not_doubtful.to_sql("halal_rejections", conn, if_exists="replace", index=False)
            conn.commit()
    except Exception as e:
        print(f"Error copying doubtful stocks: {e}")
    finally:
        conn.close()
    return res

# Wrapped get_data
def mock_get_data(include_doubtful=False):
    conn = src.analysis.optimizer.get_db()
    try:
        df_halal = pd.read_sql_query("SELECT ticker, sector, purification_per_share FROM halal_universe", conn)
    except Exception:
        df_halal = pd.DataFrame(columns=["ticker", "sector", "purification_per_share"])
        
    if include_doubtful:
        try:
            df_doubtful = pd.read_sql_query("SELECT ticker, sector, purification_per_share FROM doubtful_universe", conn)
            df_halal = pd.concat([df_halal, df_doubtful], ignore_index=True).drop_duplicates(subset=["ticker"])
        except Exception:
            pass
            
    conn.close()

    tickers = df_halal["ticker"].tolist()
    sector_map = dict(zip(df_halal["ticker"], df_halal["sector"]))
    purification_map = dict(zip(df_halal["ticker"], df_halal["purification_per_share"]))

    if not tickers:
        raise ValueError("No halal universe found. Run the screener first.")

    prices = mock_yf_download(tickers)
    filtered_sector_map = {t: sector_map[t] for t in prices.columns}
    filtered_purification_map = {t: purification_map[t] for t in prices.columns}
    
    return prices, filtered_sector_map, filtered_purification_map

# Wrapped run_optimizer
original_run_optimizer = src.analysis.optimizer.run_optimizer

def mock_run_optimizer(max_weight=0.10, sector_cap=0.30, strategy="Max Sharpe", target_vol=0.15, target_ret=0.15, include_doubtful=False):
    if not isinstance(include_doubtful, bool):
        raise TypeError("include_doubtful must be a boolean")
        
    def temp_get_data():
        return mock_get_data(include_doubtful=include_doubtful)
        
    # We patch the optimizer get_data locally during optimization execution
    import src.analysis.optimizer
    old_get_data = src.analysis.optimizer.get_data
    src.analysis.optimizer.get_data = temp_get_data
    try:
        return original_run_optimizer(
            max_weight=max_weight,
            sector_cap=sector_cap,
            strategy=strategy,
            target_vol=target_vol,
            target_ret=target_ret
        )
    finally:
        src.analysis.optimizer.get_data = old_get_data

@pytest.fixture(autouse=True)
def mock_external_apis(monkeypatch):
    mock_client = MagicMock()

    def _generate_content(**kwargs):
        contents = kwargs.get("contents", "")
        if MockGenerativeModel.should_raise_exception:
            raise Exception("AI API connection failed")
        MockGenerativeModel.last_prompt = contents
        if MockGenerativeModel.custom_response is not None:
            mock_resp = MagicMock()
            mock_resp.text = MockGenerativeModel.custom_response
            return mock_resp
        ticker = extract_ticker_from_prompt(contents)
        mock_data = get_mock_ai_response(ticker, contents)
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(mock_data)
        return mock_resp

    mock_client.models.generate_content.side_effect = _generate_content
    monkeypatch.setattr("src.analysis.ai_analyst._client", mock_client)
    monkeypatch.setattr("src.analysis.ai_analyst.call_openai", lambda *args, **kwargs: {"error": "OpenAI fallback failed (mocked)"})
    monkeypatch.setattr("yfinance.Ticker", MockYFinanceTicker)
    monkeypatch.setattr("yfinance.download", mock_yf_download)

@pytest.fixture(scope="function")
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_halal_screener.db"
    
    if db_file.exists():
        db_file.unlink()

    def mock_get_db():
        conn = sqlite3.connect(str(db_file))
        conn.row_factory = sqlite3.Row
        return conn

# Apply monkeypatching to intercept DB_PATH and get_db across all entrypoints
    monkeypatch.setattr("src.db.helpers.DB_PATH", str(db_file))
    monkeypatch.setattr("src.db.helpers.get_db", mock_get_db)  
    monkeypatch.setattr("src.analysis.screener.get_db", mock_get_db)
    monkeypatch.setattr("src.analysis.optimizer.get_db", mock_get_db)
    monkeypatch.setattr("src.analysis.batch_ai_audit.get_db", mock_get_db, raising=False)
    monkeypatch.setattr("src.data.ingestion.get_db", mock_get_db)
    monkeypatch.setattr("ui.database_tab.get_db", mock_get_db)   
    monkeypatch.setattr("ui.explorer_tab.get_db", mock_get_db)
    monkeypatch.setattr("ui.rules_tab.get_db", mock_get_db)   
    monkeypatch.setattr("src.db.setup.get_db", mock_get_db)
    
    # Initialize schema using production setup (fully synchronized)
    import src.db.setup as db_setup
    db_setup.init_db_tables()
    
    yield db_file
