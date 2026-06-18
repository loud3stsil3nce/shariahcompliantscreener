import streamlit as st
import json
import os

def render():
    st.subheader("🤖 SRE Agent Status")
    
    # Path inside the container (mapped via volume)
    status_path = "/app/status.json"
    
    
    if os.path.exists(status_path):
        try:
            with open(status_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            st.error("Telemetry file is corrupted or currently being written.")
            return
        
        # Displaying the status with visual hierarchy
        col1, col2 = st.columns(2)
        
        # Accessing nested keys
        last_action = data.get('last_action', {})
        result = last_action.get('result', 'unknown')
        notes = last_action.get('notes', 'No notes provided')

        # Now use these variables for your UI logic
        status_color = "normal" if result == "success" else "inverse"

        col1.metric("System Health", data['system']['status'])
        col2.metric("Last Result", result)

        st.info(f"**Last Action:** {last_action.get('type')}")
        st.warning(f"**Agent Notes:** {notes}")
        st.caption(f"Last updated at: {data.get('timestamp', 'N/A')}")
        
        # Optional: Raw JSON view for debugging
        with st.expander("View Raw Telemetry"):
            st.json(data)
    else:
        st.error("No telemetry data found. Is the MCP Agent running?")