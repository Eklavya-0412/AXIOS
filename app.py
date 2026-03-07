"""
app.py — Streamlit Dashboard for Autonomous Network Operations.

Run:
    streamlit run app.py
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

# ─────────────────────────────────────────────
# Custom Styling
# ─────────────────────────────────────────────
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    .main-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }

    .main-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }

    .main-header p {
        margin: 0.3rem 0 0 0;
        opacity: 0.75;
        font-size: 0.9rem;
    }

    .status-card {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #2a2a4a;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        color: #e0e0e0;
    }

    .status-card h4 {
        color: #7c83ff;
        margin: 0 0 0.5rem 0;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .status-card .value {
        font-size: 1.6rem;
        font-weight: 700;
        color: white;
    }

    .trace-step {
        background: #1a1a2e;
        border-left: 3px solid #7c83ff;
        padding: 0.8rem 1rem;
        margin-bottom: 0.5rem;
        border-radius: 0 8px 8px 0;
        font-family: 'Courier New', monospace;
        font-size: 0.82rem;
        color: #c8c8e8;
    }

    .trace-step.observe { border-left-color: #00d2ff; }
    .trace-step.retrieve { border-left-color: #a855f7; }
    .trace-step.reason { border-left-color: #f59e0b; }
    .trace-step.human { border-left-color: #ef4444; }
    .trace-step.act { border-left-color: #22c55e; }

    .anomaly-btn {
        background: linear-gradient(135deg, #ef4444, #dc2626) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        padding: 0.6rem 1.5rem !important;
        border-radius: 8px !important;
        font-size: 1rem !important;
    }

    .sidebar-router {
        background: #1e1e3a;
        border-radius: 8px;
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.4rem;
        border: 1px solid #2a2a4a;
    }

    .router-active { border-left: 3px solid #22c55e; }
    .router-standby { border-left: 3px solid #f59e0b; }

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 1px solid #2a2a4a;
        border-radius: 10px;
        padding: 1rem;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────
def fetch_api(endpoint: str, method: str = "GET"):
    """Fetch data from the FastAPI backend."""
    try:
        if method == "POST":
            resp = requests.post(f"{API_BASE}{endpoint}", timeout=30)
        else:
            resp = requests.get(f"{API_BASE}{endpoint}", timeout=5)
        return resp.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception as e:
        return {"error": str(e)}


def get_trace_class(log_line: str) -> str:
    """Map log line to CSS class for coloring."""
    line_upper = log_line.upper()
    if "OBSERVE" in line_upper:
        return "observe"
    elif "RETRIEV" in line_upper:
        return "retrieve"
    elif "REASON" in line_upper:
        return "reason"
    elif "HUMAN" in line_upper or "APPROVAL" in line_upper:
        return "human"
    elif "EXECUTOR" in line_upper or "ACT" in line_upper:
        return "act"
    return ""


# ─────────────────────────────────────────────
# Sidebar — Network Topology
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌐 Network Topology")

    topology = fetch_api("/topology")
    if topology and "error" not in topology:
        st.markdown("### Routers")
        for router in topology.get("routers", []):
            status_class = (
                "router-active" if router["status"] == "active" else "router-standby"
            )
            status_icon = "🟢" if router["status"] == "active" else "🟡"
            st.markdown(
                f"""<div class="sidebar-router {status_class}">
                {status_icon} <strong>{router['name']}</strong><br/>
                <small>{router['type'].upper()} — {router['location']} — {router['ip']}</small>
            </div>""",
                unsafe_allow_html=True,
            )

        st.markdown("### Links")
        for link in topology.get("links", []):
            status_icon = "🔗" if link["status"] == "active" else "⏸️"
            st.markdown(
                f"""<div class="sidebar-router">
                {status_icon} <strong>{link['name']}</strong><br/>
                <small>{link['source']} ↔ {link['target']} | {link['bandwidth_gbps']}Gbps | {link['type']}</small>
            </div>""",
                unsafe_allow_html=True,
            )
    else:
        st.warning("⚠️ Cannot connect to API. Start the FastAPI server first.")
        st.code("python -m uvicorn main:app --reload --port 8000", language="bash")

    st.markdown("---")

    # Agent Graph visualization
    st.markdown("### 🧠 Agent Graph")
    st.markdown(
        """
    ```
    observe
       ↓
    retrieve (RAG)
       ↓
    reason & decide
       ↓
    ┌─────────────┐
    │  risk_level  │
    └──┬────────┬──┘
       │ HIGH   │ LOW
       ↓        ↓
    human     act
    approval    ↓
       ↓      END
      act
       ↓
      END
    ```
    """
    )

# ─────────────────────────────────────────────
# Main Header
# ─────────────────────────────────────────────
st.markdown(
    """<div class="main-header">
    <h1>🤖 NetOps Autonomous Agent</h1>
    <p>Observe → Reason → Decide → Act → Learn | ISP Network Operations PoC</p>
</div>""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# Top Metrics Row
# ─────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

telemetry = fetch_api("/telemetry?limit=100")
agent_logs_data = fetch_api("/agent-logs")

if telemetry and "data" in telemetry:
    data_points = telemetry["data"]
    if data_points:
        latest = data_points[-1]
        avg_latency = sum(p["latency_ms"] for p in data_points) / len(data_points)
        anomaly_count = sum(1 for p in data_points if p.get("status") == "anomaly")

        col1.metric("📊 Data Points", len(data_points))
        col2.metric("⚡ Latest Latency", f"{latest['latency_ms']}ms")
        col3.metric("📈 Avg Latency", f"{avg_latency:.1f}ms")
        col4.metric("🚨 Anomalies", anomaly_count)
    else:
        col1.metric("📊 Data Points", 0)
        col2.metric("⚡ Latest Latency", "—")
        col3.metric("📈 Avg Latency", "—")
        col4.metric("🚨 Anomalies", 0)
else:
    col1.metric("📊 Data Points", "—")
    col2.metric("⚡ Latest Latency", "—")
    col3.metric("📈 Avg Latency", "—")
    col4.metric("🚨 Anomalies", "—")

# ─────────────────────────────────────────────
# Simulate Anomaly + Live Chart
# ─────────────────────────────────────────────
chart_col, action_col = st.columns([2, 1])

with chart_col:
    st.markdown("### 📈 Live Telemetry — Latency (ms)")

    if telemetry and "data" in telemetry and telemetry["data"]:
        data_points = telemetry["data"]

        timestamps = [p["timestamp"][-12:-1] for p in data_points]
        latencies = [p["latency_ms"] for p in data_points]
        colors = [
            "#ef4444" if p.get("status") == "anomaly" else "#7c83ff"
            for p in data_points
        ]

        fig = go.Figure()

        # Main latency line
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=latencies,
                mode="lines+markers",
                name="Latency",
                line=dict(color="#7c83ff", width=2),
                marker=dict(
                    color=colors,
                    size=6,
                    line=dict(width=1, color="#ffffff"),
                ),
            )
        )

        # Threshold line
        fig.add_hline(
            y=100,
            line_dash="dash",
            line_color="#ef4444",
            annotation_text="Anomaly Threshold (100ms)",
            annotation_position="top left",
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(26,26,46,0.8)",
            plot_bgcolor="rgba(26,26,46,0.8)",
            height=350,
            margin=dict(l=40, r=20, t=30, b=40),
            xaxis=dict(
                showgrid=False,
                title="Time",
                tickangle=-45,
                nticks=15,
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="rgba(255,255,255,0.05)",
                title="Latency (ms)",
            ),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("⏳ Waiting for telemetry data... Make sure the API server is running.")

with action_col:
    st.markdown("### 🚨 Control Panel")

    st.markdown("")  # spacer

    if st.button("🚨 Simulate Anomaly", key="sim_anomaly", use_container_width=True):
        with st.spinner("Injecting anomaly & running agent..."):
            result = fetch_api("/simulate-anomaly", method="POST")

        if result and result.get("status") == "success":
            st.success("✅ Anomaly simulated! Agent trace below.")
            trace = result.get("agent_trace", {}).get("result", {})

            # Show the action result
            st.markdown(
                f"""<div class="status-card">
                <h4>Action Taken</h4>
                <div class="value">{trace.get('recommended_action', 'N/A')}</div>
                <small>Risk: {trace.get('risk_level', 'N/A').upper()}</small>
            </div>""",
                unsafe_allow_html=True,
            )

            # Show the trace steps
            for log in trace.get("logs", []):
                css_class = get_trace_class(log)
                st.markdown(
                    f'<div class="trace-step {css_class}">{log}</div>',
                    unsafe_allow_html=True,
                )
        elif result:
            st.error(f"❌ Error: {result.get('detail', 'Unknown error')}")
        else:
            st.error("❌ Cannot connect to API server.")

    st.markdown("")  # spacer
    st.markdown(
        """<div class="status-card">
        <h4>Quick Commands</h4>
        <small>
        <strong>API:</strong> <code>uvicorn main:app --port 8000</code><br/>
        <strong>Dashboard:</strong> <code>streamlit run app.py</code>
        </small>
    </div>""",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# Agent Action Log
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🧠 Agent Action Log")

if agent_logs_data and "logs" in agent_logs_data and agent_logs_data["logs"]:
    for i, log_entry in enumerate(reversed(agent_logs_data["logs"])):
        trigger = log_entry.get("trigger", "unknown")
        trigger_icon = "🔄" if trigger == "auto_detection" else "🎯"
        ts = log_entry.get("timestamp", "")[:19]

        with st.expander(
            f"{trigger_icon} Run #{len(agent_logs_data['logs']) - i} — {trigger} — {ts}",
            expanded=(i == 0),
        ):
            if "error" in log_entry:
                st.error(f"Error: {log_entry['error']}")
                continue

            result = log_entry.get("result", {})

            # Summary metrics
            mcol1, mcol2, mcol3 = st.columns(3)
            mcol1.metric("Action", result.get("recommended_action", "N/A"))
            mcol2.metric("Risk Level", result.get("risk_level", "N/A").upper())
            mcol3.metric(
                "Thread", result.get("thread_id", "N/A")[:12]
            )

            # Anomaly info
            anomaly = log_entry.get("anomaly", {})
            st.markdown(
                f"**Anomaly:** {anomaly.get('router', 'N/A')} — "
                f"{anomaly.get('metric', 'N/A')} = {anomaly.get('value', 'N/A')} "
                f"(Z-score: {anomaly.get('zscore', 'N/A')})"
            )

            # Full trace
            st.markdown("**Full Agent Trace:**")
            for log_line in result.get("logs", []):
                css_class = get_trace_class(log_line)
                st.markdown(
                    f'<div class="trace-step {css_class}">{log_line}</div>',
                    unsafe_allow_html=True,
                )

            # RAG Context preview
            ctx = result.get("retrieved_context", "")
            if ctx:
                with st.expander("📚 Retrieved SOP Context"):
                    st.text(ctx[:1000])

            # LLM Reasoning
            reasoning = result.get("llm_reasoning", "")
            if reasoning:
                with st.expander("🧠 LLM Reasoning"):
                    st.markdown(reasoning[:2000])

            # Action result
            st.markdown(
                f"""<div class="trace-step act">
                <strong>Result:</strong> {result.get('action_result', 'N/A')}
            </div>""",
                unsafe_allow_html=True,
            )
else:
    st.info(
        '⏳ No agent runs yet. Click "🚨 Simulate Anomaly" to trigger the agent!'
    )

# ─────────────────────────────────────────────
# Auto-refresh
# ─────────────────────────────────────────────
st.markdown("---")
auto_refresh = st.checkbox("🔄 Auto-refresh (every 5s)", value=False)
if auto_refresh:
    time.sleep(5)
    st.rerun()
