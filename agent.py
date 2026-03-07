"""
agent.py — LangGraph Network Operations Agent with ChromaDB RAG.

Follows the StateGraph pattern from aspen-main reference:
- TypedDict state with Annotated lists
- MemorySaver checkpointer  
- @tool decorators with .invoke()
- Conditional edges with interrupt_before for human approval
- llm.bind_tools() for structured tool calling
"""

import os
import json
import operator
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
    """Lazy-load the ChromaDB retriever."""
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
# 3. Tool Definitions (following @tool pattern from aspen-main)
# ─────────────────────────────────────────────
@tool
def reroute_traffic(source_router: str, target_router: str):
    """
    Reroutes network traffic from a failing source router to a healthy target router.
    Use this for latency spikes or link failures where an alternate path exists.
    Args:
        source_router: The router currently experiencing issues (e.g., 'Core-Router-Mumbai').
        target_router: The healthy router to reroute traffic to (e.g., 'Core-Router-Hyderabad').
    """
    timestamp = datetime.now().isoformat()
    return (
        f"ACTION SUCCESS [{timestamp}]: Traffic rerouted from {source_router} "
        f"to {target_router}. Alternate path is now active."
    )


@tool
def restart_interface(router: str, interface: str):
    """
    Restarts a specific network interface on a router to resolve link flapping or errors.
    Args:
        router: The router name (e.g., 'Core-Router-Mumbai').
        interface: The interface identifier (e.g., 'Gi0/1').
    """
    timestamp = datetime.now().isoformat()
    return (
        f"ACTION SUCCESS [{timestamp}]: Interface {interface} on {router} "
        f"restarted. Link status: UP."
    )


@tool
def adjust_qos(router: str, policy: str):
    """
    Applies or adjusts a QoS policy on a router to manage congestion or prioritize traffic.
    Args:
        router: The router name (e.g., 'Edge-Router-Delhi').
        policy: The QoS policy name (e.g., 'EDGE_PROTECT', 'VOIP_PRIORITY', 'HIGH_PRIORITY_REROUTE').
    """
    timestamp = datetime.now().isoformat()
    return (
        f"ACTION SUCCESS [{timestamp}]: QoS policy '{policy}' applied to {router}. "
        f"Traffic shaping active."
    )


@tool
def escalate_to_noc(issue_summary: str):
    """
    Escalates an issue to the Network Operations Center (NOC) for human intervention.
    Use this when the issue is too complex or risky for automated resolution.
    Args:
        issue_summary: A brief description of the issue and what has been tried.
    """
    timestamp = datetime.now().isoformat()
    return (
        f"ESCALATION [{timestamp}]: Issue escalated to NOC Tier 2. "
        f"Summary: {issue_summary}. Ticket ID: NOC-{hash(issue_summary) % 10000:04d}"
    )


TOOL_MAP = {
    "reroute_traffic": reroute_traffic,
    "restart_interface": restart_interface,
    "adjust_qos": adjust_qos,
    "escalate_to_noc": escalate_to_noc,
}

ALL_TOOLS = [reroute_traffic, restart_interface, adjust_qos, escalate_to_noc]


# ─────────────────────────────────────────────
# 4. Agent State (TypedDict, following aspen-main pattern)
# ─────────────────────────────────────────────
class NetworkAgentState(TypedDict):
    anomaly_payload: dict  # Incoming anomaly from FastAPI
    retrieved_context: str  # RAG results from ChromaDB
    llm_reasoning: str  # LLM analysis output
    recommended_action: str  # Tool name chosen
    action_args: Optional[str]  # JSON string of tool args
    action_result: str  # Execution result
    risk_level: str  # "low" or "high"
    human_approved: bool  # Gate for high-risk actions

    # Append-only logs (using operator.add like aspen-main)
    reasoning_log: Annotated[List[str], operator.add]
    action_history: Annotated[List[str], operator.add]


# ─────────────────────────────────────────────
# 5. Graph Nodes
# ─────────────────────────────────────────────
def observe_node(state: NetworkAgentState):
    """Node 1: Receives and logs the anomaly payload."""
    payload = state.get("anomaly_payload", {})
    router = payload.get("router", "Unknown")
    metric = payload.get("metric", "Unknown")
    value = payload.get("value", "N/A")
    threshold = payload.get("threshold", "N/A")

    log_msg = (
        f"Observer: Anomaly detected on {router}. "
        f"{metric}={value} (threshold: {threshold})"
    )

    return {
        "reasoning_log": [log_msg],
    }


def retrieve_node(state: NetworkAgentState):
    """Node 2: Queries ChromaDB for relevant SOPs and past incidents."""
    payload = state.get("anomaly_payload", {})
    router = payload.get("router", "")
    metric = payload.get("metric", "latency")

    query = f"{metric} issue on {router}"

    try:
        retriever = get_retriever()
        docs = retriever.invoke(query)
        context = "\n\n---\n\n".join([doc.page_content for doc in docs])
    except Exception as e:
        context = f"RAG retrieval failed: {str(e)}"

    log_msg = f"Retriever: Found {len(docs) if 'docs' in dir() else 0} relevant SOPs for '{query}'"

    return {
        "retrieved_context": context,
        "reasoning_log": [log_msg],
    }


def reason_and_decide_node(state: NetworkAgentState):
    """
    Node 3: LLM analyzes telemetry + RAG context and decides which tool to use.
    Uses llm.bind_tools() pattern from aspen-main's decider_node.
    """
    payload = state.get("anomaly_payload", {})
    context = state.get("retrieved_context", "No context available.")
    history = state.get("action_history", [])

    prompt = f"""
    SYSTEM: You are an Autonomous Network Operations AI for an ISP called IndiaNet.
    
    ANOMALY DATA:
    - Router: {payload.get('router', 'Unknown')}
    - Metric: {payload.get('metric', 'Unknown')}
    - Current Value: {payload.get('value', 'N/A')}
    - Threshold: {payload.get('threshold', 'N/A')}
    - Recent Telemetry: {json.dumps(payload.get('recent_data', [])[-5:], indent=2)}
    
    RELEVANT SOPs & PAST INCIDENTS (from knowledge base):
    {context[:3000]}
    
    PAST ACTIONS TAKEN: {json.dumps(history[-5:])}
    
    AVAILABLE TOOLS:
    1. 'reroute_traffic': Reroute traffic from failing router to healthy one. LOW RISK for single-link issues.
    2. 'restart_interface': Restart a network interface. LOW RISK.
    3. 'adjust_qos': Apply QoS policy for congestion/DDoS. LOW RISK.
    4. 'escalate_to_noc': Escalate to human NOC team. Use for complex/multi-failure scenarios. LOW RISK.
    
    RISK GUIDELINES:
    - Actions affecting a single interface or applying rate-limiting = LOW risk
    - Rerouting traffic for a single router with known backup = LOW risk
    - Actions affecting core infrastructure or multiple routers = HIGH risk
    - Actions when root cause is unclear = HIGH risk
    
    MISSION:
    1. Diagnose the root cause based on the anomaly data and SOPs.
    2. Choose the most appropriate tool.
    3. Determine if this is LOW or HIGH risk.
    
    Call the appropriate tool now.
    """

    # Use bind_tools pattern from aspen-main
    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    response = llm_with_tools.invoke([
        SystemMessage(content="You are an expert network operations AI. Analyze the anomaly and call the most appropriate tool."),
        HumanMessage(content=prompt),
    ])

    # Parse tool calls (same pattern as aspen-main's decider_node)
    risk_level = "low"
    recommended_action = "escalate_to_noc"
    action_args = json.dumps({"issue_summary": "Anomaly detected, manual review needed"})
    reasoning = response.content or ""

    if response.tool_calls:
        tool_call = response.tool_calls[0]
        recommended_action = tool_call["name"]
        action_args = json.dumps(tool_call["args"])

        # Determine risk level based on action + context
        if recommended_action == "reroute_traffic":
            # High risk if multiple failures mentioned or router is completely down
            if "unreachable" in context.lower() or "power" in context.lower():
                risk_level = "high"
            else:
                risk_level = "low"
        elif recommended_action in ("restart_interface", "adjust_qos", "escalate_to_noc"):
            risk_level = "low"
        else:
            risk_level = "high"

    log_msg = (
        f"Reasoner: Decided '{recommended_action}' with args {action_args}. "
        f"Risk: {risk_level.upper()}. Reasoning: {reasoning[:200]}"
    )

    return {
        "llm_reasoning": reasoning,
        "recommended_action": recommended_action,
        "action_args": action_args,
        "risk_level": risk_level,
        "reasoning_log": [log_msg],
    }


def human_approval_node(state: NetworkAgentState):
    """
    Node 4 (conditional): Pass-through for high-risk actions.
    Uses interrupt_before pattern from aspen-main's sentry_node.
    In demo mode, auto-approves.
    """
    action = state.get("recommended_action", "unknown")
    args = state.get("action_args", "{}")
    log_msg = (
        f"Human Approval: HIGH-RISK action '{action}' requires approval. "
        f"Args: {args}. Auto-approved for demo."
    )
    return {
        "human_approved": True,
        "reasoning_log": [log_msg],
    }


def act_node(state: NetworkAgentState):
    """
    Node 5: Executes the chosen tool.
    Uses the tool_map + .invoke() pattern from aspen-main's executor_node.
    """
    tool_name = state.get("recommended_action", "")
    args_str = state.get("action_args", "{}")

    try:
        args = json.loads(args_str)
    except json.JSONDecodeError:
        args = {}

    if tool_name in TOOL_MAP:
        result = TOOL_MAP[tool_name].invoke(args)
    else:
        result = f"Error: Tool '{tool_name}' not found in tool map."

    action_record = f"ACTION: {tool_name} | ARGS: {args} | RESULT: {result}"
    log_msg = f"Executor: {result}"

    return {
        "action_result": str(result),
        "reasoning_log": [log_msg],
        "action_history": [action_record],
    }


# ─────────────────────────────────────────────
# 6. Build the Graph (following aspen-main pattern)
# ─────────────────────────────────────────────
def route_decision(state: NetworkAgentState):
    """Conditional edge: route to human_approval for high-risk, act for low-risk."""
    risk = state.get("risk_level", "high")
    if risk == "high":
        return "human_approval"
    return "act"


# Build the workflow
workflow = StateGraph(NetworkAgentState)

# Add nodes
workflow.add_node("observe", observe_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("reason_and_decide", reason_and_decide_node)
workflow.add_node("human_approval", human_approval_node)
workflow.add_node("act", act_node)

# Set entry point
workflow.set_entry_point("observe")

# Add edges
workflow.add_edge("observe", "retrieve")
workflow.add_edge("retrieve", "reason_and_decide")

# Conditional edge from reason_and_decide
workflow.add_conditional_edges(
    "reason_and_decide",
    route_decision,
    {
        "human_approval": "human_approval",
        "act": "act",
    },
)
workflow.add_edge("human_approval", "act")
workflow.add_edge("act", END)

# Compile with checkpointer and human-in-the-loop interrupt
checkpointer = MemorySaver()
agent_app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval"],
)


# ─────────────────────────────────────────────
# 7. Public API (called from main.py)
# ─────────────────────────────────────────────
def get_graph_diagram():
    """Returns a Mermaid-compatible string to render the agent graph."""
    return agent_app.get_graph().draw_mermaid()


def run_agent(anomaly_payload: dict, thread_id: str = "auto") -> dict:
    """
    Run the full agent pipeline for an anomaly.
    Returns the final state with the complete trace.
    """
    import uuid

    if thread_id == "auto":
        thread_id = f"anomaly_{uuid.uuid4().hex[:8]}"

    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "anomaly_payload": anomaly_payload,
        "reasoning_log": [],
        "action_history": [],
    }

    # Stream through the graph (same pattern as aspen-main's server.py)
    logs = []
    for event in agent_app.stream(initial_state, config=config):
        for node, update in event.items():
            if "reasoning_log" in update:
                entry = f"[{node.upper()}] {update['reasoning_log'][-1]}"
                logs.append(entry)

    # Check if interrupted at human_approval
    snapshot = agent_app.get_state(config)
    if snapshot.next and "human_approval" in snapshot.next:
        # Auto-resume for demo (like aspen-main's approve_action)
        for event in agent_app.stream(None, config=config):
            for node, update in event.items():
                if "reasoning_log" in update:
                    entry = f"[{node.upper()}] {update['reasoning_log'][-1]}"
                    logs.append(entry)

    # Get final state
    final_state = agent_app.get_state(config).values

    return {
        "thread_id": thread_id,
        "logs": logs,
        "action_result": final_state.get("action_result", "No action taken"),
        "risk_level": final_state.get("risk_level", "unknown"),
        "recommended_action": final_state.get("recommended_action", "none"),
        "llm_reasoning": final_state.get("llm_reasoning", ""),
        "retrieved_context": final_state.get("retrieved_context", "")[:500],
    }
