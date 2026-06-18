import streamlit as st
import pandas as pd
from src.utils import get_db

def render():
    st.header("⚙️ Active Shariah Segment Rules (AI-Generated)")
    st.markdown("""
    This panel displays the Shariah compliance segment rules automatically generated and enforced by the AI.
    Rules are discovered and committed dynamically during audits to guide future classifications.
    """)
    
    conn = get_db()
    try:
        # Fetch metrics
        ticker_rules_count = conn.execute("SELECT COUNT(*) FROM shariah_segment_map").fetchone()[0]
        global_patterns_count = conn.execute("SELECT COUNT(*) FROM global_segment_patterns").fetchone()[0]
        
        m1, m2 = st.columns(2)
        m1.metric("Ticker-Specific Rules (Tier 3)", ticker_rules_count)
        m2.metric("Global Keyword Patterns (Tier 2)", global_patterns_count)
        
        # Create sub-tabs for segment rules viewing
        sub_tab1, sub_tab2 = st.tabs([
            "🎯 Ticker-Specific Rules", 
            "🌐 Global Keyword Patterns"
        ])
        
        with sub_tab1:
            st.subheader("🎯 Ticker-Specific Segment Rules")
            st.markdown("Rules automatically applied to individual stock segments to resolve aggregate services and conglomerates.")
            
            # Fetch existing ticker rules
            ticker_rules = pd.read_sql_query("SELECT ticker, segment_name, compliance_status, notes FROM shariah_segment_map ORDER BY ticker, segment_name", conn)
            
            if ticker_rules.empty:
                st.info("No active ticker-specific rules.")
            else:
                for idx, row in ticker_rules.iterrows():
                    ticker = row['ticker']
                    seg_name = row['segment_name']
                    status = row['compliance_status']
                    notes = row['notes']
                    
                    col_t1, col_t2, col_t3, col_t4 = st.columns([1, 2, 1, 4])
                    with col_t1:
                        st.markdown(f"**{ticker}**")
                    with col_t2:
                        st.markdown(f"`{seg_name}`")
                    with col_t3:
                        badge_color = "#10B981" if status == "halal" else ("#EF4444" if status == "haram" else "#D2691E")
                        st.markdown(f"<span style='background-color: {badge_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;'>{status.upper()}</span>", unsafe_allow_html=True)
                    with col_t4:
                        st.caption(notes)
                    st.markdown("<hr style='margin: 4px 0px;' />", unsafe_allow_html=True)
                    
        with sub_tab2:
            st.subheader("🌐 Global Keyword Patterns")
            st.markdown("Keyword rules that apply globally to any segment containing the keyword pattern.")
            
            # Fetch existing global patterns
            global_patterns = pd.read_sql_query("SELECT pattern, compliance_status, notes FROM global_segment_patterns ORDER BY pattern", conn)
            
            if global_patterns.empty:
                st.info("No active global keyword patterns.")
            else:
                for idx, row in global_patterns.iterrows():
                    pattern = row['pattern']
                    status = row['compliance_status']
                    notes = row['notes']
                    
                    col_g1, col_g2, col_g3 = st.columns([2, 1, 5])
                    with col_g1:
                        st.markdown(f"`{pattern}`")
                    with col_g2:
                        badge_color = "#10B981" if status == "halal" else ("#EF4444" if status == "haram" else "#D2691E")
                        st.markdown(f"<span style='background-color: {badge_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: bold;'>{status.upper()}</span>", unsafe_allow_html=True)
                    with col_g3:
                        st.caption(notes)
                    st.markdown("<hr style='margin: 4px 0px;' />", unsafe_allow_html=True)
                    
    except Exception as e:
        st.error(f"Error loading Segment Rules: {e}")
    finally:
        conn.close()
