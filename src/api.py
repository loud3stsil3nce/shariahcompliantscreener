import asyncio
from typing import List, Optional
import os
import json
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.db.helpers import ASYNC_DB_URL, get_db
from src.db.models import (
    Base,
    HalalUniverse,
    DoubtfulUniverse,
    HalalRejection,
    ManualOverride,
    AIOverride,
    ComplianceScan,
    TradeProposal,
    Stock
)
from src.data.ingestion import run_ingestion, fetch_stock_with_retry
from src.analysis.screener import run_screener, get_effective_override, MAX_DEBT_RATIO, MAX_CASH_RATIO, MIN_TANGIBILITY_RATIO, MAX_LIQUID_RATIO, MAX_HARAM_INCOME_RATIO, HARAM_SECTORS, HARAM_INDUSTRY_KEYWORDS
from src.analysis.optimizer import run_optimizer
from src.analysis.backtester import run_backtest

# 1. Initialize FastAPI & enable CORS
app = FastAPI(title="Shariah Screener API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Configure Async Database Connections
engine = create_async_engine(ASYNC_DB_URL)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session

# 3. Define Pydantic Models for Input Validation
class ManualOverrideInput(BaseModel):
    ticker: str
    haram_revenue_override: Optional[float] = None
    debt_ratio_override: Optional[float] = None
    cash_ratio_override: Optional[float] = None
    receivables_ratio_override: Optional[float] = None
    tangibility_ratio_override: Optional[float] = None
    interest_income_override: Optional[float] = None
    doubtful_revenue_override: Optional[float] = None
    reasoning: Optional[str] = None
    is_user_override: int = 1

class AIOverrideInput(BaseModel):
    ticker: str
    haram_revenue_estimate: Optional[float] = None
    reasoning: Optional[str] = None
    segments_found: Optional[str] = None

class PortfolioOptimizationInput(BaseModel):
    max_weight: float = 0.10
    sector_cap: float = 0.30
    strategy: str = "Max Sharpe"
    target_vol: float = 0.15
    target_ret: float = 0.15

class TradeProposalInput(BaseModel):
    symbol: str
    action: str  # BUY/SELL
    user_id: str

# 4. API Endpoints
@app.get("/api/universe/halal")
async def get_halal_universe(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(HalalUniverse))
    return result.scalars().all()

@app.get("/api/universe/doubtful")
async def get_doubtful_universe(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(DoubtfulUniverse))
    return result.scalars().all()

@app.get("/api/universe/rejected")
async def get_rejected_universe(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(HalalRejection))
    return result.scalars().all()

@app.get("/api/overrides/manual")
async def get_manual_overrides(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(ManualOverride))
    return result.scalars().all()

@app.post("/api/overrides/manual")
async def set_manual_override(data: ManualOverrideInput, db: AsyncSession = Depends(get_db_session)):
    # Merge/upsert manual override record
    override = ManualOverride(
        ticker=data.ticker.upper(),
        haram_revenue_override=data.haram_revenue_override,
        debt_ratio_override=data.debt_ratio_override,
        cash_ratio_override=data.cash_ratio_override,
        receivables_ratio_override=data.receivables_ratio_override,
        tangibility_ratio_override=data.tangibility_ratio_override,
        interest_income_override=data.interest_income_override,
        doubtful_revenue_override=data.doubtful_revenue_override,
        reasoning=data.reasoning,
        is_user_override=data.is_user_override,
        updated_at=None  # Can populate with timestamp if needed
    )
    await db.merge(override)
    await db.commit()
    # Trigger non-blocking compliance update in the background
    asyncio.create_task(asyncio.to_thread(run_screener))
    return {"status": "success", "message": f"Manual override saved for {data.ticker.upper()}"}

@app.get("/api/overrides/ai")
async def get_ai_overrides(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(AIOverride))
    return result.scalars().all()

@app.post("/api/overrides/ai")
async def set_ai_override(data: AIOverrideInput, db: AsyncSession = Depends(get_db_session)):
    override = AIOverride(
        ticker=data.ticker.upper(),
        haram_revenue_estimate=data.haram_revenue_estimate,
        reasoning=data.reasoning,
        segments_found=data.segments_found,
        updated_at=None
    )
    await db.merge(override)
    await db.commit()
    asyncio.create_task(asyncio.to_thread(run_screener))
    return {"status": "success", "message": f"AI override saved for {data.ticker.upper()}"}

@app.get("/api/compliance/scans")
async def get_compliance_scans(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(ComplianceScan).order_by(ComplianceScan.timestamp.desc()))
    return result.scalars().all()

@app.get("/api/trade/proposals")
async def get_trade_proposals(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(TradeProposal))
    return result.scalars().all()

# 5. Background Pipeline Run Handlers

@app.post("/api/pipeline/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks, refresh: bool = False):
    background_tasks.add_task(run_ingestion, refresh=refresh)
    return {"status": "queued", "message": "Yahoo Finance ingestion started in background."}

@app.post("/api/pipeline/screen")
async def trigger_screening(background_tasks: BackgroundTasks, use_current_mcap: bool = False):
    background_tasks.add_task(run_screener, use_current_mcap)
    return {"status": "queued", "message": "Compliance screening started in background."}

@app.post("/api/portfolio/optimize")
async def optimize_portfolio(data: PortfolioOptimizationInput):
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(
            None,
            lambda: run_optimizer(
                max_weight=data.max_weight,
                sector_cap=data.sector_cap,
                strategy=data.strategy,
                target_vol=data.target_vol,
                target_ret=data.target_ret
            )
        )
        if not results:
            raise HTTPException(status_code=400, detail="Optimization constraints could not be satisfied.")
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. Portfolio Visualizations & Backtest Endpoints

@app.get("/api/portfolio/frontier-chart")
async def get_frontier_chart():
    path = "efficient_frontier.png"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Efficient Frontier chart has not been generated yet.")
    return FileResponse(path, media_type="image/png")

@app.get("/api/portfolio/backtest-chart")
async def get_backtest_chart():
    path = "backtest_results.png"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Backtest results chart has not been generated yet.")
    return FileResponse(path, media_type="image/png")

class BacktestInput(BaseModel):
    months: int = 12

@app.post("/api/portfolio/backtest")
async def trigger_backtest(data: BacktestInput):
    loop = asyncio.get_running_loop()
    try:
        stats = await loop.run_in_executor(
            None,
            lambda: run_backtest(test_months=data.months)
        )
        if isinstance(stats, str) and stats.startswith("❌"):
            raise HTTPException(status_code=400, detail=stats)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 7. Stock Explorer Endpoints

@app.get("/api/stocks")
async def get_all_tickers():
    conn = get_db()
    try:
        tickers = pd.read_sql_query("SELECT ticker, name, sector FROM stocks ORDER BY ticker", conn)
        return tickers.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/stocks/{ticker}")
async def get_stock_details(ticker: str):
    ticker = ticker.upper().strip()
    conn = get_db()
    try:
        query = f"""
            SELECT s.*, 
                   COALESCE(h.grade, d.grade, r.grade, 'F') as grade,
                   COALESCE(h.compliance_score, d.compliance_score, r.compliance_score, 0.0) as compliance_score,
                   COALESCE(h.purification_per_share, d.purification_per_share, 0.0) as purification_per_share,
                   m.haram_revenue_override, m.debt_ratio_override, m.cash_ratio_override, m.receivables_ratio_override, m.tangibility_ratio_override, m.interest_income_override, m.doubtful_revenue_override, m.reasoning as override_reason, m.is_user_override,
                   c.haram_revenue_override AS cur_haram_revenue_override,
                   c.debt_ratio_override AS cur_debt_ratio_override,
                   c.cash_ratio_override AS cur_cash_ratio_override,
                   c.tangibility_ratio_override AS cur_tangibility_ratio_override,
                   c.interest_income_override AS cur_interest_income_override,
                   c.doubtful_revenue_override AS cur_doubtful_revenue_override
            FROM stocks s
            LEFT JOIN halal_universe h ON s.ticker = h.ticker
            LEFT JOIN doubtful_universe d ON s.ticker = d.ticker
            LEFT JOIN halal_rejections r ON s.ticker = r.ticker
            LEFT JOIN manual_overrides m ON s.ticker = m.ticker
            LEFT JOIN curated_benchmarks c ON s.ticker = c.ticker
            WHERE s.ticker = '{ticker}'
        """
        stock_df = pd.read_sql_query(query, conn)
        if stock_df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found.")
        return stock_df.iloc[0].to_dict()
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/stocks/{ticker}")
async def delete_stock(ticker: str):
    ticker = ticker.upper().strip()
    conn = get_db()
    try:
        conn.execute("DELETE FROM stocks WHERE ticker = ?", (ticker,))
        conn.execute("DELETE FROM manual_overrides WHERE ticker = ?", (ticker,))
        conn.commit()
        # Queue screener run
        asyncio.create_task(asyncio.to_thread(run_screener))
        return {"status": "success", "message": f"Successfully deleted {ticker} and queued screener recalculation."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/stocks/{ticker}/ingest")
async def add_custom_ticker(ticker: str):
    ticker = ticker.upper().strip()
    loop = asyncio.get_running_loop()
    try:
        data = await loop.run_in_executor(
            None,
            lambda: fetch_stock_with_retry(ticker)
        )
        if not data:
            raise HTTPException(status_code=400, detail=f"Could not find ticker '{ticker}' on Yahoo Finance.")
        
        conn = get_db()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO stocks (
                    ticker, name, sector, industry,
                    total_assets, total_debt, cash_equivalents, accounts_receivable,
                    total_revenue, interest_income,
                    shares_outstanding, avg_market_cap_36mo, raw_info, sec_filing_url, fetched_at
                ) VALUES (
                    :ticker, :name, :sector, :industry,
                    :total_assets, :total_debt, :cash_equivalents, :accounts_receivable,
                    :total_revenue, :interest_income,
                    :shares_outstanding, :avg_market_cap_36mo, :raw_info, :sec_filing_url, :fetched_at
                )""",
                data,
            )
            conn.commit()
        finally:
            conn.close()
            
        # Run screener in backend
        await loop.run_in_executor(None, lambda: run_screener(use_current_market_cap=False))
        return {"status": "success", "message": f"Successfully ingested and screened {ticker}!"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stocks/{ticker}/quote")
async def get_realtime_quote(ticker: str):
    ticker = ticker.upper().strip()
    
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
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found in database. Ingest it first.")
        stock_data = stock_df.iloc[0]
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
            
        live_price = await loop.run_in_executor(None, fetch_yf_price)
        if not live_price:
            raise HTTPException(status_code=500, detail=f"Could not fetch real-time price for {ticker}.")
            
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
            
        return {
            "ticker": ticker,
            "live_price": float(live_price) if live_price is not None else None,
            "live_market_cap": float(live_cap),
            "live_grade": str(live_grade),
            "live_score": float(live_score),
            "debt_ratio": float(debt_ratio),
            "cash_ratio": float(cash_ratio),
            "tangibility_ratio": float(tang_ratio),
            "interest_income_ratio": float(int_ratio),
            "haram_revenue_ratio": float(haram_ratio),
            "total_haram_ratio": float(total_haram),
            "doubtful_revenue_ratio": float(doubtful_ratio),
            "total_combined_ratio": float(total_combined),
            "pass_sector": bool(pass_sector),
            "pass_industry": bool(pass_industry),
            "pass_debt": bool(pass_debt),
            "pass_cash": bool(pass_cash),
            "pass_tangibility": bool(pass_tangibility),
            "pass_interest": bool(pass_interest),
            "pass_combined": bool(pass_combined)
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

class AuditInput(BaseModel):
    audit_type: str  # 'standard', 'source_backed', or 'multi_source'

@app.post("/api/stocks/{ticker}/audit")
async def run_ai_audit(ticker: str, data: AuditInput):
    ticker = ticker.upper().strip()
    
    conn = get_db()
    try:
        stock_df = pd.read_sql_query(f"SELECT * FROM stocks WHERE ticker = '{ticker}'", conn)
        if stock_df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found.")
        stock_data = stock_df.iloc[0]
    finally:
        conn.close()
        
    loop = asyncio.get_running_loop()
    try:
        db_financials = {
            'total_revenue': stock_data.get('total_revenue', 0.0) or 0.0,
            'total_debt': stock_data.get('total_debt', 0.0) or 0.0,
            'cash_equivalents': stock_data.get('cash_equivalents', 0.0) or 0.0,
            'interest_income': stock_data.get('interest_income', 0.0) or 0.0
        }
        
        raw_info = json.loads(stock_data['raw_info']) if stock_data.get('raw_info') else {}
        business_summary = raw_info.get('longBusinessSummary', "No summary available.")
        
        source_text = ""
        source_url = ""
        harvested = None
        
        if data.audit_type == "source_backed":
            from src.data.sec_extractor import get_latest_10k_text
            def get_sec():
                return get_latest_10k_text(ticker)
            source_text, source_url = await loop.run_in_executor(None, get_sec)
            if not source_text:
                raise HTTPException(status_code=400, detail=f"Could not retrieve SEC filings for {ticker}.")
                
        elif data.audit_type == "multi_source":
            from src.data.sec_extractor import get_latest_10k_text
            from src.data.harvester import harvest_all_sources
            
            def get_sec():
                return get_latest_10k_text(ticker)
            source_text, source_url = await loop.run_in_executor(None, get_sec)
            
            def run_harvester():
                import asyncio
                loop2 = asyncio.new_event_loop()
                try:
                    return loop2.run_until_complete(harvest_all_sources(ticker, year=2025, quarter=4, sec_text=source_text))
                finally:
                    loop2.close()
            harvested = await loop.run_in_executor(None, run_harvester)
            if not harvested or not harvested.get("chunks"):
                raise HTTPException(status_code=400, detail="Could not harvest transcripts or search supplement chunks.")
                
        from src.analysis.ai_analyst import analyze_company_compliance
        from src.db.setup import save_proposed_rules
        
        def run_ai_verdict():
            if data.audit_type == "multi_source":
                from src.analysis.ai_analyst import analyze_multi_source_compliance
                return analyze_multi_source_compliance(ticker, stock_data['name'], harvested, summary=business_summary)
            else:
                return analyze_company_compliance(ticker, stock_data['name'], business_summary if data.audit_type == "standard" else "", source_text=source_text, db_financials=db_financials)
                
        ai_res = await loop.run_in_executor(None, run_ai_verdict)
        if not isinstance(ai_res, dict) or "error" in ai_res:
            err_msg = ai_res.get("error") if isinstance(ai_res, dict) else str(ai_res)
            raise HTTPException(status_code=500, detail=f"AI model verdict failed: {err_msg}")
            
        mc_denom_save = stock_data['avg_market_cap_36mo'] or 1.0
        filing_period = ai_res.get('filing_period_months', 12) or 12
        scale_factor = 12.0 / filing_period
        
        total_rev_m = (ai_res.get('total_revenue_millions', 1.0) or 1.0) * scale_factor
        haram_rev_m = (ai_res.get('haram_revenue_millions', 0.0) or 0.0) * scale_factor
        doubtful_rev_m = (ai_res.get('doubtful_revenue_millions', 0.0) or 0.0) * scale_factor
        int_inc_m = (ai_res.get('interest_income_millions', 0.0) or 0.0) * scale_factor
        
        final_haram_rev = haram_rev_m / total_rev_m
        final_doubtful_rev = doubtful_rev_m / total_rev_m
        final_int_inc_ratio = int_inc_m / total_rev_m
        cash_and_securities_m = ai_res.get('total_cash_and_securities_millions', 0.0) or 0.0
        if final_int_inc_ratio == 0.0 and stock_data['total_revenue'] and stock_data['total_revenue'] > 0.0:
            final_int_inc_ratio = (stock_data['interest_income'] or 0.0) / stock_data['total_revenue']
            
        final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_denom_save
        final_cash_ratio = (cash_and_securities_m * 1e6) / mc_denom_save
        
        conn_db = get_db()
        try:
            conn_db.execute("""
                INSERT OR REPLACE INTO manual_overrides 
                (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                ticker, 
                final_haram_rev, 
                final_debt_ratio, 
                final_cash_ratio, 
                final_int_inc_ratio,
                final_doubtful_rev,
                json.dumps(ai_res),
                pd.Timestamp.now().isoformat()
            ))
            conn_db.commit()
            save_proposed_rules(ticker, ai_res)
        finally:
            conn_db.close()
            
        await loop.run_in_executor(None, lambda: run_screener(use_current_market_cap=False))
        
        return {
            "status": "success", 
            "message": "AI Audit complete, saved, and screener updated.",
            "verdict": ai_res
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stocks/{ticker}/upload-audit")
async def run_document_upload_audit(ticker: str, file: UploadFile = File(...)):
    ticker = ticker.upper().strip()
    
    conn = get_db()
    try:
        stock_df = pd.read_sql_query(f"SELECT * FROM stocks WHERE ticker = '{ticker}'", conn)
        if stock_df.empty:
            raise HTTPException(status_code=404, detail=f"Stock {ticker} not found.")
        stock_data = stock_df.iloc[0]
    finally:
        conn.close()
        
    loop = asyncio.get_running_loop()
    try:
        contents = await file.read()
        file_name = file.filename or "uploaded_report.pdf"
        
        def parse_doc():
            if file_name.lower().endswith(".pdf"):
                import pypdf
                import io
                pdf_file = io.BytesIO(contents)
                reader = pypdf.PdfReader(pdf_file)
                pages_text = []
                for page in reader.pages:
                    p_txt = page.extract_text()
                    if p_txt:
                        pages_text.append(p_txt)
                return "\n".join(pages_text)
            else:
                return contents.decode("utf-8", errors="ignore")
                
        raw_text = await loop.run_in_executor(None, parse_doc)
        if not raw_text:
            raise HTTPException(status_code=400, detail="Could not extract text from document.")
            
        from src.data.sec_extractor import SECParser
        parser = SECParser()
        source_text = parser.extract_relevant_sections(raw_text, max_chars=300000)
        
        from src.analysis.ai_analyst import analyze_company_compliance
        from src.db.setup import save_proposed_rules
        
        db_financials = {
            'total_revenue': stock_data.get('total_revenue', 0.0) or 0.0,
            'total_debt': stock_data.get('total_debt', 0.0) or 0.0,
            'cash_equivalents': stock_data.get('cash_equivalents', 0.0) or 0.0,
            'interest_income': stock_data.get('interest_income', 0.0) or 0.0
        }
        
        def run_verdict():
            return analyze_company_compliance(ticker, stock_data['name'], "", source_text=source_text, db_financials=db_financials)
            
        ai_res = await loop.run_in_executor(None, run_verdict)
        if not isinstance(ai_res, dict) or "error" in ai_res:
            err_msg = ai_res.get("error") if isinstance(ai_res, dict) else str(ai_res)
            raise HTTPException(status_code=500, detail=f"AI model verdict on upload failed: {err_msg}")
            
        mc_denom_save = stock_data['avg_market_cap_36mo'] or 1.0
        filing_period = ai_res.get('filing_period_months', 12) or 12
        scale_factor = 12.0 / filing_period
        
        total_rev_m = (ai_res.get('total_revenue_millions', 1.0) or 1.0) * scale_factor
        haram_rev_m = (ai_res.get('haram_revenue_millions', 0.0) or 0.0) * scale_factor
        doubtful_rev_m = (ai_res.get('doubtful_revenue_millions', 0.0) or 0.0) * scale_factor
        int_inc_m = (ai_res.get('interest_income_millions', 0.0) or 0.0) * scale_factor
        
        final_haram_rev = haram_rev_m / total_rev_m
        final_doubtful_rev = doubtful_rev_m / total_rev_m
        final_int_inc_ratio = int_inc_m / total_rev_m
        cash_and_securities_m = ai_res.get('total_cash_and_securities_millions', 0.0) or 0.0
        if final_int_inc_ratio == 0.0 and stock_data['total_revenue'] and stock_data['total_revenue'] > 0.0:
            final_int_inc_ratio = (stock_data['interest_income'] or 0.0) / stock_data['total_revenue']
            
        final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_denom_save
        final_cash_ratio = (cash_and_securities_m * 1e6) / mc_denom_save
        
        conn_db = get_db()
        try:
            conn_db.execute("""
                INSERT OR REPLACE INTO manual_overrides 
                (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                ticker, 
                final_haram_rev, 
                final_debt_ratio, 
                final_cash_ratio, 
                final_int_inc_ratio,
                final_doubtful_rev,
                json.dumps(ai_res),
                pd.Timestamp.now().isoformat()
            ))
            conn_db.commit()
            save_proposed_rules(ticker, ai_res)
        finally:
            conn_db.close()
            
        await loop.run_in_executor(None, lambda: run_screener(use_current_market_cap=False))
        
        return {
            "status": "success",
            "message": f"Successfully parsed and audited document: {file_name}",
            "verdict": ai_res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 8. Shariah Segment Rules Endpoints

@app.get("/api/rules/ticker-rules")
async def get_ticker_specific_rules():
    conn = get_db()
    try:
        rules = pd.read_sql_query("SELECT ticker, segment_name, compliance_status, notes FROM shariah_segment_map ORDER BY ticker, segment_name", conn)
        return rules.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/rules/global-rules")
async def get_global_keyword_rules():
    conn = get_db()
    try:
        rules = pd.read_sql_query("SELECT pattern, compliance_status, notes FROM global_segment_patterns ORDER BY pattern", conn)
        return rules.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# 9. MCP Status Endpoint

@app.get("/api/mcp/status")
async def get_mcp_status():
    status_path = "status.json"
    if not os.path.exists(status_path):
        raise HTTPException(status_code=404, detail="MCP Agent status file not found.")
    try:
        with open(status_path, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read telemetry status: {str(e)}")