"""
pages/1_Chaos_Engineering.py — Chaos Monitoring Console.
Read-only view of agent activity log. Anomaly injection has moved to the
standalone Stress Test page served by FastAPI at /stress-test.
"""

import streamlit as st
import requests

# ─────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Chaos Monitoring", page_icon="⚡", layout="wide")

# ── Shared CSS (same palette as app.py) ──────
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
    .main-header p  { margin: 0.3rem 0 0 0; opacity: 0.75; font-size: 0.9rem; }
    .trace-step {
        background: #1a1a2e; border-left: 3px solid #7c83ff; padding: 0.8rem 1rem; margin-bottom: 0.5rem;
        border-radius: 0 8px 8px 0; font-family: 'Courier New', monospace; font-size: 0.82rem; color: #c8c8e8;
    }
    .trace-step.observe  { border-left-color: #00d2ff; }
    .trace-step.retrieve { border-left-color: #a855f7; }
    .trace-step.reason   { border-left-color: #f59e0b; }
    .trace-step.human    { border-left-color: #ef4444; }
    .trace-step.act      { border-left-color: #22c55e; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e, #16213e); border: 1px solid #2a2a4a;
        border-radius: 10px; padding: 1rem;
    }
    .stress-link {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
        border: 2px solid #7c83ff; border-radius: 12px;
        padding: 1.5rem; margin-bottom: 1.5rem; text-align: center;
    }
    .stress-link h3 { color: #7c83ff; margin: 0 0 0.5rem 0; }
    .stress-link p  { color: #c8c8e8; margin: 0; font-size: 0.85rem; }
    .stress-link a  {
        display: inline-block; margin-top: 0.8rem; padding: 0.6rem 1.5rem;
        background: linear-gradient(135deg, #7c83ff, #6366f1); color: white;
        border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.85rem;
    }
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
    if "ERROR" in u: return "human"
    return ""


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ Chaos Monitoring")
    st.caption("View autonomous agent responses to injected anomalies in real time.")
    st.markdown("---")
    st.markdown("📡 **Live monitoring →** NOC Dashboard")
    st.markdown("🔧 **Inject anomalies →** [Stress Test Console](http://127.0.0.1:8000/stress-test)")


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.markdown("""<div class="main-header">
    <h1>⚡ Chaos Monitoring — Agent Activity</h1>
    <p>Track autonomous agent responses to injected anomalies · Approve/reject high-risk actions on the NOC Dashboard</p>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Stress Test Console Link Banner
# ─────────────────────────────────────────────
st.markdown("""<div class="stress-link">
    <h3>🔧 Stress Test Console</h3>
    <p>Anomaly injection has moved to a standalone webpage. Open it in a separate browser to inject
    failures while monitoring effects here and on the NOC Dashboard.</p>
    <a href="http://127.0.0.1:8000/stress-test" target="_blank">Open Stress Test Console ↗</a>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Recent Agent Activity
# ─────────────────────────────────────────────
st.markdown("### 📜 Recent Agent Activity")
st.caption("Latest autonomous responses to injected anomalies")

logs_data = fetch_api("/agent-logs")
if logs_data and logs_data.get("logs"):
    for i, entry in enumerate(reversed(logs_data["logs"][-5:])):
        ts      = entry.get("timestamp", "")
        trigger = entry.get("trigger", "unknown")
        icons   = {"auto_detection": "🔄", "human_approved": "✅", "human_rejected": "❌"}
        icon    = icons.get(trigger, "🧩")

        with st.expander(f"{icon} {trigger} — {ts}", expanded=(i == 0)):
            if "error" in entry:
                st.error(f"```\n{entry['error']}\n```")
                continue

            result = entry.get("result", {})
            if result.get("error"):
                st.error(f"```\n{result['error']}\n```")

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Action", result.get("recommended_action", "N/A"))
            mc2.metric("Risk",   result.get("risk_level", "N/A").upper())
            mc3.metric("Status", result.get("status", "N/A"))

            for line in result.get("logs", []):
                cls = trace_class(line)
                st.markdown(f'<div class="trace-step {cls}">{line}</div>', unsafe_allow_html=True)

            ar = result.get("action_result", "")
            if ar:
                st.markdown(f'<div class="trace-step act"><strong>Result:</strong> {ar}</div>', unsafe_allow_html=True)
else:
    st.info("⏳ No agent activity yet. Open the [Stress Test Console](http://127.0.0.1:8000/stress-test) to inject anomalies.")
