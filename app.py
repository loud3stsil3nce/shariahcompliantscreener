import streamlit as st
import pandas as pd
import os
import json

from src.data.ingestion import run_ingestion

from src.analysis.screener import run_screener
from src.analysis.optimizer import run_optimizer
from src.analysis.backtester import run_backtest
from src.db.helpers import get_db

from ui.dashboard_tab import render as render_dashboard
from ui.database_tab import render as render_database
from ui.explorer_tab import render as render_explorer
from ui.mcp_tab import render as render_mcp
from ui.rules_tab import render as render_rules
from ui.simulation_tab import render as render_simulation

import sqlite3
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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Portfolio Dashboard",
    "📋 Halal Universe",
    "⏳ Historical Backtest",
    "🔍 Stock Explorer",
    "MCP Tab",
    "Rules Tab"
])

with tab1:
    render_dashboard(invest_amount)

with tab2:
    render_database()

with tab3:
    render_simulation()

with tab4:
    render_explorer()

with tab5:
    render_mcp()

with tab6:
    render_rules()

