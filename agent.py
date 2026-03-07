"""
agent.py — LangGraph Network Operations Agent with ChromaDB RAG.

Now fully integrates with the backend Control Plane endpoints via the python `requests` library.
This establishes a Complete Closed-Loop Resolution System.
"""

import os
import json
import operator
import requests
from typing import Annotated, List, Optional, TypedDict
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from langchain_community.vectorstores import Chroma

# ─────────────────────────────────────────────
# 1. LLM Setup (Gemini Flash)
# ─────────────────────────────────────────────
api_key = os.getenv("GOOGLE_API_KEY", "").strip()

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=api_key,
    temperature=0.3,
)

# ─────────────────────────────────────────────
# 2. ChromaDB RAG Retriever
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
# 3. Tool Definitions (Making Actual HTTP Requests)
# ─────────────────────────────────────────────
API_BASE = "http://127.0.0.1:8000/api/resolve"

@tool
def reroute_traffic(source_router: str, target_router: str):
    """
    Reroutes network traffic from a congested/failing source router to a healthy target router.
    Args:
        source_router: The router currently experiencing issues (e.g., 'Core-Router-Mumbai').
        target_router: The healthy router to reroute traffic to (e.g., 'Core-Router-Hyderabad').
    """
    try:
        response = requests.post(f"{API_BASE}/reroute", json={"router": source_router, "target_router": target_router})
        response.raise_for_status()
        data = response.json()
        timestamp = datetime.now().isoformat()
        return f"ACTION SUCCESS [{timestamp}]: {data.get('message', 'Rerouted.')}"
    except Exception as e:
        return f"ACTION FAILED: Request to control plane failed. {str(e)}"

@tool
def restart_interface(router: str, interface: str):
    """
    Restarts a specific network interface to resolve hardware degradation or interface flapping.
    Args:
        router: The router name (e.g., 'Core-Router-Mumbai').
        interface: The interface identifier (e.g., 'Gi0/1').
    """
    try:
        response = requests.post(f"{API_BASE}/restart_interface", json={"router": router, "interface": interface})
        response.raise_for_status()
        data = response.json()
        timestamp = datetime.now().isoformat()
        return f"ACTION SUCCESS [{timestamp}]: {data.get('message', 'Interface restarted.')}"
    except Exception as e:
        return f"ACTION FAILED: Request to control plane failed. {str(e)}"

@tool
def adjust_qos(router: str, policy: str):
    """
    Applies a QoS policy to manage congestion.
    Args:
        router: The router name (e.g., 'Edge-Router-Delhi').
        policy: The QoS policy name (e.g., 'EDGE_PROTECT', 'VOIP_PRIORITY').
    """
    try:
        response = requests.post(f"{API_BASE}/adjust_qos", json={"router": router, "policy": policy})
        response.raise_for_status()
        data = response.json()
        timestamp = datetime.now().isoformat()
        return f"ACTION SUCCESS [{timestamp}]: {data.get('message', 'QoS Adjusted.')}"
    except Exception as e:
        return f"ACTION FAILED: Request to control plane failed. {str(e)}"

@tool
def reset_bgp_session(router: str, peer: str = "upstream"):
    """
    Resets a BGP peering session to resolve routing flaps or BGP down anomalies.
    Args:
        router: The router name (e.g., 'Core-Router-Mumbai').
        peer: The BGP peer to reset.
    """
    try:
        response = requests.post(f"{API_BASE}/reset_bgp", json={"router": router})
        response.raise_for_status()
        data = response.json()
        timestamp = datetime.now().isoformat()
        return f"ACTION SUCCESS [{timestamp}]: {data.get('message', 'BGP Reset.')}"
    except Exception as e:
        return f"ACTION FAILED: Request to control plane failed. {str(e)}"

@tool
def escalate_to_noc(issue_summary: str, router: str = "Unknown"):
    """
    Escalates to the human NOC team for complex scenarios where auto-resolution is risky.
    Args:
        issue_summary: Description of the issue.
        router: The impacted router.
    """
    try:
        response = requests.post(f"{API_BASE}/escalate", json={"router": router})
        response.raise_for_status()
        data = response.json()
        timestamp = datetime.now().isoformat()
        return f"ESCALATION [{timestamp}]: {data.get('message', 'Escalated.')}"
    except Exception as e:
        return f"ACTION FAILED: Request to control plane failed. {str(e)}"


TOOL_MAP = {
    "reroute_traffic": reroute_traffic,
    "restart_interface": restart_interface,
    "adjust_qos": adjust_qos,
    "reset_bgp_session": reset_bgp_session,
    "escalate_to_noc": escalate_to_noc,
}

ALL_TOOLS = [reroute_traffic, restart_interface, adjust_qos, reset_bgp_session, escalate_to_noc]

# ─────────────────────────────────────────────
# 4. Agent State (TypedDict)
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
# 5. Graph Nodes
# ─────────────────────────────────────────────
def observe_node(state: NetworkAgentState):
    payload = state.get("anomaly_payload", {})
    return {
        "reasoning_log": [(
            f"Observer: Anomaly detected on {payload.get('router')}. "
            f"{payload.get('metric')}={payload.get('value')} (threshold: {payload.get('threshold')})"
        )]
    }

def retrieve_node(state: NetworkAgentState):
    payload = state.get("anomaly_payload", {})
    query = f"{payload.get('metric')} issue on {payload.get('router')}"
    
    try:
        retriever = get_retriever()
        docs = retriever.invoke(query)
        context = "\n\n---\n\n".join([doc.page_content for doc in docs])
        log_msg = f"Retriever: Found {len(docs)} relevant SOPs for '{query}'"
    except Exception as e:
        context = f"RAG retrieval failed: {str(e)}"
        log_msg = "Retriever: RAG failed."

    return {"retrieved_context": context, "reasoning_log": [log_msg]}

def reason_and_decide_node(state: NetworkAgentState):
    payload = state.get("anomaly_payload", {})
    context = state.get("retrieved_context", "No context available.")
    
    prompt = f"""
    SYSTEM: You are an Autonomous Network Operations AI for an ISP called IndiaNet.
    
    ANOMALY DATA:
    - Router: {payload.get('router', 'Unknown')}
    - Metric: {payload.get('metric', 'Unknown')}
    - Current Value: {payload.get('value', 'N/A')}
    - Latest Telemetry: {json.dumps(payload.get('recent_data', [])[-2:], indent=2)}
    
    RELEVANT SOPs & PAST INCIDENTS (from knowledge base):
    {context[:3000]}
    
    AVAILABLE TOOLS:
    1. 'reroute_traffic': Resolve 'congestion' by routing to a backup. LOW RISK.
    2. 'restart_interface': Resolve 'hardware degradation' or 'CPU spike' or 'interface flap'. LOW RISK.
    3. 'adjust_qos': Apply QoS policy for DDoS/congestion. LOW RISK.
    4. 'reset_bgp_session': Resolve 'BGP down' or route flaps. LOW RISK.
    5. 'escalate_to_noc': Escalate to human NOC team.
    
    MISSION: Determine root cause based on data and SOP, then call ONE appropriate tool.
    Set risk_level to 'high' if uncertain or if it affects multiple routers. Otherwise 'low'.
    """

    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    response = llm_with_tools.invoke([
        SystemMessage(content="You are an expert network operations AI. Analyze and call the tool."),
        HumanMessage(content=prompt),
    ])

    risk_level = "low"
    recommended_action = "escalate_to_noc"
    action_args = json.dumps({"issue_summary": "Fallback escalation.", "router": payload.get('router', 'Unknown')})
    reasoning = response.content or ""

    if response.tool_calls:
        tool_call = response.tool_calls[0]
        recommended_action = tool_call["name"]
        action_args = json.dumps(tool_call["args"])

        if "multiple" in str(tool_call["args"]) or "escalate" in recommended_action:
            risk_level = "high"

    log_msg = f"Reasoner: Decided '{recommended_action}' with args {action_args}. Risk: {risk_level.upper()}."

    return {
        "llm_reasoning": reasoning,
        "recommended_action": recommended_action,
        "action_args": action_args,
        "risk_level": risk_level,
        "reasoning_log": [log_msg],
    }

def human_approval_node(state: NetworkAgentState):
    # Only hit if risk_level == "high"
    action = state.get("recommended_action", "unknown")
    try:
        args = json.loads(state.get("action_args", "{}"))
        router_arg = args.get('router') or args.get('source_router') or "Unknown"
    except json.JSONDecodeError:
        router_arg = "Unknown"
        
    return {
        "human_approved": True, 
        "reasoning_log": [f"Human Approval: Action '{action}' auto-approved for demo."]
    }

def act_node(state: NetworkAgentState):
    tool_name = state.get("recommended_action")
    args_str = state.get("action_args", "{}")

    try:
        args = json.loads(args_str)
    except:
        args = {}

    if tool_name in TOOL_MAP:
        result = TOOL_MAP[tool_name].invoke(args)
    else:
        result = "Error: Tool not found."

    log_msg = f"Executor: {result}"
    return {
        "action_result": str(result),
        "reasoning_log": [log_msg],
        "action_history": [f"ACTION: {tool_name} | ARGS: {args} | RESULT: {result}"],
    }

# ─────────────────────────────────────────────
# 6. Build Graph
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

def route_decision(state: NetworkAgentState):
    if state.get("risk_level", "high") == "high":
        return "human_approval"
    return "act"

workflow.add_conditional_edges("reason_and_decide", route_decision)
workflow.add_edge("human_approval", "act")
workflow.add_edge("act", END)

checkpointer = MemorySaver()
agent_app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval"],
)

def run_agent(anomaly_payload: dict, thread_id: str = "auto") -> dict:
    import uuid
    if thread_id == "auto":
        thread_id = f"anomaly_{uuid.uuid4().hex[:8]}"

    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"anomaly_payload": anomaly_payload, "reasoning_log": [], "action_history": []}

    logs = []
    
    # 1. Stream up to the interruption
    for event in agent_app.stream(initial_state, config=config):
        for node, update in event.items():
            if "reasoning_log" in update:
                logs.append(f"[{node.upper()}] {update['reasoning_log'][-1]}")

    # 2. Check for human permission
    snapshot = agent_app.get_state(config)
    if snapshot.next and "human_approval" in snapshot.next:
        # Auto resume for closed loop demo
        for event in agent_app.stream(None, config=config):
            for node, update in event.items():
                if "reasoning_log" in update:
                    logs.append(f"[{node.upper()}] {update['reasoning_log'][-1]}")

    final_state = agent_app.get_state(config).values
    
    return {
        "thread_id": thread_id,
        "logs": logs,
        "action_result": final_state.get("action_result", "No action taken"),
        "risk_level": final_state.get("risk_level", "unknown"),
        "recommended_action": final_state.get("recommended_action", "none"),
    }
