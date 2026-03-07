"""
agent.py — LangGraph Network Operations Agent.
Closed-loop: tools POST to FastAPI control plane endpoints.
Human-in-the-loop: graph genuinely halts at human_approval, NO auto-resume.
All timestamps in IST. Full traceback on errors.
"""

import os
import json
import operator
import uuid
import traceback
import requests as http_requests
from typing import Annotated, List, Optional, TypedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_community.vectorstores import Chroma

# ─────────────────────────────────────────────
# IST
# ─────────────────────────────────────────────
IST = ZoneInfo("Asia/Kolkata")

def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S IST")

# ─────────────────────────────────────────────
# 1. LLM
# ─────────────────────────────────────────────
api_key = os.getenv("GOOGLE_API_KEY", "").strip()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=api_key,
    temperature=0.3,
)

# ─────────────────────────────────────────────
# 2. ChromaDB RAG
# ─────────────────────────────────────────────
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "network_sops"
_retriever = None

def get_retriever():
    global _retriever
    if _retriever is None:
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=api_key,
        )
        vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=CHROMA_DIR,
            embedding_function=embeddings,
        )
        _retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    return _retriever

# ─────────────────────────────────────────────
# 3. Tools — Real HTTP calls to FastAPI Control Plane
# ─────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000/api/resolve"

@tool
def reroute_traffic(source_router: str, target_router: str):
    """
    Reroutes traffic from a congested/failing router to a healthy backup router.
    Args:
        source_router: The failing router (e.g., 'Core-Router-Mumbai').
        target_router: The healthy router (e.g., 'Core-Router-Hyderabad').
    """
    try:
        resp = http_requests.post(f"{API_BASE}/reroute", json={"router": source_router, "target_router": target_router}, timeout=10)
        resp.raise_for_status()
        return f"ACTION SUCCESS [{now_ist()}]: {resp.json().get('message')}"
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def restart_interface(router: str, interface: str):
    """
    Restarts a network interface to fix flapping or hardware degradation.
    Args:
        router: Router name (e.g., 'Core-Router-Mumbai').
        interface: Interface ID (e.g., 'Gi0/1').
    """
    try:
        resp = http_requests.post(f"{API_BASE}/restart_interface", json={"router": router, "interface": interface}, timeout=10)
        resp.raise_for_status()
        return f"ACTION SUCCESS [{now_ist()}]: {resp.json().get('message')}"
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def adjust_qos(router: str, policy: str):
    """
    Applies a QoS policy to manage congestion or DDoS.
    Args:
        router: Router name (e.g., 'Edge-Router-Delhi').
        policy: Policy name (e.g., 'EDGE_PROTECT', 'VOIP_PRIORITY').
    """
    try:
        resp = http_requests.post(f"{API_BASE}/adjust_qos", json={"router": router, "policy": policy}, timeout=10)
        resp.raise_for_status()
        return f"ACTION SUCCESS [{now_ist()}]: {resp.json().get('message')}"
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def reset_bgp_session(router: str, peer: str = "upstream"):
    """
    Resets a BGP session to fix routing flaps or BGP down.
    Args:
        router: Router name (e.g., 'Core-Router-Mumbai').
        peer: The BGP peer to reset.
    """
    try:
        resp = http_requests.post(f"{API_BASE}/reset_bgp", json={"router": router}, timeout=10)
        resp.raise_for_status()
        return f"ACTION SUCCESS [{now_ist()}]: {resp.json().get('message')}"
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def escalate_to_noc(issue_summary: str, router: str = "Unknown"):
    """
    Escalates to the NOC team when auto-resolution is too risky.
    Args:
        issue_summary: Description of the issue.
        router: The impacted router.
    """
    try:
        resp = http_requests.post(f"{API_BASE}/escalate", json={"router": router}, timeout=10)
        resp.raise_for_status()
        return f"ESCALATION [{now_ist()}]: {resp.json().get('message')}"
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"


TOOL_MAP = {
    "reroute_traffic": reroute_traffic,
    "restart_interface": restart_interface,
    "adjust_qos": adjust_qos,
    "reset_bgp_session": reset_bgp_session,
    "escalate_to_noc": escalate_to_noc,
}
ALL_TOOLS = list(TOOL_MAP.values())

# ─────────────────────────────────────────────
# 4. State
# ─────────────────────────────────────────────
class NetworkAgentState(TypedDict):
    anomaly_payload: dict
    retrieved_context: str
    llm_reasoning: str
    recommended_action: str
    action_args: Optional[str]
    action_result: str
    risk_level: str
    human_approved: bool
    reasoning_log: Annotated[List[str], operator.add]
    action_history: Annotated[List[str], operator.add]

# ─────────────────────────────────────────────
# 5. Nodes
# ─────────────────────────────────────────────
def observe_node(state: NetworkAgentState):
    p = state.get("anomaly_payload", {})
    return {"reasoning_log": [
        f"Observer [{now_ist()}]: Anomaly on {p.get('router')}. {p.get('metric')}={p.get('value')} (threshold: {p.get('threshold')})"
    ]}

def retrieve_node(state: NetworkAgentState):
    p = state.get("anomaly_payload", {})
    query = f"{p.get('metric')} issue on {p.get('router')}"
    try:
        docs = get_retriever().invoke(query)
        context = "\n\n---\n\n".join([d.page_content for d in docs])
        return {"retrieved_context": context, "reasoning_log": [f"Retriever [{now_ist()}]: Found {len(docs)} SOPs for '{query}'"]}
    except Exception as e:
        return {"retrieved_context": f"RAG failed: {e}", "reasoning_log": [f"Retriever [{now_ist()}]: RAG error — {e}"]}

def reason_and_decide_node(state: NetworkAgentState):
    p = state.get("anomaly_payload", {})
    ctx = state.get("retrieved_context", "No context.")

    prompt = f"""
    You are an Autonomous Network Operations AI for IndiaNet ISP.
    
    ANOMALY:
    - Router: {p.get('router')}
    - Metric: {p.get('metric')}
    - Value: {p.get('value')}
    
    SOPs FROM KNOWLEDGE BASE:
    {ctx[:3000]}
    
    TOOLS:
    1. reroute_traffic(source_router, target_router) — fix congestion by rerouting. LOW RISK.
    2. restart_interface(router, interface) — fix CPU spike or interface flap. LOW RISK.
    3. adjust_qos(router, policy) — apply QoS for DDoS/congestion. LOW RISK.
    4. reset_bgp_session(router, peer) — fix BGP down. HIGH RISK.
    5. escalate_to_noc(issue_summary, router) — escalate to humans. HIGH RISK.
    
    Call ONE tool. reset_bgp_session and escalate_to_noc are HIGH RISK.
    """

    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        response = llm_with_tools.invoke([
            SystemMessage(content="You are an expert network ops AI. Analyze and call the appropriate tool."),
            HumanMessage(content=prompt),
        ])
    except Exception as e:
        # LLM call failed — return error in the log so it shows in UI
        return {
            "llm_reasoning": f"LLM ERROR: {e}",
            "recommended_action": "escalate_to_noc",
            "action_args": json.dumps({"issue_summary": f"LLM failed: {e}", "router": p.get("router", "Unknown")}),
            "risk_level": "high",
            "reasoning_log": [f"Reasoner [{now_ist()}]: LLM CALL FAILED — {e}\n{traceback.format_exc()}"],
        }

    # Defaults (fallback if LLM doesn't call a tool)
    risk_level = "high"
    action = "escalate_to_noc"
    args = json.dumps({"issue_summary": "Fallback: LLM did not call a tool.", "router": p.get("router", "Unknown")})
    reasoning = response.content or ""

    if response.tool_calls:
        tc = response.tool_calls[0]
        action = tc["name"]
        args = json.dumps(tc["args"])
        if action in ("reset_bgp_session", "escalate_to_noc"):
            risk_level = "high"
        else:
            risk_level = "low"

    return {
        "llm_reasoning": reasoning,
        "recommended_action": action,
        "action_args": args,
        "risk_level": risk_level,
        "reasoning_log": [f"Reasoner [{now_ist()}]: Action='{action}', Risk={risk_level.upper()}, Args={args}"],
    }

def human_approval_node(state: NetworkAgentState):
    return {
        "human_approved": True,
        "reasoning_log": [f"Human Approval [{now_ist()}]: Action APPROVED by NOC operator."],
    }

def act_node(state: NetworkAgentState):
    tool_name = state.get("recommended_action", "")
    try:
        args = json.loads(state.get("action_args", "{}"))
    except Exception:
        args = {}

    try:
        if tool_name in TOOL_MAP:
            result = str(TOOL_MAP[tool_name].invoke(args))
        else:
            result = f"Error: Tool '{tool_name}' not found."
    except Exception as e:
        result = f"TOOL EXECUTION ERROR [{now_ist()}]: {e}\n{traceback.format_exc()}"

    return {
        "action_result": result,
        "reasoning_log": [f"Executor [{now_ist()}]: {result}"],
        "action_history": [f"{tool_name} | {args} | {result}"],
    }

# ─────────────────────────────────────────────
# 6. Graph
# ─────────────────────────────────────────────
workflow = StateGraph(NetworkAgentState)
workflow.add_node("observe", observe_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("reason_and_decide", reason_and_decide_node)
workflow.add_node("human_approval", human_approval_node)
workflow.add_node("act", act_node)

workflow.set_entry_point("observe")
workflow.add_edge("observe", "retrieve")
workflow.add_edge("retrieve", "reason_and_decide")

def route_decision(state):
    return "human_approval" if state.get("risk_level") == "high" else "act"

workflow.add_conditional_edges("reason_and_decide", route_decision)
workflow.add_edge("human_approval", "act")
workflow.add_edge("act", END)

checkpointer = MemorySaver()
agent_app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval"],
)

# ─────────────────────────────────────────────
# 7. Public API
# ─────────────────────────────────────────────
def _stream_logs(stream) -> list:
    logs = []
    for event in stream:
        for node, update in event.items():
            if "reasoning_log" in update:
                logs.append(f"[{node.upper()}] {update['reasoning_log'][-1]}")
    return logs

def start_agent(anomaly_payload: dict) -> dict:
    """
    Runs the agent. LOW risk → completes. HIGH risk → halts for human approval.
    All errors are captured and returned in the result dict for UI display.
    """
    thread_id = f"anomaly_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    try:
        logs = _stream_logs(agent_app.stream(
            {"anomaly_payload": anomaly_payload, "reasoning_log": [], "action_history": []},
            config=config,
        ))
    except Exception as e:
        tb = traceback.format_exc()
        return {
            "status": "error",
            "thread_id": thread_id,
            "logs": [f"[AGENT_ERROR] {e}\n{tb}"],
            "recommended_action": "none",
            "action_result": f"Agent stream failed: {e}",
            "risk_level": "unknown",
            "error": f"{e}\n{tb}",
        }

    try:
        snapshot = agent_app.get_state(config)
    except Exception as e:
        return {
            "status": "error",
            "thread_id": thread_id,
            "logs": logs + [f"[STATE_ERROR] Failed to get state: {e}"],
            "recommended_action": "none",
            "action_result": f"State retrieval failed: {e}",
            "risk_level": "unknown",
        }

    if snapshot.next and "human_approval" in snapshot.next:
        vals = snapshot.values
        return {
            "status": "pending_approval",
            "thread_id": thread_id,
            "logs": logs,
            "recommended_action": vals.get("recommended_action", "unknown"),
            "action_args": vals.get("action_args", "{}"),
            "risk_level": "high",
            "action_result": "⏳ Awaiting human approval...",
        }

    vals = agent_app.get_state(config).values
    return {
        "status": "completed",
        "thread_id": thread_id,
        "logs": logs,
        "recommended_action": vals.get("recommended_action", "none"),
        "action_result": vals.get("action_result", "No action"),
        "risk_level": vals.get("risk_level", "low"),
    }

def resume_agent(thread_id: str) -> dict:
    """Resumes the agent after human approval."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        logs = _stream_logs(agent_app.stream(None, config=config))
        vals = agent_app.get_state(config).values
        return {
            "status": "completed",
            "thread_id": thread_id,
            "logs": logs,
            "recommended_action": vals.get("recommended_action", "none"),
            "action_result": vals.get("action_result", "No action"),
            "risk_level": vals.get("risk_level", "high"),
        }
    except Exception as e:
        return {
            "status": "error",
            "thread_id": thread_id,
            "logs": [f"[RESUME_ERROR] {e}\n{traceback.format_exc()}"],
            "recommended_action": "none",
            "action_result": f"Resume failed: {e}",
            "risk_level": "high",
        }
