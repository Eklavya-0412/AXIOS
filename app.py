"""
app.py — Streamlit Dashboard for Autonomous Network Operations.
Human-in-the-loop approval. Hardcoded 10s auto-refresh.
All timestamps IST. Agent errors shown in UI.
"""

import streamlit as st
import requests
import plotly.graph_objects as go
import time

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000"
REFRESH_INTERVAL_SEC = 10

st.set_page_config(
    page_title="NetOps Autonomous Agent",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "last_approval_action" not in st.session_state:
    st.session_state.last_approval_action = None

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem; color: white;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .main-header h1 { margin: 0; font-size: 1.8rem; font-weight: 700; }
    .main-header p { margin: 0.3rem 0 0 0; opacity: 0.75; font-size: 0.9rem; }
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
    .approval-box {
        background: linear-gradient(135deg, #3b0a0a, #1a0505);
        border: 2px solid #ef4444; border-radius: 12px; padding: 1.5rem; margin: 1rem 0;
        color: #fca5a5;
    }
    .approval-box h3 { color: #ef4444; margin: 0 0 0.8rem 0; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def fetch_api(endpoint, method="GET", payload=None):
    try:
        url = f"{API_BASE}{endpoint}"
        if method == "POST":
            return requests.post(url, json=payload, timeout=30).json()
        return requests.get(url, timeout=5).json()
    except Exception as e:
        return {"error": str(e)}

def trace_class(line):
    u = line.upper()
    if "OBSERVE" in u: return "observe"
    if "RETRIEV" in u: return "retrieve"
    if "REASON" in u: return "reason"
    if "HUMAN" in u or "APPROVAL" in u: return "human"
    if "EXECUTOR" in u or "ACT" in u or "ACTION" in u: return "act"
    if "ERROR" in u: return "human"  # Red for errors
    return ""


# ─────────────────────────────────────────────
# Sidebar — Controls
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌐 Network Controllers")
    st.markdown("### 🚨 Inject Anomaly")

    demo_routers = ["Core-Router-Mumbai", "Edge-Router-Delhi", "Core-Router-Delhi"]
    sel_router = st.selectbox("Target Router", demo_routers)
    sel_type = st.selectbox("Anomaly Type", ["congestion", "bgp_down", "cpu_spike", "interface_flap"])

    if st.button("⚡ Inject Anomaly", type="primary", use_container_width=True):
        res = fetch_api("/api/simulate-anomaly", "POST", {"anomaly_type": sel_type, "router_name": sel_router})
        if res and "error" not in res:
            st.success(f"✅ {sel_type} → {sel_router}")
        else:
            st.error(f"Failed: {res.get('error', 'unknown')}")

    st.markdown("---")

    # Live network state
    tele = fetch_api("/telemetry?limit=1")
    if tele and "network_state" in tele:
        st.markdown("### 📡 Router Health")
        for r in demo_routers:
            rs = tele["network_state"].get(r, {})
            flags = {k: v for k, v in rs.items() if isinstance(v, bool) and v}
            bad = len(flags) > 0
            st.markdown(f"{'🔴' if bad else '🟢'} **{r}**")
            if bad:
                st.caption(", ".join(flags.keys()))
            else:
                st.caption("Healthy")
            route = rs.get("current_traffic_route", "Primary-Link-A")
            st.caption(f"Route: {route}")

    st.markdown("---")
    st.caption(f"🔄 Auto-refreshing every {REFRESH_INTERVAL_SEC}s")


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.markdown("""<div class="main-header">
    <h1>🤖 NetOps Autonomous Agent</h1>
    <p>Observe → Reason → Decide → Act → Learn | Closed-Loop with Human-in-the-Loop</p>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# HUMAN-IN-THE-LOOP APPROVAL PANEL
# ─────────────────────────────────────────────
pending = fetch_api("/api/pending-approvals")
if pending and pending.get("count", 0) > 0:
    for item in pending.get("pending", []):
        tid = item.get("thread_id", "unknown")
        st.markdown(f"""<div class="approval-box">
            <h3>🚨 HIGH-RISK ACTION — Awaiting NOC Approval</h3>
            <p><strong>Action:</strong> {item.get('action', 'N/A')}</p>
            <p><strong>Args:</strong> <code>{item.get('action_args', '{}')}</code></p>
            <p><strong>Router:</strong> {item.get('anomaly', {}).get('router', 'N/A')}</p>
            <p><strong>Metric:</strong> {item.get('anomaly', {}).get('metric', 'N/A')} = {item.get('anomaly', {}).get('value', 'N/A')}</p>
            <p><strong>Time:</strong> {item.get('timestamp', 'N/A')}</p>
        </div>""", unsafe_allow_html=True)

        # Show agent trace so far
        for log_line in item.get("logs", []):
            cls = trace_class(log_line)
            st.markdown(f'<div class="trace-step {cls}">{log_line}</div>', unsafe_allow_html=True)

        col_a, col_r = st.columns(2)
        with col_a:
            if st.button(f"✅ APPROVE", key=f"approve_{tid}", type="primary", use_container_width=True):
                res = fetch_api("/api/approve", "POST", {"thread_id": tid})
                st.session_state.last_approval_action = f"Approved: {tid}"
                st.rerun()
        with col_r:
            if st.button(f"❌ REJECT", key=f"reject_{tid}", use_container_width=True):
                res = fetch_api("/api/reject", "POST", {"thread_id": tid})
                st.session_state.last_approval_action = f"Rejected: {tid}"
                st.rerun()

# Show last approval action feedback
if st.session_state.last_approval_action:
    if "Approved" in st.session_state.last_approval_action:
        st.success(f"✅ {st.session_state.last_approval_action}")
    else:
        st.warning(f"❌ {st.session_state.last_approval_action}")
    st.session_state.last_approval_action = None


# ─────────────────────────────────────────────
# Metrics + Chart
# ─────────────────────────────────────────────
full_data = fetch_api("/telemetry?limit=100")

if full_data and "data" in full_data and full_data["data"]:
    pts = full_data["data"]
    latest = pts[-1]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⚡ Latency", f"{latest.get('latency_ms', 0):.1f} ms")
    c2.metric("📉 Pkt Loss", f"{latest.get('packet_loss_pct', 0):.1f} %")
    c3.metric("💻 CPU", f"{latest.get('cpu_utilization_pct', 0):.1f} %")
    c4.metric("🔄 BGP Flaps", f"{latest.get('bgp_flaps_per_min', 0)}")

    st.markdown("### 📈 Live Telemetry (IST)")

    timestamps = [p["timestamp"] for p in pts]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=timestamps, y=[p["latency_ms"] for p in pts],
                             mode="lines+markers", name="Latency (ms)", line=dict(color="#7c83ff", width=2)))
    fig.add_trace(go.Scatter(x=timestamps, y=[p["packet_loss_pct"] for p in pts],
                             mode="lines+markers", name="Pkt Loss (%)", line=dict(color="#ef4444", width=2)))
    fig.add_trace(go.Scatter(x=timestamps, y=[p.get("cpu_utilization_pct", 0) for p in pts],
                             mode="lines+markers", name="CPU (%)", line=dict(color="#f59e0b", width=2)))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(26,26,46,0.8)", plot_bgcolor="rgba(26,26,46,0.8)",
        height=350, margin=dict(l=40, r=20, t=30, b=40),
        xaxis=dict(title="Time (IST)", tickangle=-45, nticks=12),
        yaxis=dict(title="Value"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("⏳ Waiting for telemetry... Start the FastAPI server first.")


# ─────────────────────────────────────────────
# Agent Action Log
# ─────────────────────────────────────────────
st.markdown("### 🧠 Agent Action Log")
logs_data = fetch_api("/agent-logs")
if logs_data and logs_data.get("logs"):
    for i, entry in enumerate(reversed(logs_data["logs"][-5:])):
        ts = entry.get("timestamp", "")
        trigger = entry.get("trigger", "unknown")
        trigger_icons = {"auto_detection": "🔄", "human_approved": "✅", "human_rejected": "❌"}
        icon = trigger_icons.get(trigger, "🧩")

        with st.expander(f"{icon} {trigger} — {ts}", expanded=(i == 0)):
            # Show error tracebacks directly in UI
            if "error" in entry:
                st.error(f"**Agent Error:**\n```\n{entry['error']}\n```")
                continue

            result = entry.get("result", {})

            # Show agent errors from result dict
            if result.get("status") == "error" or result.get("error"):
                st.error(f"**Agent Error:**\n```\n{result.get('error', result.get('action_result', 'Unknown error'))}\n```")

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Action", result.get("recommended_action", "N/A"))
            mc2.metric("Risk", result.get("risk_level", "N/A").upper())
            mc3.metric("Status", result.get("status", "N/A"))

            for line in result.get("logs", []):
                cls = trace_class(line)
                st.markdown(f'<div class="trace-step {cls}">{line}</div>', unsafe_allow_html=True)

            ar = result.get("action_result", "")
            if ar:
                st.markdown(f'<div class="trace-step act"><strong>Result:</strong> {ar}</div>', unsafe_allow_html=True)
else:
    st.info("⏳ No agent runs yet. Inject an anomaly to trigger the agent.")


# ─────────────────────────────────────────────
# Hardcoded 10s auto-refresh
# ─────────────────────────────────────────────
time.sleep(REFRESH_INTERVAL_SEC)
st.rerun()
