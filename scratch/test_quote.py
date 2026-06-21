import sys
import os
import asyncio
import pandas as pd
import numpy as np
import yfinance as yf

# Add project root to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.helpers import get_db
from src.analysis.screener import get_effective_override

MAX_DEBT_RATIO = 0.30
MAX_CASH_RATIO = 0.30
MAX_RECEIVABLES_RATIO = 0.45
MAX_HARAM_INCOME_RATIO = 0.05
MIN_TANGIBILITY_RATIO = 0.30
MAX_LIQUID_RATIO = 0.70

HARAM_SECTORS = ["financial"]
HARAM_INDUSTRY_KEYWORDS = [
    "casino", "gambling", "tobacco", "brewers", "wineries", "distilleries",
    "entertainment", "porn", "adult", "pork"
]

async def test_quote():
    ticker = "AAPL"
    
    # First check database details
    conn = get_db()
    try:
        query = f"""
            SELECT s.*,
                   m.haram_revenue_override, m.debt_ratio_override, m.cash_ratio_override, m.receivables_ratio_override, m.tangibility_ratio_override, m.interest_income_override, m.doubtful_revenue_override, m.reasoning as override_reason, m.is_user_override
            FROM stocks s
            LEFT JOIN manual_overrides m ON s.ticker = m.ticker
            WHERE s.ticker = '{ticker}'
        """
        stock_df = pd.read_sql_query(query, conn)
        if stock_df.empty:
            print("AAPL not found in database. Please ingest first.")
            return
        stock_data = stock_df.iloc[0]
        print("Stock database read successful.")
    finally:
        conn.close()
        
    loop = asyncio.get_running_loop()
    try:
        def fetch_yf_price():
            t = yf.Ticker(ticker)
            live_p = t.fast_info.get("lastPrice")
            if not live_p or pd.isna(live_p):
                hist = t.history(period="1d")
                if not hist.empty:
                    live_p = float(hist["Close"].iloc[-1])
            return live_p
            
        print("Fetching Yahoo Finance price...")
        live_price = await loop.run_in_executor(None, fetch_yf_price)
        print(f"Live price: {live_price}")
        
        shares = float(stock_data.get('shares_outstanding', 0.0) or 0.0)
        live_cap = live_price * shares if shares > 0 else 0.0
        
        # Calculate dynamic ratios
        eff_debt = get_effective_override(stock_data, "debt_ratio_override")
        eff_cash = get_effective_override(stock_data, "cash_ratio_override")
        eff_tangibility = get_effective_override(stock_data, "tangibility_ratio_override")
        eff_int = get_effective_override(stock_data, "interest_income_override")
        eff_haram = get_effective_override(stock_data, "haram_revenue_override")
        eff_doubtful = get_effective_override(stock_data, "doubtful_revenue_override")
        
        debt_ratio = eff_debt if not pd.isna(eff_debt) else (stock_data['total_debt'] / live_cap if live_cap else 0.0)
        cash_ratio = eff_cash if not pd.isna(eff_cash) else (stock_data['cash_equivalents'] / live_cap if live_cap else 0.0)
        
        if not pd.isna(eff_tangibility):
            tang_ratio = eff_tangibility
        else:
            denom = stock_data['total_assets']
            cash_val = stock_data['cash_equivalents'] if (stock_data['cash_equivalents'] is not None and not pd.isna(stock_data['cash_equivalents'])) else 0.0
            ar_val = stock_data['accounts_receivable'] if (stock_data['accounts_receivable'] is not None and not pd.isna(stock_data['accounts_receivable'])) else 0.0
            tang_ratio = (denom - cash_val - ar_val) / denom if denom else 0.0
        
        int_ratio = eff_int if not pd.isna(eff_int) else (stock_data['interest_income'] / stock_data['total_revenue'] if stock_data['total_revenue'] else 0.0)
        haram_ratio = eff_haram if not pd.isna(eff_haram) else 0.0
        total_haram = int_ratio + haram_ratio
        doubtful_ratio = eff_doubtful if not pd.isna(eff_doubtful) else 0.0
        total_combined = total_haram + doubtful_ratio
        
        sector_lower = str(stock_data.get('sector', '')).lower()
        industry_lower = str(stock_data.get('industry', '')).lower()
        
        pass_sector = not any(s in sector_lower for s in HARAM_SECTORS)
        pass_industry = not any(i in industry_lower for i in HARAM_INDUSTRY_KEYWORDS)
        pass_debt = debt_ratio < MAX_DEBT_RATIO
        pass_cash = cash_ratio < MAX_CASH_RATIO
        pass_tangibility = tang_ratio >= MIN_TANGIBILITY_RATIO
        pass_interest = total_haram < MAX_HARAM_INCOME_RATIO
        pass_combined = total_combined < MAX_HARAM_INCOME_RATIO
        
        is_halal_live = pass_sector and pass_industry and pass_debt and pass_cash and pass_tangibility and pass_interest and pass_combined
        
        if is_halal_live:
            s_debt = debt_ratio / MAX_DEBT_RATIO
            s_cash = cash_ratio / MAX_CASH_RATIO
            s_tang = (1.0 - tang_ratio) / MAX_LIQUID_RATIO
            s_int = total_combined / MAX_HARAM_INCOME_RATIO
            
            avg_ratio = np.mean([s_debt, s_cash, s_tang, s_int])
            live_score = max(0.0, 100.0 * (1.0 - avg_ratio))
            
            if live_score >= 92: live_grade = "A+"
            elif live_score >= 85: live_grade = "A"
            elif live_score >= 78: live_grade = "B+"
            elif live_score >= 70: live_grade = "B"
            elif live_score >= 62: live_grade = "C+"
            elif live_score >= 55: live_grade = "C"
            else: live_grade = "D"
        else:
            is_doubtful_reason = pass_sector and pass_industry and pass_debt and pass_cash and pass_tangibility and pass_interest and (not pass_combined)
            if is_doubtful_reason:
                live_grade = "Doubtful"
            else:
                live_grade = "F"
            live_score = 0.0
            
        print("Calculation complete:")
        print("Live Grade:", live_grade)
        print("Live Score:", live_score)
        
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test_quote())
