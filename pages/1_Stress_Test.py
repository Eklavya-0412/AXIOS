"""
pages/1_Chaos_Engineering.py — Stress Simulation Console.
Read-only view of agent activity log. Anomaly injection has moved to the
standalone Stress Test page served by FastAPI at /stress-test.
"""

import streamlit as st
import requests

# ─────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Stress Simulation", page_icon="C", layout="wide")

# ── Shared CSS (same palette as app.py) ──────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Base ── */
    .stApp { font-family: 'Inter', sans-serif; background-color: #131314 !important; }
    section[data-testid="stSidebar"] { background-color: #1E1F20 !important; }
    header[data-testid="stHeader"] { background-color: #131314 !important; }
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp span, .stApp label, .stApp li { color: #E3E3E3; }
    .stApp .stCaption, .stApp small { color: #C4C7C5 !important; }
    .stMarkdown hr { border-color: #444746 !important; }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #1E1F20; }
    ::-webkit-scrollbar-thumb { background: #444746; border-radius: 3px; }

    /* ── Header ── */
    .main-header {
        background: #1E1F20; border: 1px solid #444746;
        padding: 1.2rem 1.8rem; border-radius: 10px; margin-bottom: 1.2rem; color: #E3E3E3;
    }
    .main-header h1 { margin: 0; font-size: 1.3rem; font-weight: 600; color: #E3E3E3; }
    .main-header p  { margin: 0.3rem 0 0 0; color: #C4C7C5; font-size: 0.85rem; }

    /* ── Agent Trace Steps ── */
    .trace-step {
        background: #1E1F20; border-left: 3px solid #444746; padding: 0.7rem 1rem; margin-bottom: 0.4rem;
        border-radius: 0 8px 8px 0; font-family: 'Inter', monospace; font-size: 0.8rem; color: #C4C7C5;
    }
    .trace-step.observe  { border-left-color: #A8C7FA; }
    .trace-step.retrieve { border-left-color: #8AB4F8; }
    .trace-step.reason   { border-left-color: #FDE293; }
    .trace-step.human    { border-left-color: #F28B82; }
    .trace-step.act      { border-left-color: #81C995; }

    /* ── Metric Cards ── */
    div[data-testid="stMetric"] {
        background: #1E1F20; border: 1px solid #444746; border-radius: 10px; padding: 1rem;
    }
    div[data-testid="stMetric"] label { color: #C4C7C5 !important; font-size: 0.8rem; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #E3E3E3 !important; }

    /* ── Stress Link Banner ── */
    .stress-link {
        background: #1E1F20; border: 1px solid #444746;
        border-radius: 10px; padding: 1.5rem; margin-bottom: 1.2rem; text-align: center;
    }
    .stress-link h3 { color: #A8C7FA; margin: 0 0 0.5rem 0; font-size: 1rem; font-weight: 600; }
    .stress-link p  { color: #C4C7C5; margin: 0; font-size: 0.85rem; }
    .stress-link a  {
        display: inline-block; margin-top: 0.8rem; padding: 0.6rem 1.5rem;
        background: #A8C7FA; color: #000000;
        border-radius: 20px; text-decoration: none; font-weight: 600; font-size: 0.85rem;
        transition: background 0.2s;
    }
    .stress-link a:hover { background: #8AB4F8; }

    /* ── Buttons ── */
    .stButton > button {
        background: #131314 !important; border: 1px solid #444746 !important;
        color: #A8C7FA !important; border-radius: 20px !important; font-weight: 500;
        transition: background 0.2s;
    }
    .stButton > button:hover { background: #1E1F20 !important; }

    /* ── Expander ── */
    details { background: #1E1F20 !important; border: 1px solid #444746 !important; border-radius: 8px !important; }
    details summary { color: #E3E3E3 !important; }
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
    st.markdown("## Stress Simulation")
    st.caption("View autonomous agent responses to injected anomalies in real time.")


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────
st.markdown("""<div class="main-header">
    <h1>Stress Simulation — Agent Activity</h1>
    <p>Track autonomous agent responses to injected anomalies · Approve/reject high-risk actions on the NOC Dashboard</p>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Stress Test Console Link Banner
# ─────────────────────────────────────────────
st.markdown("""<div class="stress-link">
    <h3>Stress Test Console</h3>
    <p>Anomaly injection has moved to a standalone webpage. Open it in a separate browser to inject
    failures while monitoring effects here and on the NOC Dashboard.</p>
    <a href="http://127.0.0.1:8000/stress-test" target="_blank">Open Stress Test Console ↗</a>
</div>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Recent Agent Activity
# ─────────────────────────────────────────────
st.markdown("### Recent Agent Activity")
st.caption("Latest autonomous responses to injected anomalies")

logs_data = fetch_api("/agent-logs")
if logs_data and logs_data.get("logs"):
    for i, entry in enumerate(reversed(logs_data["logs"][-5:])):
        ts      = entry.get("timestamp", "")
        trigger = entry.get("trigger", "unknown")
        icons   = {"auto_detection": "[auto]", "human_approved": "[approved]", "human_rejected": "[rejected]"}
        icon    = icons.get(trigger, "[event]")

        with st.expander(f"{icon} {trigger} — {ts}", expanded=(i == 0)):
            if "error" in entry:
                st.error(f"```\n{entry['error']}\n```")
                continue

            result = entry.get("result", {})
            if result.get("error"):
                st.error(f"```\n{result['error']}\n```")

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Action", result.get("recommended_action", "N/A"))
            mc2.metric("Risk",   (result.get("risk_level") or "N/A").upper())
            mc3.metric("Status", result.get("status", "N/A"))

            for line in result.get("logs", []):
                cls = trace_class(line)
                st.markdown(f'<div class="trace-step {cls}">{line}</div>', unsafe_allow_html=True)

            ar = result.get("action_result", "")
            if ar:
                st.markdown(f'<div class="trace-step act"><strong>Result:</strong> {ar}</div>', unsafe_allow_html=True)
else:
    st.info("No agent activity yet. Open the [Stress Test Console](http://127.0.0.1:8000/stress-test) to inject anomalies.")
