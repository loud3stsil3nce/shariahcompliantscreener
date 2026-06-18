import streamlit as st
import os
from src.ingestion import run_ingestion
from src.screener import run_screener
from src.optimizer import run_optimizer

def apply_custom_css():
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

def render_sidebar():
    st.sidebar.header("⚙️ Control Panel")

    # 1. Ingestion
    st.sidebar.subheader("1. Data Ingestion")
    use_current_mcap = False

    force_refresh = st.sidebar.checkbox("Force Full Refresh", value=False, help="Update existing database records. If unchecked, only missing stocks will be fetched.")
    if st.sidebar.button("Fetch Latest Data"):
        with st.spinner("Fetching data from Yahoo Finance..."):
            run_ingestion(refresh=force_refresh)
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
    include_doubtful = st.sidebar.checkbox(
        "Include Doubtful Stocks",
        value=False,
        help="If checked, stocks categorized as Doubtful (due to combined Haram + Doubtful revenue exceeding 5%) will be included in the portfolio optimization universe."
    )
    invest_amount = st.sidebar.number_input("Investment Amount ($)", min_value=1000, value=10000, step=1000)

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
                    target_ret=target_ret,
                    include_doubtful=include_doubtful
                )
                if results:
                    st.session_state.optimizer_results = results
                    st.sidebar.success("Optimization Complete!")
                else:
                    st.sidebar.error("Optimization failed. The constraints could not be satisfied. Try lowering your Target Return, raising your Target Volatility, or increasing Max Weight limits.")
            except Exception as e:
                st.sidebar.error(f"Optimization failed: {e}")
                
    return invest_amount
