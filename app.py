"""
app.py — Streamlit Dashboard for Autonomous Network Operations.
Connects to FastAPI to display live persistent telemetry and orchestrate the control plane.
"""

import streamlit as st
import requests
import plotly.graph_objects as go
import time
import json
from datetime import datetime

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="NetOps Autonomous Agent",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem; color: white;
    }
    .main-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; }
    .main-header p { margin: 0.3rem 0 0 0; opacity: 0.75; font-size: 0.9rem; }
    .status-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #2a2a4a; border-radius: 10px; padding: 1rem 1.2rem; margin-bottom: 0.8rem; color: #e0e0e0;
    }
    .status-card h4 { color: #7c83ff; margin: 0 0 0.5rem 0; font-size: 0.85rem; text-transform: uppercase; }
    .status-card .value { font-size: 1.6rem; font-weight: 700; color: white; }
    .trace-step {
        background: #1a1a2e; border-left: 3px solid #7c83ff; padding: 0.8rem 1rem; margin-bottom: 0.5rem;
        border-radius: 0 8px 8px 0; font-family: 'Courier New', monospace; font-size: 0.82rem; color: #c8c8e8;
    }
    .trace-step.observe { border-left-color: #00d2ff; }
    .trace-step.retrieve { border-left-color: #a855f7; }
    .trace-step.reason { border-left-color: #f59e0b; }
    .trace-step.human { border-left-color: #ef4444; }
    .trace-step.act { border-left-color: #22c55e; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e, #16213e); border: 1px solid #2a2a4a; border-radius: 10px; padding: 1rem;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────
def fetch_api(endpoint: str, method: str = "GET", payload: dict = None):
    try:
        url = f"{API_BASE}{endpoint}"
        if method == "POST":
            resp = requests.post(url, json=payload, timeout=30)
        else:
            resp = requests.get(url, timeout=5)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def get_trace_class(log_line: str) -> str:
    line = log_line.upper()
    if "OBSERVE" in line: return "observe"
    elif "RETRIEV" in line: return "retrieve"
    elif "REASON" in line: return "reason"
    elif "HUMAN" in line or "APPROVAL" in line: return "human"
    elif "EXECUTOR" in line or "ACT" in line: return "act"
    return ""

# ─────────────────────────────────────────────
# Sidebar — Network Topology & Controls
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌐 Network Controllers")
    
    st.markdown("### 🚨 Simulate Persistent Anomalies")
    
    # We will pick 3 routers to focus on for demo purposes
    demo_routers = ["Core-Router-Mumbai", "Edge-Router-Delhi", "Core-Router-Delhi"]
    
    selected_router = st.selectbox("Target Router", demo_routers)
    anomaly_type = st.selectbox("Anomaly Type", ["congestion", "bgp_down", "cpu_spike", "interface_flap"])
    
    if st.button("Inject Anomaly", type="primary", use_container_width=True):
        with st.spinner("Injecting persistent anomaly..."):
            res = fetch_api("/api/simulate-anomaly", method="POST", payload={"anomaly_type": anomaly_type, "router_name": selected_router})
            if "error" not in res:
                st.success(f"Injected {anomaly_type} on {selected_router}!")
            else:
                st.error("Failed to inject.")

    st.markdown("---")
    
    telemetry = fetch_api("/telemetry?limit=5")
    if telemetry and "network_state" in telemetry:
        state = telemetry["network_state"]
        st.markdown("### 📉 Live Network State")
        for r in demo_routers:
            r_state = state.get(r, {})
            has_issues = any(r_state.values())
            icon = "🔴" if has_issues else "🟢"
            issues = [k for k,v in r_state.items() if v]
            st.markdown(f"{icon} **{r}**")
            if has_issues:
                st.caption(f"Errors: {', '.join(issues)}")
            else:
                st.caption("Status: Healthy")

# ─────────────────────────────────────────────
# Main View
# ─────────────────────────────────────────────
st.markdown("""<div class="main-header">
    <h1>🤖 NetOps Autonomous Agent</h1>
    <p>Observe → Reason → Decide → Act → Learn | Closed-Loop Resolution System</p>
</div>""", unsafe_allow_html=True)

# Fetch Full Telemetry
full_data = fetch_api("/telemetry?limit=100")
agent_logs_data = fetch_api("/agent-logs")

if full_data and "data" in full_data and len(full_data["data"]) > 0:
    data_points = full_data["data"]
    latest = data_points[-1]
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("⚡ Latest Latency", f"{latest.get('latency_ms', 0):.1f} ms")
    col2.metric("📉 Packet Loss", f"{latest.get('packet_loss_pct', 0):.1f} %")
    col3.metric("💻 CPU Utilization", f"{latest.get('cpu_utilization_pct', 0):.1f} %")
    col4.metric("🔄 BGP Flaps", f"{latest.get('bgp_flaps_per_min', 0)}")
    
    st.markdown("### 📈 Live Telemetry — Metrics")
    
    timestamps = [p["timestamp"][-12:-1] for p in data_points]
    
    fig = go.Figure()
    # Latency 
    fig.add_trace(go.Scatter(x=timestamps, y=[p["latency_ms"] for p in data_points], 
                             mode="lines+markers", name="Latency (ms)", line=dict(color="#7c83ff")))
    # Packet Loss
    fig.add_trace(go.Scatter(x=timestamps, y=[p["packet_loss_pct"] for p in data_points], 
                             mode="lines+markers", name="Packet Loss (%)", line=dict(color="#ef4444")))
    # CPU
    fig.add_trace(go.Scatter(x=timestamps, y=[p.get("cpu_utilization_pct", 0) for p in data_points], 
                             mode="lines+markers", name="CPU (%)", line=dict(color="#f59e0b")))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(26,26,46,0.8)", plot_bgcolor="rgba(26,26,46,0.8)",
        height=350, margin=dict(l=40, r=20, t=30, b=40),
        yaxis=dict(title="Value"), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("⏳ Waiting for telemetry data... Make sure the API server is running.")


st.markdown("### 🧠 Agent Action Log")
if agent_logs_data and "logs" in agent_logs_data and agent_logs_data["logs"]:
    # Show last 3 logs
    for i, log_entry in enumerate(reversed(agent_logs_data["logs"][-3:])):
        ts = log_entry.get("timestamp", "")[:19]
        trigger = log_entry.get("trigger", "unknown")
        
        with st.expander(f"🧩 Run: {trigger} — {ts}", expanded=(i == 0)):
            if "error" in log_entry:
                st.error(f"Error: {log_entry['error']}")
                continue
            
            result = log_entry.get("result", {})
            
            mcol1, mcol2 = st.columns(2)
            mcol1.metric("Action Taken", result.get("recommended_action", "N/A"))
            mcol2.metric("Risk Level", result.get("risk_level", "N/A").upper())

            st.markdown("**Agent Trace:**")
            for log_line in result.get("logs", []):
                css_class = get_trace_class(log_line)
                st.markdown(f'<div class="trace-step {css_class}">{log_line}</div>', unsafe_allow_html=True)
else:
    st.info('⏳ No agent runs yet. Inject an anomaly from the sidebar to test the closed loop.')

# Auto-refresh
st.markdown("---")
auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh (every 2s)", value=True)
if auto_refresh:
    time.sleep(2)
    st.rerun()
