import streamlit as st
import pandas as pd
from src.utils import get_db

def render():
    st.header("📋 Global Stock Database")
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["🟢 Halal Universe", "🟡 Doubtful Stocks", "🔴 Haram Stocks"])
    
    with sub_tab1:
        st.subheader("🟢 Halal Universe")
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

    with sub_tab2:
        st.subheader("🟡 Doubtful Stocks")
        conn = get_db()
        try:
            df_doubtful = pd.read_sql_query("SELECT * FROM doubtful_universe", conn)
            if not df_doubtful.empty:
                cols_to_show = ["ticker", "name", "sector", "grade", "debt_ratio", "total_haram_ratio", "doubtful_ratio", "total_combined_ratio", "purification_per_share"]
                existing_cols = [c for c in cols_to_show if c in df_doubtful.columns]
                df_doubtful_show = df_doubtful[existing_cols]
                
                def color_grade(val):
                    color = 'green' if val.startswith('A') else 'orange' if (val.startswith('B') or val.startswith('C') or val == 'Doubtful') else 'red'
                    return f'color: {color}; font-weight: bold'
                
                formatters = {}
                if "debt_ratio" in existing_cols:
                    formatters["debt_ratio"] = "{:.2%}"
                if "total_haram_ratio" in existing_cols:
                    formatters["total_haram_ratio"] = "{:.2%}"
                if "doubtful_ratio" in existing_cols:
                    formatters["doubtful_ratio"] = "{:.2%}"
                if "total_combined_ratio" in existing_cols:
                    formatters["total_combined_ratio"] = "{:.2%}"
                if "purification_per_share" in existing_cols:
                    formatters["purification_per_share"] = "${:.4f}"
                
                st.dataframe(df_doubtful_show.style.map(color_grade, subset=['grade']).format(formatters), width='stretch', hide_index=True)
            else:
                st.info("No doubtful stocks found.")
        except Exception:
            st.info("Run the Screener first.")
        finally:
            conn.close()

    with sub_tab3:
        st.subheader("🔴 Haram Stocks (Rejected)")
        conn = get_db()
        try:
            df_haram = pd.read_sql_query("SELECT * FROM halal_rejections", conn)
            if not df_haram.empty:
                cols_to_show = ["ticker", "name", "sector", "grade", "debt_ratio", "total_haram_ratio", "total_combined_ratio", "halal_failure"]
                existing_cols = [c for c in cols_to_show if c in df_haram.columns]
                df_haram_show = df_haram[existing_cols]
                
                def color_grade(val):
                    color = 'green' if val.startswith('A') else 'orange' if (val.startswith('B') or val.startswith('C') or val == 'Doubtful') else 'red'
                    return f'color: {color}; font-weight: bold'
                
                formatters = {}
                if "debt_ratio" in existing_cols:
                    formatters["debt_ratio"] = "{:.2%}"
                if "total_haram_ratio" in existing_cols:
                    formatters["total_haram_ratio"] = "{:.2%}"
                if "total_combined_ratio" in existing_cols:
                    formatters["total_combined_ratio"] = "{:.2%}"
                
                st.dataframe(df_haram_show.style.map(color_grade, subset=['grade']).format(formatters), width='stretch', hide_index=True)
            else:
                st.info("No haram stocks found.")
        except Exception:
            st.info("Run the Screener first.")
        finally:
            conn.close()
