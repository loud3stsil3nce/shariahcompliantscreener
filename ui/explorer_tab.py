import streamlit as st
import pandas as pd
import json
import os
from src.utils import get_db
from src.screener import run_screener

def render():
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
                WHERE s.ticker = '{search_ticker}'
            """
            stock_data = pd.read_sql_query(query, conn).iloc[0]
            
            # --- LIVE TICKER COMPLIANCE TRACKING ---
            enable_live = st.sidebar.toggle("🔌 Enable Real-Time Price Compliance Monitor", key=f"live_toggle_{search_ticker}")
            live_price = None
            live_cap = None
            live_grade = stock_data['grade'] or "F"
            live_score = stock_data['compliance_score'] or 0.0
            
            if enable_live:
                import yfinance as yf
                import numpy as np
                from src.screener import get_effective_override, MAX_DEBT_RATIO, MAX_CASH_RATIO, MIN_TANGIBILITY_RATIO, MAX_LIQUID_RATIO, MAX_HARAM_INCOME_RATIO, HARAM_SECTORS, HARAM_INDUSTRY_KEYWORDS
                
                with st.spinner("Fetching real-time price..."):
                    try:
                        t = yf.Ticker(search_ticker)
                        live_price = t.fast_info.get("lastPrice")
                        if not live_price or pd.isna(live_price):
                            hist = t.history(period="1d")
                            if not hist.empty:
                                live_price = float(hist["Close"].iloc[-1])
                                
                        shares = float(stock_data.get('shares_outstanding', 0.0) or 0.0)
                        if live_price and shares > 0:
                            live_cap = live_price * shares
                    except Exception as e:
                        st.sidebar.error(f"Failed to fetch live price: {e}")
                        
                if live_price and live_cap:
                    # Dynamically calculate compliance grade and ratios
                    eff_debt = get_effective_override(stock_data, "debt_ratio_override")
                    eff_cash = get_effective_override(stock_data, "cash_ratio_override")
                    eff_tangibility = get_effective_override(stock_data, "tangibility_ratio_override")
                    eff_int = get_effective_override(stock_data, "interest_income_override")
                    eff_haram = get_effective_override(stock_data, "haram_revenue_override")
                    eff_doubtful = get_effective_override(stock_data, "doubtful_revenue_override")
                    
                    debt_ratio = eff_debt if not pd.isna(eff_debt) else (stock_data['total_debt'] / live_cap)
                    cash_ratio = eff_cash if not pd.isna(eff_cash) else (stock_data['cash_equivalents'] / live_cap)
                    
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
                    
                    if not is_halal_live:
                        is_doubtful_reason = pass_sector and pass_industry and pass_debt and pass_cash and pass_tangibility and pass_interest and (not pass_combined)
                        if is_doubtful_reason:
                            live_grade = "Doubtful"
                        else:
                            live_grade = "F"
                        live_score = 0.0
                    else:
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
            
            c1, c2 = st.columns([3, 1])
            with c1:
                st.title(f"{stock_data['ticker']}: {stock_data['name']}")
                st.caption(f"{stock_data['sector']} | {stock_data['industry']}")
                if enable_live and live_price and live_cap:
                    db_halal = stock_data['grade'] not in ["F", "Doubtful"]
                    live_halal = live_grade not in ["F", "Doubtful"]
                    
                    drift_indicator = ""
                    if db_halal and not live_halal:
                        drift_indicator = " ⚠️ **CRITICAL DRIFT: Stock is no longer compliant due to price drop!**"
                    elif not db_halal and live_halal:
                        drift_indicator = " 🎉 **RECOVERY: Stock price rise has restored compliance!**"
                        
                    st.markdown(f"🟢 **Live Price**: `${live_price:,.2f}` | **Live Cap**: `${live_cap/1e6:,.1f}M`{drift_indicator}")
                
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
                grade = live_grade
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

                # --- SOURCE-BACKED AUDIT ---
                if st.button("🔬 Source-Backed Deep Audit (Very Accurate)"):
                    from src.sec_extractor import get_latest_10k_text
                    from src.ai_analyst import analyze_company_compliance
                    from src.db_setup import save_proposed_rules

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
                                        (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
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
                                    save_proposed_rules(search_ticker, ai_res)
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

                # --- MULTI-SOURCE HARVESTER AUDIT ---
                if st.button("🌐 Multi-Source Harvester Audit (Gold Standard)", help="Parallel-retrieves 10-K, earnings call transcripts, and investor supplements to run a cross-source semantic RAG audit."):
                    from src.sec_extractor import get_latest_10k_text
                    from src.harvester import harvest_all_sources
                    from src.ai_analyst import analyze_multi_source_compliance
                    from src.db_setup import save_proposed_rules
                    import threading
                    import asyncio

                    def run_async_in_thread(coro):
                        res = []
                        err = []
                        def worker():
                            try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                val = loop.run_until_complete(coro)
                                res.append(val)
                            except Exception as e:
                                err.append(e)
                            finally:
                                loop.close()
                        t = threading.Thread(target=worker)
                        t.start()
                        t.join()
                        if err:
                            raise err[0]
                        return res[0]

                    with st.spinner(f"Step 1 of 3: Locating and downloading latest audited SEC report for {stock_data['ticker']}..."):
                        sec_text, sec_url = get_latest_10k_text(stock_data['ticker'])
                        
                    with st.spinner("Step 2 of 3: Fetching transcripts, supplements and building semantic vector database..."):
                        try:
                            # Run async harvest in a separate thread to avoid Streamlit event loop collision
                            harvested = run_async_in_thread(harvest_all_sources(stock_data['ticker'], year=2025, quarter=4, sec_text=sec_text))
                        except Exception as e:
                            st.error(f"Harvester failed: {e}")
                            harvested = None

                    if harvested and harvested.get("chunks"):
                        with st.spinner("Step 3 of 3: Executing cross-source semantic Shariah auditor..."):
                            ai_res = analyze_multi_source_compliance(
                                stock_data['ticker'],
                                stock_data['name'],
                                harvested,
                                summary=business_summary
                            )
                            
                            if "error" not in ai_res:
                                st.session_state[f"ai_scan_{search_ticker}"] = ai_res
                                
                                # --- AUTOMATIC SAVE AND SCREENER WORKFLOW ---
                                mc_denom_save = stock_data['avg_market_cap_36mo'] or 1.0
                                
                                # TTM Normalization / Scaling for flow metrics
                                filing_period = ai_res.get('filing_period_months', 12) or 12
                                scale_factor = 12.0 / filing_period
                                
                                total_rev_m = (ai_res.get('total_revenue_millions', 1.0) or 1.0) * scale_factor
                                haram_revenue_millions = (ai_res.get('haram_revenue_millions', 0.0) or 0.0) * scale_factor
                                doubtful_revenue_millions = (ai_res.get('doubtful_revenue_millions', 0.0) or 0.0) * scale_factor
                                interest_income_millions = (ai_res.get('interest_income_millions', 0.0) or 0.0) * scale_factor
                                
                                final_haram_rev = haram_revenue_millions / total_rev_m
                                final_doubtful_rev = doubtful_revenue_millions / total_rev_m
                                
                                final_int_inc_ratio = interest_income_millions / total_rev_m
                                cash_and_securities_m = ai_res.get('total_cash_and_securities_millions', 0.0) or 0.0
                                if final_int_inc_ratio == 0.0 and cash_and_securities_m > 0.0:
                                    annual_rev_m = (stock_data.get('total_revenue', 0.0) or 1.0) / 1e6
                                    final_int_inc_ratio = (cash_and_securities_m * 0.03) / annual_rev_m
                                
                                final_debt_ratio = (ai_res.get('interest_bearing_debt_millions', 0.0) * 1e6) / mc_denom_save
                                final_cash_ratio = (cash_and_securities_m * 1e6) / mc_denom_save
                                
                                conn_s = get_db()
                                try:
                                    conn_s.execute("""
                                        INSERT OR REPLACE INTO manual_overrides 
                                        (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                                    """, (
                                        search_ticker, 
                                        final_haram_rev, 
                                        final_debt_ratio, 
                                        final_cash_ratio, 
                                        final_int_inc_ratio,
                                        final_doubtful_rev,
                                        json.dumps(ai_res),
                                        pd.Timestamp.now().isoformat()
                                    ))
                                    conn_s.commit()
                                    save_proposed_rules(search_ticker, ai_res)
                                    run_screener(use_current_market_cap=False)
                                    st.sidebar.success(f"Audit complete using Multi-Source Harvester!")
                                    st.success("✅ Multi-Source Harvester Audit completed, saved, and screener updated automatically!")
                                    st.rerun()
                                finally:
                                    conn_s.close()
                            else:
                                st.error(ai_res["error"])
                    else:
                        st.error("Could not compile search or transcript chunks. Check internet connectivity.")

                if st.button("🔍 Standard AI Analysis (Fast)"):
                    from src.ai_analyst import analyze_company_compliance
                    from src.db_setup import save_proposed_rules

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
                            
                            # TTM Normalization / Scaling for flow metrics
                            filing_period = ai_res.get('filing_period_months', 12) or 12
                            scale_factor = 12.0 / filing_period
                            
                            total_rev_m = (ai_res.get('total_revenue_millions', 1.0) or 1.0) * scale_factor
                            haram_revenue_millions = (ai_res.get('haram_revenue_millions', 0.0) or 0.0) * scale_factor
                            doubtful_revenue_millions = (ai_res.get('doubtful_revenue_millions', 0.0) or 0.0) * scale_factor
                            interest_income_millions = (ai_res.get('interest_income_millions', 0.0) or 0.0) * scale_factor
                            
                            final_haram_rev = haram_revenue_millions / total_rev_m
                            final_doubtful_rev = doubtful_revenue_millions / total_rev_m
                            
                            final_int_inc_ratio = interest_income_millions / total_rev_m
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
                                    (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
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
                                save_proposed_rules(search_ticker, ai_res)
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
                                        from src.db_setup import save_proposed_rules
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
                                            
                                            # TTM Normalization / Scaling for flow metrics
                                            filing_period = ai_res.get('filing_period_months', 12) or 12
                                            scale_factor = 12.0 / filing_period
                                            
                                            total_rev_m = (ai_res.get('total_revenue_millions', 1.0) or 1.0) * scale_factor
                                            haram_revenue_millions = (ai_res.get('haram_revenue_millions', 0.0) or 0.0) * scale_factor
                                            doubtful_revenue_millions = (ai_res.get('doubtful_revenue_millions', 0.0) or 0.0) * scale_factor
                                            interest_income_millions = (ai_res.get('interest_income_millions', 0.0) or 0.0) * scale_factor
                                            
                                            final_haram_rev = haram_revenue_millions / total_rev_m
                                            final_doubtful_rev = doubtful_revenue_millions / total_rev_m
                                            
                                            final_int_inc_ratio = interest_income_millions / total_rev_m
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
                                                    (ticker, haram_revenue_override, debt_ratio_override, cash_ratio_override, interest_income_override, doubtful_revenue_override, reasoning, is_user_override, updated_at)
                                                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
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
                                                save_proposed_rules(search_ticker, ai_res)
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


                def format_ratio(num, den):
                    if num is None or den is None or den == 0: return 0.0, True
                    return num / den, False

                denom_mc = live_cap if (enable_live and live_cap) else (stock_data['avg_market_cap_36mo'] or 1.0)

                from src.screener import get_effective_override
                raw_debt, d_m = format_ratio(stock_data['total_debt'], denom_mc)
                debt_override = get_effective_override(stock_data, 'debt_ratio_override')
                debt_v = debt_override if not pd.isna(debt_override) else raw_debt

                raw_cash, c_m = format_ratio(stock_data['cash_equivalents'], denom_mc)
                cash_override = get_effective_override(stock_data, 'cash_ratio_override')
                cash_v = cash_override if not pd.isna(cash_override) else raw_cash

                tang_override = get_effective_override(stock_data, 'tangibility_ratio_override')
                if not pd.isna(tang_override):
                    tang_v = tang_override
                else:
                    ta_val = stock_data['total_assets']
                    cash_val = stock_data['cash_equivalents'] if (stock_data['cash_equivalents'] is not None and not pd.isna(stock_data['cash_equivalents'])) else 0.0
                    ar_val = stock_data['accounts_receivable'] if (stock_data['accounts_receivable'] is not None and not pd.isna(stock_data['accounts_receivable'])) else 0.0
                    tang_v = (ta_val - cash_val - ar_val) / ta_val if ta_val else 0.0
                liquid_v = 1.0 - tang_v

                raw_int, i_m = format_ratio(stock_data['interest_income'], stock_data['total_revenue'])
                int_override = get_effective_override(stock_data, 'interest_income_override')
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
                raw_rev_ratio, rev_m = format_ratio(get_effective_override(stock_data, 'haram_revenue_override'), 1.0)
                rev_override = get_effective_override(stock_data, 'haram_revenue_override')
                rev_v = rev_override if not pd.isna(rev_override) else 0.0
                
                total_haram_v = rev_v + int_v
                total_haram_override = not pd.isna(rev_override) or not pd.isna(int_override)
                
                # Doubtful Revenue Screen
                doubtful_override = get_effective_override(stock_data, 'doubtful_revenue_override')
                doubtful_v = doubtful_override if not pd.isna(doubtful_override) else 0.0
                total_combined_v = total_haram_v + doubtful_v
                total_combined_override = total_haram_override or not pd.isna(doubtful_override)

                render_custom_progress(total_haram_v, 0.05, "Haram Revenue Screen", total_haram_override)
                render_custom_progress(total_combined_v, 0.05, "Haram + Doubtful Revenue Screen", total_combined_override, is_combined_check=True, haram_val=total_haram_v)
                render_custom_progress(debt_v, 0.30, "Debt / Market Cap Screen", not pd.isna(debt_override))
                render_custom_progress(cash_v, 0.30, "Cash / Market Cap Screen", not pd.isna(cash_override))
                render_custom_progress(liquid_v, 0.70, "Liquid Assets / Total Assets (Max 70%)", not pd.isna(tang_override))
                
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
                    source_badge = ""
                    if ai_data and ai_data.get("audit_source"):
                        source_badge = f"<span style='font-size:0.75rem; background-color:#3B82F6; color:#ffffff; padding:3px 8px; border-radius:4px; margin-left:10px; font-weight:normal;'>{ai_data.get('audit_source')}</span>"
                    st.markdown(
                        f'<div style="background-color: #F0F7FF; border-left: 5px solid #2563EB; padding: 15px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">'
                        f'<h4 style="margin-top:0; color:#1E40AF; display:flex; align-items:center; gap:8px; flex-wrap:wrap;">'
                        f'<span>🤖 AI Analyst Compliance Verdict</span>'
                        f'{source_badge}'
                        f'</h4>'
                        f'<p style="color:#1E293B; font-size:0.95rem; line-height:1.5; margin:0;">'
                        f'{reasoning_text}'
                        f'</p>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
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
