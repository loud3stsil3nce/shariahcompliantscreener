import streamlit as st
import os
from src.backtester import run_backtest

def render():
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
