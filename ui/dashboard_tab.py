import streamlit as st
import pandas as pd
import os

def render(invest_amount):
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
