"""
agent.py — LangGraph Network Operations Agent.
ASPEN PATTERN: Tools write DIRECTLY to network_config.json (no HTTP middleman).
Human-in-the-loop: graph halts at human_approval for HIGH risk actions.
All timestamps IST. Full error tracebacks.
"""

import os
import json
import operator
import uuid
import traceback
import asyncio
import threading
import time as _time
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
IST = ZoneInfo("Asia/Kolkata")
def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S IST")

# ─────────────────────────────────────────────
# Config File I/O (same as in main.py — shared logic)
# ─────────────────────────────────────────────
from pathlib import Path
CONFIG_FILE = Path("network_config.json")
_config_lock = threading.Lock()

def read_config() -> dict:
    with _config_lock:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

def write_config(config: dict):
    with _config_lock:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

# ─────────────────────────────────────────────
# 1. LLM
# ─────────────────────────────────────────────
api_key = os.getenv("GOOGLE_API_KEY", "").strip()
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key, temperature=0.3)

# ─────────────────────────────────────────────
# 2. ChromaDB RAG
# ─────────────────────────────────────────────
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "network_sops"
_vectorstore = None
_retriever = None

def get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=api_key)
        _vectorstore = Chroma(collection_name=COLLECTION_NAME, persist_directory=CHROMA_DIR, embedding_function=embeddings)
    return _vectorstore

def get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = get_vectorstore().as_retriever(search_kwargs={"k": 3})
    return _retriever

# ─────────────────────────────────────────────
# 3. Tools — DIRECT FILE WRITES to network_config.json (Aspen Pattern)
# ─────────────────────────────────────────────

@tool
def reroute_traffic(source_router: str, target_router: str):
    """
    Reroutes traffic from a congested router to a backup path.
    WRITES to network_config.json: changes current_route to Backup-Link-B, clears is_congested.
    Use this for: congestion, high latency.
    Args:
        source_router: The failing router (e.g., 'Core-Router-Mumbai').
        target_router: The backup router (e.g., 'Core-Router-Hyderabad').
    """
    try:
        config = read_config()
        if source_router not in config:
            return f"ACTION FAILED [{now_ist()}]: Router '{source_router}' not found in network_config.json"
        
        backup_route = f"Backup-via-{target_router}"
        config[source_router]["current_route"] = backup_route
        config[source_router]["is_congested"] = False
        config[source_router]["interface_flapping"] = False
        write_config(config)
        
        return f"ACTION SUCCESS [{now_ist()}]: network_config.json updated — {source_router} route changed to '{backup_route}'. Congestion cleared."
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def restart_interface(router: str, interface: str):
    """
    Restarts a router's interface. Sets status='rebooting' in network_config.json, 
    waits 5 seconds, then sets status='online' and clears ALL anomaly flags.
    Use this for: cpu_spike, interface_flapping, hardware degradation.
    Args:
        router: Router name (e.g., 'Core-Router-Mumbai').
        interface: Interface ID (e.g., 'Gi0/1').
    """
    try:
        config = read_config()
        if router not in config:
            return f"ACTION FAILED [{now_ist()}]: Router '{router}' not found in network_config.json"
        
        # Phase 1: Mark as rebooting
        config[router]["status"] = "rebooting"
        write_config(config)
        
        # Phase 2: Simulate boot time
        _time.sleep(5)
        
        # Phase 3: Come back online, clear everything
        config = read_config()
        config[router]["status"] = "online"
        config[router]["is_congested"] = False
        config[router]["bgp_down"] = False
        config[router]["cpu_spiking"] = False
        config[router]["interface_flapping"] = False
        config[router]["current_route"] = "Primary-Link-A"
        write_config(config)
        
        return f"ACTION SUCCESS [{now_ist()}]: network_config.json updated — {router} rebooted. Status: online. All flags cleared."
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def adjust_qos(router: str, policy: str):
    """
    Applies a QoS policy to manage congestion or DDoS.
    WRITES to network_config.json: clears is_congested flag.
    Use this for: packet loss on edge routers, DDoS mitigation.
    Args:
        router: Router name (e.g., 'Edge-Router-Delhi').
        policy: Policy name (e.g., 'EDGE_PROTECT', 'VOIP_PRIORITY').
    """
    try:
        config = read_config()
        if router not in config:
            return f"ACTION FAILED [{now_ist()}]: Router '{router}' not found in network_config.json"
        
        config[router]["is_congested"] = False
        write_config(config)
        
        return f"ACTION SUCCESS [{now_ist()}]: network_config.json updated — QoS '{policy}' applied on {router}. Congestion cleared."
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def reset_bgp_session(router: str, peer: str = "upstream"):
    """
    Resets a BGP session. WRITES to network_config.json: clears bgp_down flag.
    Use this for: bgp_down, routing flaps, 100% packet loss with BGP flaps.
    THIS IS HIGH RISK — requires human approval before execution.
    Args:
        router: Router name (e.g., 'Core-Router-Mumbai').
        peer: The BGP peer to reset.
    """
    try:
        config = read_config()
        if router not in config:
            return f"ACTION FAILED [{now_ist()}]: Router '{router}' not found in network_config.json"
        
        config[router]["bgp_down"] = False
        write_config(config)
        
        return f"ACTION SUCCESS [{now_ist()}]: network_config.json updated — {router} BGP session reset. bgp_down cleared."
    except Exception as e:
        return f"ACTION FAILED [{now_ist()}]: {e}"

@tool
def escalate_to_noc(issue_summary: str, router: str = "Unknown"):
    """
    Escalates to NOC team. Does NOT modify network_config.json.
    THIS IS HIGH RISK — requires human approval.
    Args:
        issue_summary: Description of the issue.
        router: The impacted router.
    """
    return f"ESCALATION [{now_ist()}]: Issue escalated to NOC for {router}. Summary: {issue_summary}"

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
    needs_rollback: bool
    reasoning_log: Annotated[List[str], operator.add]
    action_history: Annotated[List[str], operator.add]

# ─────────────────────────────────────────────
# 5. Nodes
# ─────────────────────────────────────────────
def observe_node(state: NetworkAgentState):
    p = state.get("anomaly_payload", {})
    # Also read current config to give context
    config = read_config()
    router_state = config.get(p.get("router", ""), {})
    return {"reasoning_log": [
        f"Observer [{now_ist()}]: Anomaly on {p.get('router')}. {p.get('metric')}={p.get('value')} (threshold: {p.get('threshold')}). Config state: {json.dumps(router_state)}"
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
    
    # Read current config state for the affected router
    config = read_config()
    router_state = config.get(p.get("router", ""), {})

    prompt = f"""
    You are an Autonomous Network Operations AI for IndiaNet ISP.
    Your tools write DIRECTLY to network_config.json, which is the source of truth.
    
    CURRENT ANOMALY:
    - Router: {p.get('router')}
    - Metric: {p.get('metric')}
    - Value: {p.get('value')}
    - Current config state: {json.dumps(router_state)}
    
    SOPs & KNOWLEDGE BASE:
    {ctx[:3000]}
    
    CRITICAL TOOL SELECTION RULES (follow exactly):
    | Anomaly (config flag)       | Tool to call             | Risk  |
    |----------------------------|--------------------------|-------|
    | is_congested / high latency | reroute_traffic          | LOW   |
    | interface_flapping          | restart_interface        | LOW   |
    | cpu_spiking                | restart_interface        | LOW   |
    | bgp_down                   | reset_bgp_session        | HIGH  |
    | packet_loss (no BGP issue)  | adjust_qos               | LOW   |
    
    AVAILABLE TOOLS:
    1. reroute_traffic(source_router, target_router) — use for congestion. Target a different core router like Core-Router-Hyderabad.
    2. restart_interface(router, interface) — use for cpu_spike, interface_flap. Interface is always "Gi0/1".
    3. adjust_qos(router, policy) — use for DDoS/packet loss. Policy is "EDGE_PROTECT" or "VOIP_PRIORITY".
    4. reset_bgp_session(router, peer) — use for bgp_down ONLY. HIGH RISK.
    5. escalate_to_noc(issue_summary, router) — escalate. HIGH RISK.
    
    INSTRUCTIONS:
    - Look at the config state flags above. Match the TRUE flag to the correct tool.
    - If bgp_down is true, you MUST call reset_bgp_session.
    - If interface_flapping is true, you MUST call restart_interface.
    - If cpu_spiking is true, you MUST call restart_interface.
    - If is_congested is true, you MUST call reroute_traffic.
    - Call exactly ONE tool.
    """

    try:
        llm_with_tools = llm.bind_tools(ALL_TOOLS)
        response = llm_with_tools.invoke([
            SystemMessage(content="You are an expert network ops AI. Match the anomaly flag to the correct tool from the table above. Call exactly one tool."),
            HumanMessage(content=prompt),
        ])
    except Exception as e:
        return {
            "llm_reasoning": f"LLM ERROR: {e}",
            "recommended_action": "escalate_to_noc",
            "action_args": json.dumps({"issue_summary": f"LLM failed: {e}", "router": p.get("router", "Unknown")}),
            "risk_level": "high",
            "reasoning_log": [f"Reasoner [{now_ist()}]: LLM FAILED — {e}\n{traceback.format_exc()}"],
        }

    risk_level = "high"
    action = "escalate_to_noc"
    args = json.dumps({"issue_summary": "Fallback.", "router": p.get("router", "Unknown")})
    reasoning = response.content or ""

    if response.tool_calls:
        tc = response.tool_calls[0]
        action = tc["name"]
        args = json.dumps(tc["args"])
        risk_level = "high" if action in ("reset_bgp_session", "escalate_to_noc") else "low"

    return {
        "llm_reasoning": reasoning,
        "recommended_action": action,
        "action_args": args,
        "risk_level": risk_level,
        "reasoning_log": [f"Reasoner [{now_ist()}]: Action='{action}', Risk={risk_level.upper()}, Args={args}"],
    }

def human_approval_node(state: NetworkAgentState):
    return {"human_approved": True, "reasoning_log": [f"Human Approval [{now_ist()}]: APPROVED by NOC."]}

def act_node(state: NetworkAgentState):
    try:
        import requests
        requests.post("http://127.0.0.1:8000/api/config/backup")
    except:
        pass

    tool_name = state.get("recommended_action", "")
    try:
        args = json.loads(state.get("action_args", "{}"))
    except Exception:
        args = {}
    try:
        result = str(TOOL_MAP[tool_name].invoke(args)) if tool_name in TOOL_MAP else f"Error: Tool '{tool_name}' not found."
    except Exception as e:
        result = f"TOOL ERROR [{now_ist()}]: {e}\n{traceback.format_exc()}"
    return {
        "action_result": result,
        "reasoning_log": [f"Executor [{now_ist()}]: {result}"],
        "action_history": [f"{tool_name} | {args} | {result}"],
    }

def verify_node(state: NetworkAgentState):
    p = state.get("anomaly_payload", {})
    router = p.get("router", "Unknown")
    _time.sleep(3)
    needs_rollback = False
    log = f"Verifier [{now_ist()}]: Health verified."
    try:
        import requests
        res = requests.get(f"http://127.0.0.1:8000/api/config/verify_health?router_name={router}").json()
        if res.get("status") == "success":
            is_healthy = res.get("is_healthy", False)
            if not is_healthy:
                needs_rollback = True
                log = f"Verifier [{now_ist()}]: Health check FAILED. Active flags: {res.get('flags')}"
            else:
                log = f"Verifier [{now_ist()}]: Health check PASSED."
    except Exception as e:
        log = f"Verifier [{now_ist()}]: API error: {e}"
        
    return {
        "needs_rollback": needs_rollback,
        "reasoning_log": [log]
    }

def rollback_node(state: NetworkAgentState):
    log = f"Rollback [{now_ist()}]: Action failed to resolve anomaly. Configuration rolled back."
    try:
        import requests
        requests.post("http://127.0.0.1:8000/api/config/rollback")
    except Exception as e:
        log = f"Rollback [{now_ist()}]: Rollback failed: {e}"
        
    return {
        "action_result": "FAILED - ROLLED BACK",
        "reasoning_log": [log],
        "recommended_action": "escalate_to_noc",
        "action_args": json.dumps({"issue_summary": "Rollback triggered."}),
        "risk_level": "high"
    }

def learn_node(state: NetworkAgentState):
    p = state.get("anomaly_payload", {})
    action = state.get("recommended_action", "Unknown")
    result = state.get("action_result", "Unknown")
    router = p.get("router", "Unknown")
    metric = p.get("metric", "Unknown")
    value = p.get("value", "Unknown")

    post_mortem = f"Incident on {router}: {metric} spiked to {value}. Action taken: {action}. Result: {result}. Date: {now_ist()}"

    history_file = os.path.join("data", "incident_history.md")
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    try:
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(f"- {post_mortem}\n")
    except Exception:
        pass

    try:
        get_vectorstore().add_texts([post_mortem])
        learn_log = f"Learner [{now_ist()}]: Post-mortem saved to incident_history.md and embedded into ChromaDB."
    except Exception as e:
        learn_log = f"Learner [{now_ist()}]: Failed to embed to ChromaDB: {e}"

    return {
        "reasoning_log": [learn_log]
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
workflow.add_node("verify", verify_node)
workflow.add_node("rollback", rollback_node)
workflow.add_node("learn", learn_node)

workflow.set_entry_point("observe")
workflow.add_edge("observe", "retrieve")
workflow.add_edge("retrieve", "reason_and_decide")

def route_decision(state):
    return "human_approval" if state.get("risk_level") == "high" else "act"

def verify_decision(state):
    return "rollback" if state.get("needs_rollback") else "learn"

workflow.add_conditional_edges("reason_and_decide", route_decision)
workflow.add_edge("human_approval", "act")
workflow.add_edge("act", "verify")
workflow.add_conditional_edges("verify", verify_decision)
workflow.add_edge("rollback", "human_approval")
workflow.add_edge("learn", END)

checkpointer = MemorySaver()
agent_app = workflow.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])

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
    thread_id = f"anomaly_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        logs = _stream_logs(agent_app.stream(
            {"anomaly_payload": anomaly_payload, "reasoning_log": [], "action_history": []}, config=config))
    except Exception as e:
        return {"status": "error", "thread_id": thread_id, "logs": [f"[ERROR] {e}\n{traceback.format_exc()}"],
                "recommended_action": "none", "action_result": f"Agent failed: {e}", "risk_level": "unknown", "error": str(e)}

    try:
        snapshot = agent_app.get_state(config)
    except Exception as e:
        return {"status": "error", "thread_id": thread_id, "logs": logs + [f"[ERROR] State: {e}"],
                "recommended_action": "none", "action_result": f"State failed: {e}", "risk_level": "unknown"}

    if snapshot.next and "human_approval" in snapshot.next:
        vals = snapshot.values
        return {"status": "pending_approval", "thread_id": thread_id, "logs": logs,
                "recommended_action": vals.get("recommended_action", "unknown"),
                "action_args": vals.get("action_args", "{}"), "risk_level": "high",
                "action_result": "⏳ Awaiting human approval..."}

    vals = agent_app.get_state(config).values
    return {"status": "completed", "thread_id": thread_id, "logs": logs,
            "recommended_action": vals.get("recommended_action", "none"),
            "action_result": vals.get("action_result", "No action"), "risk_level": vals.get("risk_level", "low")}

def resume_agent(thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        logs = _stream_logs(agent_app.stream(None, config=config))
        vals = agent_app.get_state(config).values
        return {"status": "completed", "thread_id": thread_id, "logs": logs,
                "recommended_action": vals.get("recommended_action", "none"),
                "action_result": vals.get("action_result", "No action"), "risk_level": vals.get("risk_level", "high")}
    except Exception as e:
        return {"status": "error", "thread_id": thread_id, "logs": [f"[ERROR] {e}\n{traceback.format_exc()}"],
                "recommended_action": "none", "action_result": f"Resume failed: {e}", "risk_level": "high"}
