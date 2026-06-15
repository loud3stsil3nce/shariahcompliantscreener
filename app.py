import streamlit as st
import pandas as pd
import os
import json
from src.ingestion import run_ingestion
from src.screener import run_screener
from src.optimizer import run_optimizer
from src.backtester import run_backtest
from src.utils import get_db

# Initialize database tables if they don't exist
def init_db_tables():
    conn = get_db()
    # USE executescript for multiple statements or safer schema management
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ai_overrides (
            ticker TEXT PRIMARY KEY,
            haram_revenue_estimate REAL,
            reasoning TEXT,
            segments_found TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS manual_overrides (
            ticker TEXT PRIMARY KEY,
            haram_revenue_override REAL,
            debt_ratio_override REAL,
            cash_ratio_override REAL,
            receivables_ratio_override REAL,
            interest_income_override REAL,
            doubtful_revenue_override REAL,
            reasoning TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS halal_universe (
            ticker TEXT PRIMARY KEY,
            grade TEXT,
            compliance_score REAL,
            purification_per_share REAL
        );
        CREATE TABLE IF NOT EXISTS halal_rejections (
            ticker TEXT PRIMARY KEY,
            grade TEXT,
            compliance_score REAL,
            purification_per_share REAL
        );
    """)
    
    # Schema migration: check if stocks table exists and has sec_filing_url column
    table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'").fetchone()
    if table_check:
        cursor = conn.execute("PRAGMA table_info(stocks)")
        columns = [row[1] for row in cursor.fetchall()]
        if "sec_filing_url" not in columns:
            conn.execute("ALTER TABLE stocks ADD COLUMN sec_filing_url TEXT")
            
    # Schema migration for manual_overrides: check if doubtful_revenue_override exists
    mo_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='manual_overrides'").fetchone()
    if mo_check:
        cursor = conn.execute("PRAGMA table_info(manual_overrides)")
        columns = [row[1] for row in cursor.fetchall()]
        if "doubtful_revenue_override" not in columns:
            conn.execute("ALTER TABLE manual_overrides ADD COLUMN doubtful_revenue_override REAL")
            
    conn.commit()
    conn.close()

init_db_tables()

st.set_page_config(page_title="Halal Stock Screener & Optimizer", layout="wide")

# Custom CSS for a cleaner look
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stMetric {
        background-color: #ffffff !important;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #E2E8F0;
    }
    [data-testid="stMetricLabel"] {
        color: #475569 !important;
        font-weight: 500 !important;
    }
    [data-testid="stMetricValue"] {
        color: #0F172A !important;
        font-weight: 700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🌙 Halal Stock Screener & Portfolio Optimizer")
st.markdown("""
This application helps you build a Shariah-compliant investment portfolio using 
Modern Portfolio Theory (MPT) with added safety constraints.
""")

# Sidebar for Controls
st.sidebar.header("⚙️ Control Panel")

# 1. Ingestion
st.sidebar.subheader("1. Data Ingestion")
use_current_mcap = False

if st.sidebar.button("Fetch Latest Data"):
    with st.spinner("Fetching data from Yahoo Finance..."):
        run_ingestion(refresh=True)
    with st.spinner("Running compliance screening..."):
        run_screener(use_current_market_cap=use_current_mcap)
    st.sidebar.success("Ingestion & Screening Complete!")

# 2. Screener
st.sidebar.subheader("2. Shariah Screening")

if st.sidebar.button("Run Screener"):
    with st.spinner("Screening stocks for compliance..."):
        try:
            run_screener(use_current_market_cap=use_current_mcap)
            st.sidebar.success("Screening Complete!")
        except Exception as e:
            st.sidebar.error(f"Screener failed: {e}")
            st.sidebar.info("Try running 'Fetch Latest Data' first.")

# 2.5 AI Global Audit
st.sidebar.subheader("2.5 AI Global Audit")
st.sidebar.caption("To perform a bulk qualitative audit on all stocks safely without browser timeout or session interruption, run this command in your terminal:")
st.sidebar.code("PYTHONPATH=. ./venv/bin/python src/batch_ai_audit.py", language="bash")

# 3. Optimizer Settings
st.sidebar.subheader("3. Portfolio Optimization")
opt_strategy = st.sidebar.selectbox(
    "Optimization Strategy",
    ["Max Sharpe Ratio", "Minimum Volatility", "Target Volatility", "Target Return"],
    help="Max Sharpe: balance return/risk. Min Volatility: minimize risk. Target Volatility: maximize return for a risk level. Target Return: minimize risk for a return level."
)

target_vol = 0.15
target_ret = 0.15

if opt_strategy == "Target Volatility":
    target_vol = st.sidebar.slider("Target Volatility (%)", 5.0, 40.0, 15.0, step=1.0, help="Constraint: Portfolio volatility will not exceed this limit.") / 100.0
elif opt_strategy == "Target Return":
    target_ret = st.sidebar.slider("Target Expected Return (%)", 5.0, 40.0, 15.0, step=1.0, help="Constraint: Portfolio expected return will meet or exceed this limit.") / 100.0

max_stock_weight = st.sidebar.slider("Max Weight per Stock", 0.05, 0.20, 0.10, help="Maximum allocation allowed for a single company.")
max_sector_weight = st.sidebar.slider("Max Weight per Sector", 0.10, 0.50, 0.30, help="Maximum allocation allowed for a single industry sector.")
invest_amount = st.sidebar.number_input("Investment Amount ($)", min_value=1000, value=10000, step=1000)

if "optimizer_results" not in st.session_state:
    st.session_state.optimizer_results = None

if st.sidebar.button("Optimize Portfolio"):
    with st.spinner("Calculating optimal weights..."):
        try:
            opt_strategy_map = {
                "Max Sharpe Ratio": "Max Sharpe",
                "Minimum Volatility": "Min Volatility",
                "Target Volatility": "Target Volatility",
                "Target Return": "Target Return"
            }
            backend_strategy = opt_strategy_map[opt_strategy]
            results = run_optimizer(
                max_weight=max_stock_weight, 
                sector_cap=max_sector_weight, 
                strategy=backend_strategy,
                target_vol=target_vol,
                target_ret=target_ret
            )
            if results:
                st.session_state.optimizer_results = results
                st.sidebar.success("Optimization Complete!")
            else:
                st.sidebar.error("Optimization failed. The constraints could not be satisfied. Try lowering your Target Return, raising your Target Volatility, or increasing Max Weight limits.")
        except Exception as e:
            st.sidebar.error(f"Optimization failed: {e}")

# Main Area Layout
tab1, tab2, tab3, tab4 = st.tabs(["📊 Portfolio Dashboard", "📋 Halal Universe", "⏳ Historical Backtest", "🔍 Stock Explorer"])

with tab1:
    if st.session_state.optimizer_results:
        res = st.session_state.optimizer_results
        m1, m2, m3 = st.columns(3)
        m1.metric("Expected Annual Return", f"{res['expected_return']:.2%}")
        m2.metric("Annual Volatility (Risk)", f"{res['volatility']:.2%}")
        m3.metric("Purification (Total)", f"${(res['purification_per_1000'] * invest_amount / 1000):.2f}")

        col_left, col_right = st.columns([1, 1])
        with col_left:
            st.subheader("📈 Efficient Frontier")
            if os.path.exists("efficient_frontier.png"):
                st.image("efficient_frontier.png", width='stretch')
            st.subheader("🏢 Sector Exposure")
            sector_df = res['sector_exposure'].reset_index()
            sector_df.columns = ["Sector", "Weight"]
            st.dataframe(sector_df.style.format({"Weight": "{:.2%}"}), width='stretch', hide_index=True)
        with col_right:
            st.subheader("💰 Target Allocation")
            alloc_df = res['allocation'].reset_index()
            alloc_df.columns = ["Ticker", "Weight"]
            alloc_df["Dollar Amount"] = alloc_df["Weight"] * invest_amount
            st.dataframe(alloc_df.style.format({"Weight": "{:.2%}", "Dollar Amount": "${:,.2f}"}), width='stretch', hide_index=True)

        st.write("---")
        st.subheader("🧮 Interactive Portfolio Purification Calculator")
        
        prices_dict = res.get('prices')
        purification_map = res.get('purification_map')
        
        if prices_dict is None or purification_map is None:
            st.warning("⚠️ Stale optimization results detected. Please click the **Optimize Portfolio** button in the sidebar to load pricing data and enable the interactive calculator.")
        else:
            st.markdown("""
            Review or customize your share holdings below to calculate your exact Shariah purification / donation obligations.
            *You can edit the **Current Share Count** column directly in the table to match your actual portfolio holdings!*
            """)

            # Build DataFrame for data_editor
            calc_data = []
            for ticker, weight in res['allocation'].items():
                price = prices_dict.get(ticker, 1.0)
                target_shares = round((invest_amount * weight) / price, 4)
                pur_share = purification_map.get(ticker, 0.0)
                calc_data.append({
                    "Ticker": ticker,
                    "Price ($)": round(price, 2),
                    "Target Weight (%)": weight * 100.0,
                    "Current Share Count": target_shares,
                    "Purification / Share ($)": pur_share,
                    "Purification Total ($)": round(target_shares * pur_share, 4)
                })
            
            calc_df = pd.DataFrame(calc_data)
            
            # Display editable table
            edited_df = st.data_editor(
                calc_df,
                column_config={
                    "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
                    "Price ($)": st.column_config.NumberColumn("Current Price ($)", format="$%.2f", disabled=True),
                    "Target Weight (%)": st.column_config.NumberColumn("Target Weight (%)", format="%.2f%%", disabled=True),
                    "Current Share Count": st.column_config.NumberColumn("Current Share Count (Editable)", min_value=0.0, step=0.0001, format="%.4f"),
                    "Purification / Share ($)": st.column_config.NumberColumn("Purification / Share ($)", format="$%.4f", disabled=True),
                    "Purification Total ($)": st.column_config.NumberColumn("Purification Total ($)", format="$%.4f", disabled=True),
                },
                hide_index=True,
                use_container_width=True,
                key="purification_calculator"
            )
            
            # Recalculate based on user edits
            edited_df["Purification Total ($)"] = edited_df["Current Share Count"] * edited_df["Purification / Share ($)"]
            total_purification = edited_df["Purification Total ($)"].sum()
            
            st.markdown(f"""
            <div style="background-color: #ECFDF5; border: 1px solid #10B981; border-radius: 8px; padding: 15px; text-align: center; margin-top: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <span style="font-size: 1.1rem; font-weight: 600; color: #065F46; display: block; margin-bottom: 5px;">Total Donation/Purification Obligation</span>
                <h2 style="color: #047857; margin: 0; font-weight: 800; font-size: 2.2rem; display: inline-block;">${total_purification:,.2f}</h2>
                <p style="color: #065F46; font-size: 0.85rem; margin: 8px 0 0 0; line-height: 1.4;">
                    Purification is calculated as: <code>Shares × Purification Per Share</code> for each holding.
                    Purified earnings should be donated to clean water, medical aid, housing, or other humanitarian causes of your choice.
                </p>
            </div>
            """, unsafe_allow_html=True)

    else:
        st.info("👈 Set your constraints in the sidebar and click 'Optimize Portfolio' to begin.")

with tab2:
    st.header("📋 Halal Universe Data")
    conn = get_db()
    try:
        df_halal = pd.read_sql_query("SELECT ticker, name, sector, grade, debt_ratio, purification_per_share FROM halal_universe", conn)
        def color_grade(val):
            color = 'green' if val.startswith('A') else 'orange' if val.startswith('B') or val.startswith('C') else 'red'
            return f'color: {color}; font-weight: bold'
        st.dataframe(df_halal.style.map(color_grade, subset=['grade']).format({"debt_ratio": "{:.2%}", "purification_per_share": "${:.4f}"}), width='stretch', hide_index=True)
    except Exception:
        st.info("Run the Screener first.")
    finally:
        conn.close()

with tab3:
    st.header("⏳ Historical Performance Simulation")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        test_window = st.selectbox("Simulation Window (Months)", [6, 12, 18, 24], index=1)
        if st.button("🚀 Run Simulation"):
            with st.spinner("Running simulation..."):
                backtest_results = run_backtest(test_months=test_window)
                if isinstance(backtest_results, dict):
                    st.session_state.backtest_results = backtest_results
                else:
                    st.error(backtest_results)
        if "backtest_results" in st.session_state:
            br = st.session_state.backtest_results
            st.metric("Portfolio Return", f"{br['portfolio_return']:.1%}")
            st.metric("S&P 500 Return", f"{br['spy_return']:.1%}")
            st.metric("Sharpe Ratio", f"{br['sharpe']:.2f}")
    with col_b:
        if "backtest_results" in st.session_state and os.path.exists("backtest_results.png"):
            st.image("backtest_results.png", width='stretch')

with tab4:
    st.header("🔍 Individual Stock Explorer")
    conn = get_db()
    try:
        all_tickers = pd.read_sql_query("SELECT ticker FROM stocks ORDER BY ticker", conn)["ticker"].tolist()
        
        # Add Custom Ticker section
        with st.expander("➕ Add Custom Ticker to Database"):
            c_col1, c_col2 = st.columns([3, 1])
            with c_col1:
                custom_ticker = st.text_input("Enter Ticker Symbol (e.g. TSLA, NVDA, BABA, ARM)", "").upper().strip()
            with c_col2:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                add_btn = st.button("Add & Ingest", use_container_width=True)
            
            if add_btn and custom_ticker:
                if custom_ticker in all_tickers:
                    st.info(f"Ticker {custom_ticker} is already in the database!")
                else:
                    with st.spinner(f"Ingesting {custom_ticker} from Yahoo Finance..."):
                        from src.ingestion import fetch_stock_with_retry
                        data = fetch_stock_with_retry(custom_ticker)
                        if data:
                            conn_add = get_db()
                            conn_add.execute(
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
                            conn_add.commit()
                            conn_add.close()
                            
                            # Run screener
                            run_screener(use_current_market_cap=False)
                            st.success(f"Successfully ingested and screened {custom_ticker}!")
                            st.rerun()
                        else:
                            st.error(f"Could not find ticker '{custom_ticker}' on Yahoo Finance. Please verify the symbol.")
                            
        search_ticker = st.selectbox("Search for a Ticker", [""] + all_tickers)
        
        if search_ticker:
            query = f"""
                SELECT s.*, 
                       COALESCE(h.grade, r.grade, 'F') as grade,
                       COALESCE(h.compliance_score, r.compliance_score, 0.0) as compliance_score,
                       COALESCE(h.purification_per_share, 0.0) as purification_per_share,
                       m.haram_revenue_override, m.debt_ratio_override, m.cash_ratio_override, m.interest_income_override, m.doubtful_revenue_override, m.reasoning as override_reason
                FROM stocks s
                LEFT JOIN halal_universe h ON s.ticker = h.ticker
                LEFT JOIN halal_rejections r ON s.ticker = r.ticker
                LEFT JOIN manual_overrides m ON s.ticker = m.ticker
                WHERE s.ticker = '{search_ticker}'
            """
            stock_data = pd.read_sql_query(query, conn).iloc[0]
            
            c1, c2 = st.columns([3, 1])
            with c1:
                st.title(f"{stock_data['ticker']}: {stock_data['name']}")
                st.caption(f"{stock_data['sector']} | {stock_data['industry']}")
                
                # Delete stock from database
                if st.button(f"🗑️ Delete {search_ticker} from Database", key=f"del_{search_ticker}", help="Permanently delete this stock and all its overrides from the local database."):
                    conn_del = get_db()
                    try:
                        conn_del.execute("DELETE FROM stocks WHERE ticker = ?", (search_ticker,))
                        conn_del.execute("DELETE FROM manual_overrides WHERE ticker = ?", (search_ticker,))
                        conn_del.commit()
                        run_screener(use_current_market_cap=False)
                        st.success(f"Successfully deleted {search_ticker} and updated screener universe!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete stock: {e}")
                    finally:
                        conn_del.close()
            with c2:
                grade = stock_data['grade'] or "F"
                if grade == "Doubtful":
                    border_color = "#D2691E"
                    text_color = "#D2691E"
                elif grade == "F":
                    border_color = "#EF4444"
                    text_color = "#EF4444"
                else:
                    border_color = "#10B981"
                    text_color = "#10B981"
                st.markdown(f"<h1 style='text-align: center; border: 2px solid {border_color}; color: {text_color}; border-radius: 10px;'>{grade}</h1>", unsafe_allow_html=True)

            st.divider()
            d1, d2 = st.columns(2)
            with d1:
                st.subheader("📝 Business Summary")
                raw_info = json.loads(stock_data['raw_info'])
                business_summary = raw_info.get('longBusinessSummary', "No summary available.")
                st.write(business_summary)
                
                st.divider()
                if stock_data.get('sec_filing_url'):
                    st.link_button("📄 View Latest SEC 10-K Filings", stock_data['sec_filing_url'])

                st.subheader("🤖 AI Analyst Deep Scan")

                # --- NEW: SOURCE-BACKED AUDIT ---
                if st.button("🔬 Source-Backed Deep Audit (Very Accurate)"):
                    from src.sec_extractor import get_latest_10k_text
                    from src.ai_analyst import analyze_company_compliance

                    with st.spinner(f"🔍 Locating and downloading latest annual report (10-K/20-F) for {stock_data['ticker']} on SEC EDGAR..."):
                        source_text, source_url = get_latest_10k_text(stock_data['ticker'])

                    if source_text:
                        filename = source_url.split('/')[-1]
                        f_type = "20-F" if "20f" in source_url.lower() or "20-f" in source_url.lower() else "10-K"
                        st.info(f"📄 Found SEC Form {f_type}: `{filename}`")
                        
                        with st.spinner(f"🧠 AI is auditing {f_type} filing ({filename}) (up to 2M chars)..."):
                            db_financials = {
                                'total_revenue': stock_data.get('total_revenue', 0.0) or 0.0,
                                'total_debt': stock_data.get('total_debt', 0.0) or 0.0,
                                'cash_equivalents': stock_data.get('cash_equivalents', 0.0) or 0.0,
                                'interest_income': stock_data.get('interest_income', 0.0) or 0.0
                            }
                            ai_res = analyze_company_compliance(
                                stock_data['ticker'], 
                                stock_data['name'], 
                                "", 
                                source_text=source_text,
                                db_financials=db_financials
                            )
                            if "error" not in ai_res:
                                st.session_state[f"ai_scan_{search_ticker}"] = ai_res
                                
                                # --- AUTOMATIC SAVE AND SCREENER WORKFLOW ---
                                mc_denom_save = stock_data['avg_market_cap_36mo'] or 1.0
                                total_rev_m = ai_res.get('total_revenue_millions', 1.0) or 1.0
                                
                                # Use absolute values to avoid transposition errors
                                final_haram_rev = ai_res.get('haram_revenue_millions', 0.0) / total_rev_m
                                final_doubtful_rev = ai_res.get('doubtful_revenue_millions', 0.0) / total_rev_m
                                
                                # Deduce interest income if reported as 0.0 but company has cash assets
                                final_int_inc_ratio = ai_res.get('interest_income_millions', 0.0) / total_rev_m
                                cash_and_securities_m = ai_res.get('total_cash_and_securities_millions', 0.0) or 0.0
                                if final_int_inc_ratio == 0.0 and cash_and_securities_m > 0.0:
                                    annual_rev_m = (stock_data.get('total_revenue', 0.0) or 1.0) / 1e6
                                    final_int_inc_ratio = (cash_and_securities_m * 0.03) / annual_rev_m
                                
                                final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_denom_save
                                # Use the total liquid assets (cash + securities) for the cash screen ratio
                                final_cash_ratio = (cash_and_securities_m * 1e6) / mc_denom_save
                                
                                conn_s = get_db()
                                try:
                                    conn_s.execute("""
                                        INSERT OR REPLACE INTO manual_overrides 
                                        (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, updated_at)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        search_ticker, 
                                        final_haram_rev, 
                                        final_debt_ratio, 
                                        final_cash_ratio, 
                                        final_int_inc_ratio,
                                        final_doubtful_rev,
                                        json.dumps(ai_res), # Save full structured AI JSON response
                                        pd.Timestamp.now().isoformat()
                                    ))
                                    conn_s.commit()
                                    run_screener(use_current_market_cap=False)
                                    st.sidebar.success(f"Audit complete using source: {source_url}")
                                    st.success("✅ Audit completed, saved, and screener updated automatically!")
                                    st.rerun()
                                finally:
                                    conn_s.close()
                            else:
                                st.error(ai_res["error"])
                    else:
                        st.error(f"Could not retrieve filing: {source_url}")

                if st.button("🔍 Standard AI Analysis (Fast)"):
                    from src.ai_analyst import analyze_company_compliance

                    db_financials = {
                        'total_revenue': stock_data.get('total_revenue', 0.0) or 0.0,
                        'total_debt': stock_data.get('total_debt', 0.0) or 0.0,
                        'cash_equivalents': stock_data.get('cash_equivalents', 0.0) or 0.0,
                        'interest_income': stock_data.get('interest_income', 0.0) or 0.0
                    }
                    with st.spinner("🧠 Performing standard AI analysis..."):
                        ai_res = analyze_company_compliance(
                            stock_data['ticker'], 
                            stock_data['name'], 
                            business_summary,
                            db_financials=db_financials
                        )
                        if "error" not in ai_res: 
                            st.session_state[f"ai_scan_{search_ticker}"] = ai_res
                            
                            # --- AUTOMATIC SAVE AND SCREENER WORKFLOW ---
                            mc_denom_save = stock_data['avg_market_cap_36mo'] or 1.0
                            total_rev_m = ai_res.get('total_revenue_millions', 1.0) or 1.0
                            
                            # Use absolute values to avoid transposition errors
                            final_haram_rev = ai_res.get('haram_revenue_millions', 0.0) / total_rev_m
                            final_doubtful_rev = ai_res.get('doubtful_revenue_millions', 0.0) / total_rev_m
                            
                            # Deduce interest income if reported as 0.0 but company has cash assets
                            final_int_inc_ratio = ai_res.get('interest_income_millions', 0.0) / total_rev_m
                            cash_and_securities_m = ai_res.get('total_cash_and_securities_millions', 0.0) or 0.0
                            if final_int_inc_ratio == 0.0 and cash_and_securities_m > 0.0:
                                annual_rev_m = (stock_data.get('total_revenue', 0.0) or 1.0) / 1e6
                                final_int_inc_ratio = (cash_and_securities_m * 0.03) / annual_rev_m
                            
                            final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_denom_save
                            # Use the total liquid assets (cash + securities) for the cash screen ratio
                            final_cash_ratio = (cash_and_securities_m * 1e6) / mc_denom_save
                            
                            conn_s = get_db()
                            try:
                                conn_s.execute("""
                                    INSERT OR REPLACE INTO manual_overrides 
                                    (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    search_ticker, 
                                    final_haram_rev, 
                                    final_debt_ratio, 
                                    final_cash_ratio, 
                                    final_int_inc_ratio,
                                    final_doubtful_rev,
                                    json.dumps(ai_res), # Save full structured AI JSON response
                                    pd.Timestamp.now().isoformat()
                                ))
                                conn_s.commit()
                                run_screener(use_current_market_cap=False)
                                st.success("✅ Audit completed, saved, and screener updated automatically!")
                                st.rerun()
                            finally:
                                conn_s.close()

                st.write("---")
                with st.expander("📤 Universal Document Uploader (PDF / TXT)"):
                    st.markdown("""
                    Upload any annual report, prospectus, or financial statement (PDF/TXT) to analyze.
                    This is particularly useful for international listings or new IPOs not indexed on SEC EDGAR.
                    """)
                    uploaded_file = st.file_uploader(
                        "Choose a PDF or TXT file",
                        type=["pdf", "txt"],
                        key=f"doc_uploader_{search_ticker}"
                    )
                    
                    if uploaded_file is not None:
                        file_name = uploaded_file.name
                        if st.button("🚀 Run AI Audit on Document", key=f"btn_audit_doc_{search_ticker}"):
                            with st.spinner("Extracting text from uploaded document..."):
                                try:
                                    if file_name.lower().endswith(".pdf"):
                                        import pypdf
                                        reader = pypdf.PdfReader(uploaded_file)
                                        pages_text = []
                                        for idx, page in enumerate(reader.pages):
                                            page_text = page.extract_text()
                                            if page_text:
                                                pages_text.append(page_text)
                                        raw_text = "\n".join(pages_text)
                                        st.info(f"Parsed {len(reader.pages)} PDF pages successfully (Total {len(raw_text)} characters).")
                                    else:
                                        raw_text = uploaded_file.read().decode("utf-8", errors="ignore")
                                        st.info(f"Read TXT file successfully (Total {len(raw_text)} characters).")
                                    
                                    from src.sec_extractor import SECParser
                                    parser = SECParser()
                                    source_text = parser.extract_relevant_sections(raw_text, max_chars=300000)
                                    st.info(f"Filtered to {len(source_text)} relevant characters using Shariah heuristics.")
                                    
                                    with st.spinner("🧠 Gemini is auditing the extracted document..."):
                                        from src.ai_analyst import analyze_company_compliance
                                        db_financials = {
                                            'total_revenue': stock_data.get('total_revenue', 0.0) or 0.0,
                                            'total_debt': stock_data.get('total_debt', 0.0) or 0.0,
                                            'cash_equivalents': stock_data.get('cash_equivalents', 0.0) or 0.0,
                                            'interest_income': stock_data.get('interest_income', 0.0) or 0.0
                                        }
                                        ai_res = analyze_company_compliance(
                                            stock_data['ticker'], 
                                            stock_data['name'], 
                                            "", 
                                            source_text=source_text,
                                            db_financials=db_financials
                                        )
                                        if "error" not in ai_res:
                                            st.session_state[f"ai_scan_{search_ticker}"] = ai_res
                                            
                                            # --- AUTOMATIC SAVE AND SCREENER WORKFLOW ---
                                            mc_denom_save = stock_data['avg_market_cap_36mo'] or 1.0
                                            total_rev_m = ai_res.get('total_revenue_millions', 1.0) or 1.0
                                            
                                            # Use absolute values to avoid transposition errors
                                            final_haram_rev = ai_res.get('haram_revenue_millions', 0.0) / total_rev_m
                                            final_doubtful_rev = ai_res.get('doubtful_revenue_millions', 0.0) / total_rev_m
                                            
                                            # Deduce interest income if reported as 0.0 but company has cash assets
                                            final_int_inc_ratio = ai_res.get('interest_income_millions', 0.0) / total_rev_m
                                            cash_and_securities_m = ai_res.get('total_cash_and_securities_millions', 0.0) or 0.0
                                            if final_int_inc_ratio == 0.0 and cash_and_securities_m > 0.0:
                                                annual_rev_m = (stock_data.get('total_revenue', 0.0) or 1.0) / 1e6
                                                final_int_inc_ratio = (cash_and_securities_m * 0.03) / annual_rev_m
                                            
                                            final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_denom_save
                                            # Use the total liquid assets (cash + securities) for the cash screen ratio
                                            final_cash_ratio = (cash_and_securities_m * 1e6) / mc_denom_save
                                            
                                            conn_s = get_db()
                                            try:
                                                conn_s.execute("""
                                                    INSERT OR REPLACE INTO manual_overrides 
                                                    (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, updated_at)
                                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                                """, (
                                                    search_ticker, 
                                                    final_haram_rev, 
                                                    final_debt_ratio, 
                                                    final_cash_ratio, 
                                                    final_int_inc_ratio,
                                                    final_doubtful_rev,
                                                    json.dumps(ai_res), # Save full structured AI JSON response
                                                    pd.Timestamp.now().isoformat()
                                                ))
                                                conn_s.commit()
                                                run_screener(use_current_market_cap=False)
                                                st.sidebar.success(f"Audit complete using uploaded document: {file_name}")
                                                st.success("✅ Audit completed, saved, and screener updated automatically!")
                                                st.rerun()
                                            finally:
                                                conn_s.close()
                                        else:
                                            st.error(ai_res["error"])
                                except Exception as e:
                                    st.error(f"Error parsing or analyzing document: {e}")
            with d2:
                st.subheader("📈 Compliance Metrics")
                
                # Manual Financial Correction Form
                with st.expander("🛠️ Manual Financial Correction"):
                    with st.form(key=f"f_{search_ticker}"):
                        f_rev = st.number_input("Haram Revenue %", value=float(stock_data.get('haram_revenue_override', 0.0) or 0.0)*100) / 100
                        f_doubtful = st.number_input("Doubtful Revenue %", value=float(stock_data.get('doubtful_revenue_override', 0.0) or 0.0)*100) / 100
                        f_debt = st.number_input("Debt %", value=float(stock_data.get('debt_ratio_override', 0.0) or 0.0)*100) / 100
                        f_cash = st.number_input("Securities %", value=float(stock_data.get('cash_ratio_override', 0.0) or 0.0)*100) / 100
                        f_int = st.number_input("Interest %", value=float(stock_data.get('interest_income_override', 0.0) or 0.0)*100) / 100
                        if st.form_submit_button("Save & Update Grade"):
                            conn_c = get_db()
                            try:
                                conn_c.execute("""
                                    INSERT INTO manual_overrides (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, (SELECT reasoning FROM manual_overrides WHERE ticker = ?), ?)
                                    ON CONFLICT(ticker) DO UPDATE SET
                                        haram_revenue_override=excluded.haram_revenue_override,
                                        debt_ratio_override=excluded.debt_ratio_override,
                                        cash_ratio_override=excluded.cash_ratio_override,
                                        interest_income_override=excluded.interest_income_override,
                                        doubtful_revenue_override=excluded.doubtful_revenue_override,
                                        updated_at=excluded.updated_at
                                """, (search_ticker, f_rev, f_debt, f_cash, f_int, f_doubtful, search_ticker, pd.Timestamp.now().isoformat()))
                                conn_c.commit()
                                run_screener(use_current_market_cap=False)
                                st.success("Saved & Screener updated!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Saved, but screener failed: {e}")
                            finally:
                                conn_c.close()

                def format_ratio(num, den):
                    if num is None or den is None or den == 0: return 0.0, True
                    return num / den, False

                denom_mc = stock_data['avg_market_cap_36mo'] or 1.0

                raw_debt, d_m = format_ratio(stock_data['total_debt'], denom_mc)
                debt_override = stock_data.get('debt_ratio_override')
                debt_v = debt_override if not pd.isna(debt_override) else raw_debt

                raw_cash, c_m = format_ratio(stock_data['cash_equivalents'], denom_mc)
                cash_override = stock_data.get('cash_ratio_override')
                cash_v = cash_override if not pd.isna(cash_override) else raw_cash

                raw_rec, r_m = format_ratio(stock_data['accounts_receivable'], stock_data['total_assets'])
                rec_override = stock_data.get('receivables_ratio_override')
                rec_v = rec_override if not pd.isna(rec_override) else raw_rec

                raw_int, i_m = format_ratio(stock_data['interest_income'], stock_data['total_revenue'])
                int_override = stock_data.get('interest_income_override')
                int_v = int_override if not pd.isna(int_override) else raw_int

                # Display Visual Progress Indicators
                def render_custom_progress(val, limit, label, is_overridden, is_combined_check=False, haram_val=0.0):
                    pct_of_limit = (val / limit) if limit > 0 else 0
                    bar_color = "#10B981" # Green
                    status_text = "Passed"
                    if val >= limit:
                        if is_combined_check and haram_val < limit:
                            bar_color = "#D2691E" # Chocolate/Doubtful Orange
                            status_text = "Doubtful"
                        else:
                            bar_color = "#EF4444" # Red
                            status_text = "Failed"
                    elif pct_of_limit > 0.8:
                        bar_color = "#F59E0B" # Orange/Yellow
                        status_text = "Warning"
                        
                    progress_val = min(100.0, float(pct_of_limit * 100))
                    override_indicator = " ✍️" if is_overridden else ""
                    
                    html_code = f"""
                    <div style="margin-bottom: 12px; padding: 10px; border-radius: 6px; background-color: #F9FAFB; border: 1px solid #F3F4F6;">
                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
                            <span style="font-weight: 600; color: #374151;">{label}{override_indicator}</span>
                            <span style="font-weight: 600; color: {bar_color};">{val:.2%} / {limit:.2%} ({status_text})</span>
                        </div>
                        <div style="background-color: #E5E7EB; border-radius: 4px; height: 8px; width: 100%; overflow: hidden;">
                            <div style="background-color: {bar_color}; width: {progress_val}%; height: 100%; border-radius: 4px;"></div>
                        </div>
                    </div>
                    """
                    st.markdown(html_code, unsafe_allow_html=True)

                # Haram Revenue Screen (Consolidated with Interest Income)
                raw_rev_ratio, rev_m = format_ratio(stock_data.get('haram_revenue_override', 0.0), 1.0)
                rev_override = stock_data.get('haram_revenue_override')
                rev_v = rev_override if not pd.isna(rev_override) else 0.0
                
                total_haram_v = rev_v + int_v
                total_haram_override = not pd.isna(rev_override) or not pd.isna(int_override)
                
                # Doubtful Revenue Screen
                doubtful_override = stock_data.get('doubtful_revenue_override')
                doubtful_v = doubtful_override if not pd.isna(doubtful_override) else 0.0
                total_combined_v = total_haram_v + doubtful_v
                total_combined_override = total_haram_override or not pd.isna(doubtful_override)

                render_custom_progress(total_haram_v, 0.05, "Haram Revenue Screen", total_haram_override)
                render_custom_progress(total_combined_v, 0.05, "Haram + Doubtful Revenue Screen", total_combined_override, is_combined_check=True, haram_val=total_haram_v)
                render_custom_progress(debt_v, 0.30, "Debt / Market Cap Screen", not pd.isna(debt_override))
                render_custom_progress(cash_v, 0.30, "Cash / Market Cap Screen", not pd.isna(cash_override))
                render_custom_progress(rec_v, 0.45, "Receivables / Total Assets", not pd.isna(rec_override))
                
                if grade not in ["F", "Doubtful"]: 
                    st.success(f"✨ Purification Per Share: **${stock_data.get('purification_per_share', 0) or 0:.4f}/share**")
                
                # --- DETAILED SHARIAH COMPLIANCE REPORT ---
                st.markdown("---")
                st.subheader("📊 Detailed Shariah Financial Report")
                
                # Try to parse override_reason as JSON to extract absolute numbers
                ai_data = None
                reasoning_text = None
                if stock_data.get('override_reason'):
                    try:
                        ai_data = json.loads(stock_data['override_reason'])
                        if isinstance(ai_data, dict):
                            reasoning_text = ai_data.get('reasoning')
                    except Exception:
                        ai_data = None
                        reasoning_text = stock_data['override_reason']

                if reasoning_text:
                    st.markdown(f"""
                    <div style="background-color: #F0F7FF; border-left: 5px solid #2563EB; padding: 15px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                        <h4 style="margin-top:0; color:#1E40AF; display:flex; align-items:center; gap:8px;">
                            <span>🤖 AI Analyst Compliance Verdict</span>
                        </h4>
                        <p style="color:#1E293B; font-size:0.95rem; line-height:1.5; margin:0;">
                            {reasoning_text}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.info("💡 Run a Standard or Source-Backed AI Scan in the left panel to generate a detailed compliance explanation and audit breakdown for this stock.")
                
                if ai_data:
                    with st.expander("📝 Detailed Balance Sheet Audit Breakdown", expanded=True):
                        tot_rev = ai_data.get('total_revenue_millions', 0.0)
                        haram_rev = ai_data.get('haram_revenue_millions', 0.0)
                        doubtful_rev_val = ai_data.get('doubtful_revenue_millions', 0.0)
                        tot_debt = ai_data.get('total_debt_millions', 0.0)
                        ib_debt = ai_data.get('interest_bearing_debt_millions', 0.0)
                        st_debt = ai_data.get('short_term_debt_millions', 0.0)
                        lt_debt = ai_data.get('long_term_debt_millions', 0.0)
                        
                        tot_cash = ai_data.get('total_cash_and_securities_millions', 0.0)
                        ib_cash = ai_data.get('interest_bearing_securities_millions', 0.0)
                        st_cash = ai_data.get('short_term_securities_millions', 0.0)
                        lt_cash = ai_data.get('long_term_securities_millions', 0.0)
                        
                        int_inc = ai_data.get('interest_income_millions', 0.0)
                        
                        mcap_m = denom_mc / 1e6 # Market cap in millions
                        
                        st.markdown(f"**Denominators:**")
                        st.markdown(f"- 36-Month Average Market Cap: **${mcap_m:,.2f} Million**")
                        st.markdown(f"- Total assets in filing: **${stock_data['total_assets']/1e6:,.2f} Million**")
                        
                        st.markdown(f"**1. Revenue & Haram Income Breakdown:**")
                        st.markdown(f"- Total Revenue reported: **${tot_rev:,.2f} Million**")
                        st.markdown(f"- Qualitative Haram Revenue (Segment Estimated): **${haram_rev:,.2f} Million** ({haram_rev/tot_rev if tot_rev > 0 else 0:.2%})")
                        st.markdown(f"- Interest Income (Haram Revenue component): **${int_inc:,.2f} Million** ({int_inc/tot_rev if tot_rev > 0 else 0:.2%})")
                        total_haram_m = haram_rev + int_inc
                        st.markdown(f"- **Total Haram Revenue**: **${total_haram_m:,.2f} Million** ({total_haram_m/tot_rev if tot_rev > 0 else 0:.2%})")
                        st.markdown(f"- **Doubtful Revenue (Uncertain/Questionable)**: **${doubtful_rev_val:,.2f} Million** ({doubtful_rev_val/tot_rev if tot_rev > 0 else 0:.2%})")
                        total_combined_m = total_haram_m + doubtful_rev_val
                        st.markdown(f"- **Total Haram + Doubtful Revenue**: **${total_combined_m:,.2f} Million** ({total_combined_m/tot_rev if tot_rev > 0 else 0:.2%})")
                        
                        # Donut Chart for Revenue Segments
                        if tot_rev > 0:
                            import matplotlib.pyplot as plt
                            labels = []
                            sizes = []
                            colors = []
                            
                            halal_rev = max(0.0, tot_rev - (haram_rev + doubtful_rev_val + int_inc))
                            
                            if halal_rev > 0:
                                labels.append(f"Halal (${halal_rev:,.1f}M)")
                                sizes.append(halal_rev)
                                colors.append("#10B981") # Green
                            if haram_rev > 0:
                                labels.append(f"Haram Segment (${haram_rev:,.1f}M)")
                                sizes.append(haram_rev)
                                colors.append("#EF4444") # Red
                            if int_inc > 0:
                                labels.append(f"Interest Income (${int_inc:,.1f}M)")
                                sizes.append(int_inc)
                                colors.append("#F59E0B") # Yellow
                            if doubtful_rev_val > 0:
                                labels.append(f"Doubtful (${doubtful_rev_val:,.1f}M)")
                                sizes.append(doubtful_rev_val)
                                colors.append("#D2691E") # Chocolate/Doubtful Orange
                                
                            if sizes:
                                fig, ax = plt.subplots(figsize=(5, 3))
                                wedges, texts, autotexts = ax.pie(
                                    sizes, 
                                    labels=labels, 
                                    autopct='%1.1f%%',
                                    startangle=140,
                                    colors=colors,
                                    textprops=dict(color="#1E293B", weight="bold", fontsize=7.5),
                                    wedgeprops=dict(width=0.35, edgecolor='w', linewidth=1.5) # Donut style
                                )
                                for t in texts:
                                    t.set_fontsize(7)
                                for at in autotexts:
                                    at.set_fontsize(7)
                                    
                                ax.set_title("Revenue Share Breakdown (%)", color="#0F172A", weight="bold", fontsize=9)
                                plt.tight_layout()
                                st.pyplot(fig)
                                plt.close(fig)
                        
                        st.markdown(f"**2. Interest-Bearing Debt Breakdown:**")
                        st.markdown(f"- Total Debt in filing: **${tot_debt:,.2f} Million**")
                        st.markdown(f"- Total Interest-Bearing Debt: **${ib_debt:,.2f} Million** ({ib_debt/tot_debt if tot_debt > 0 else 0:.1%})")
                        st.markdown(f"  - *Short-Term portion*: **${st_debt:,.2f} Million** ({st_debt/mcap_m if mcap_m > 0 else 0:.2%} of Market Cap)")
                        st.markdown(f"  - *Long-Term portion*: **${lt_debt:,.2f} Million** ({lt_debt/mcap_m if mcap_m > 0 else 0:.2%} of Market Cap)")
                        st.markdown(f"  - *Total Debt/Market Cap Ratio*: **{ib_debt/mcap_m:.2%}**")
                        
                        st.markdown(f"**3. Liquid Assets & Cash Portfolio Breakdown:**")
                        st.markdown(f"- Total Cash & Securities Portfolio: **${tot_cash:,.2f} Million**")
                        st.markdown(f"- Total Interest-Bearing Securities: **${ib_cash:,.2f} Million** ({ib_cash/tot_cash if tot_cash > 0 else 0:.1%})")
                        st.markdown(f"  - *Short-Term portion* (Cash/Current Marketable): **${st_cash:,.2f} Million** ({st_cash/mcap_m if mcap_m > 0 else 0:.2%} of Market Cap)")
                        st.markdown(f"  - *Long-Term portion* (Non-current Marketable): **${lt_cash:,.2f} Million** ({lt_cash/mcap_m if mcap_m > 0 else 0:.2%} of Market Cap)")
                        st.markdown(f"  - *Total Cash/Market Cap Ratio*: **{ib_cash/mcap_m:.2%}**")
    except Exception as e: st.error(f"Error: {e}")
    finally: conn.close()
