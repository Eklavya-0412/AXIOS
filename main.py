"""
main.py — FastAPI Backend: Network Telemetry Simulator + Control Plane + Agent Orchestration.
All timestamps in IST (Asia/Kolkata). Real closed-loop state management.
Human-in-the-loop support via pending approval queue.
Live JSONL logger for continuous network telemetry.
"""

import os
import json
import random
import asyncio
import math
import uuid
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ─────────────────────────────────────────────
# IST Timezone
# ─────────────────────────────────────────────
IST = ZoneInfo("Asia/Kolkata")

def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S IST")

def now_ist_dt() -> datetime:
    return datetime.now(IST)

# ─────────────────────────────────────────────
# In-Memory Storage
# ─────────────────────────────────────────────
TELEMETRY_BUFFER = deque(maxlen=500)
AGENT_LOGS = []
LATENCY_HISTORY = deque(maxlen=50)
PENDING_APPROVALS = {}

# Live JSONL log file
LOG_FILE = Path("live_network_logs.jsonl")

# Load topology
TOPOLOGY_FILE = os.path.join("data", "topology.json")
try:
    with open(TOPOLOGY_FILE, "r") as f:
        TOPOLOGY = json.load(f)
    ROUTERS = [r["name"] for r in TOPOLOGY["routers"]]
except Exception:
    TOPOLOGY = {"routers": [], "links": []}
    ROUTERS = ["Core-Router-Mumbai", "Edge-Router-Delhi", "Core-Router-Delhi"]

# ─────────────────────────────────────────────
# GLOBAL NETWORK STATE (enriched with routing info)
# ─────────────────────────────────────────────
NETWORK_STATE = {
    router: {
        "is_congested": False,
        "bgp_down": False,
        "cpu_spiking": False,
        "interface_flapping": False,
        "current_traffic_route": "Primary-Link-A",
        "traffic_amount_mbps": round(random.uniform(200, 800), 1),
    }
    for router in ROUTERS
}

# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class AnomalyRequest(BaseModel):
    anomaly_type: str
    router_name: str

class ResolveRequest(BaseModel):
    router: str
    target_router: str | None = None
    interface: str | None = None
    policy: str | None = None

class ApprovalAction(BaseModel):
    thread_id: str

# ─────────────────────────────────────────────
# Telemetry Generator
# ─────────────────────────────────────────────
def calculate_zscore(value: float, history: deque) -> float:
    if len(history) < 10:
        return 0.0
    values = list(history)
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 1.0
    return (value - mean) / std

def generate_telemetry_point(force_router: str | None = None):
    router = force_router if force_router else random.choice(ROUTERS[:4])
    state = NETWORK_STATE.get(router, {})

    # Healthy baseline
    latency = max(5, random.gauss(20, 5))
    packet_loss = random.uniform(0.0, 0.3)
    cpu_util = random.uniform(10, 30)
    bgp_flaps = 0
    is_anomalous = False

    # Apply persistent penalties from NETWORK_STATE
    if state.get("is_congested"):
        latency = random.uniform(250, 400)
        packet_loss = random.uniform(5.0, 15.0)
        is_anomalous = True
    if state.get("bgp_down"):
        packet_loss = 100.0
        bgp_flaps = random.randint(1, 5)
        is_anomalous = True
    if state.get("cpu_spiking"):
        cpu_util = random.uniform(90, 99)
        latency += random.uniform(50, 100)
        is_anomalous = True
    if state.get("interface_flapping"):
        packet_loss = random.uniform(20.0, 50.0)
        latency += random.uniform(20, 50)
        is_anomalous = True

    # Traffic amount: degraded if anomalous
    traffic_mbps = round(random.uniform(50, 200), 1) if is_anomalous else round(random.uniform(400, 900), 1)

    return {
        "timestamp": now_ist(),
        "router": router,
        "latency_ms": round(max(5, latency), 2),
        "packet_loss_pct": round(packet_loss, 3),
        "cpu_utilization_pct": round(cpu_util, 1),
        "bgp_flaps_per_min": bgp_flaps,
        "interface": "Gi0/1",
        "status": "anomaly" if is_anomalous else "normal",
    }

def write_jsonl_log(point: dict):
    """Append a log entry to live_network_logs.jsonl every tick."""
    router = point["router"]
    state = NETWORK_STATE.get(router, {})
    is_active = any([
        state.get("is_congested", False),
        state.get("bgp_down", False),
        state.get("cpu_spiking", False),
        state.get("interface_flapping", False),
    ])
    entry = {
        "timestamp": point["timestamp"],
        "router_name": router,
        "current_traffic_route": state.get("current_traffic_route", "Primary-Link-A"),
        "traffic_amount_mbps": round(random.uniform(50, 200) if is_active else random.uniform(400, 900), 1),
        "anomaly_status": "active" if is_active else "resolved",
        "latency_ms": point["latency_ms"],
        "packet_loss_pct": point["packet_loss_pct"],
        "cpu_utilization_pct": point["cpu_utilization_pct"],
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Non-blocking

# ─────────────────────────────────────────────
# Background Telemetry Task
# ─────────────────────────────────────────────
# Tracks last agent trigger time per router to prevent rapid re-firing
_last_agent_trigger: dict[str, datetime] = {}
AGENT_COOLDOWN_SECONDS = 25

async def telemetry_background_task():
    global _last_agent_trigger
    while True:
        point = generate_telemetry_point()
        TELEMETRY_BUFFER.append(point)
        LATENCY_HISTORY.append(point["latency_ms"])

        # Write to JSONL log
        write_jsonl_log(point)

        # Check if this point is anomalous
        is_bad = (
            point["packet_loss_pct"] > 10.0
            or point["cpu_utilization_pct"] > 90.0
            or abs(calculate_zscore(point["latency_ms"], LATENCY_HISTORY)) > 3.0
        )

        if is_bad:
            router = point["router"]
            now = now_ist_dt()

            # Real cooldown: check last trigger time for THIS router
            last_trigger = _last_agent_trigger.get(router)
            if last_trigger and (now - last_trigger).total_seconds() < AGENT_COOLDOWN_SECONDS:
                await asyncio.sleep(2)
                continue  # Skip, still in cooldown

            _last_agent_trigger[router] = now

            metric = "latency"
            value = point["latency_ms"]
            threshold = 100
            if point["packet_loss_pct"] > 10.0:
                metric, value, threshold = "packet_loss", point["packet_loss_pct"], 5.0
            elif point["cpu_utilization_pct"] > 90.0:
                metric, value, threshold = "cpu_utilization", point["cpu_utilization_pct"], 80.0

            anomaly_payload = {
                "router": router,
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "timestamp": point["timestamp"],
                "recent_data": list(TELEMETRY_BUFFER)[-10:],
            }

            try:
                from agent import start_agent
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, start_agent, anomaly_payload)

                log_entry = {
                    "id": str(uuid.uuid4())[:8],
                    "timestamp": now_ist(),
                    "trigger": "auto_detection",
                    "anomaly": anomaly_payload,
                    "result": result,
                }
                AGENT_LOGS.append(log_entry)

                if result.get("status") == "pending_approval":
                    PENDING_APPROVALS[result["thread_id"]] = {
                        "thread_id": result["thread_id"],
                        "action": result.get("recommended_action"),
                        "action_args": result.get("action_args"),
                        "anomaly": anomaly_payload,
                        "logs": result.get("logs", []),
                        "timestamp": now_ist(),
                    }
            except Exception as e:
                tb = traceback.format_exc()
                AGENT_LOGS.append({
                    "id": str(uuid.uuid4())[:8],
                    "timestamp": now_ist(),
                    "trigger": "auto_detection",
                    "error": f"{str(e)}\n{tb}",
                })

        await asyncio.sleep(2)

# ─────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(telemetry_background_task())
    yield
    task.cancel()

app = FastAPI(title="NetOps Autonomous Agent — API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Telemetry & Log Endpoints
# ─────────────────────────────────────────────
@app.get("/")
def health_check():
    return {"status": "NetOps API is online", "time": now_ist()}

@app.get("/telemetry")
def get_telemetry(limit: int = 100):
    return {"data": list(TELEMETRY_BUFFER)[-limit:], "network_state": NETWORK_STATE}

@app.get("/topology")
def get_topology():
    return TOPOLOGY

@app.get("/agent-logs")
def get_agent_logs():
    return {"logs": AGENT_LOGS, "count": len(AGENT_LOGS)}

# ─────────────────────────────────────────────
# Anomaly Injection
# ─────────────────────────────────────────────
@app.post("/api/simulate-anomaly")
def simulate_anomaly(req: AnomalyRequest):
    if req.router_name not in NETWORK_STATE:
        NETWORK_STATE[req.router_name] = {
            "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False,
            "current_traffic_route": "Primary-Link-A", "traffic_amount_mbps": 500.0,
        }

    type_map = {
        "congestion": "is_congested",
        "bgp_down": "bgp_down",
        "cpu_spike": "cpu_spiking",
        "interface_flap": "interface_flapping",
    }
    flag = type_map.get(req.anomaly_type)
    if not flag:
        raise HTTPException(400, "Unknown anomaly_type")

    NETWORK_STATE[req.router_name][flag] = True

    # Clear cooldown for this router so agent can re-trigger immediately
    _last_agent_trigger.pop(req.router_name, None)

    # Inject spike points for the target router
    for _ in range(3):
        p = generate_telemetry_point(force_router=req.router_name)
        TELEMETRY_BUFFER.append(p)
        LATENCY_HISTORY.append(p["latency_ms"])
        write_jsonl_log(p)

    return {"status": "success", "message": f"{req.anomaly_type} injected on {req.router_name}", "timestamp": now_ist()}

# ─────────────────────────────────────────────
# Control Plane — Resolution Endpoints
# ─────────────────────────────────────────────
@app.post("/api/resolve/reroute")
def resolve_reroute(req: ResolveRequest):
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["is_congested"] = False
        NETWORK_STATE[req.router]["interface_flapping"] = False
        NETWORK_STATE[req.router]["current_traffic_route"] = f"Backup-via-{req.target_router or 'Link-B'}"
        return {"status": "success", "message": f"Traffic rerouted from {req.router} to {req.target_router}. Congestion cleared. [{now_ist()}]"}
    return {"status": "error", "message": f"Router '{req.router}' not found."}

@app.post("/api/resolve/reset_bgp")
def resolve_reset_bgp(req: ResolveRequest):
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["bgp_down"] = False
        return {"status": "success", "message": f"BGP session on {req.router} reset. Session UP. [{now_ist()}]"}
    return {"status": "error", "message": f"Router '{req.router}' not found."}

@app.post("/api/resolve/restart_interface")
def resolve_restart_interface(req: ResolveRequest):
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["interface_flapping"] = False
        NETWORK_STATE[req.router]["cpu_spiking"] = False
        return {"status": "success", "message": f"Interface {req.interface} on {req.router} restarted. Degradation cleared. [{now_ist()}]"}
    return {"status": "error", "message": f"Router '{req.router}' not found."}

@app.post("/api/resolve/adjust_qos")
def resolve_adjust_qos(req: ResolveRequest):
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["is_congested"] = False
        return {"status": "success", "message": f"QoS '{req.policy}' on {req.router}. Congestion cleared. [{now_ist()}]"}
    return {"status": "error", "message": f"Router '{req.router}' not found."}

@app.post("/api/resolve/escalate")
def resolve_escalate(req: ResolveRequest):
    return {"status": "success", "message": f"Escalated to NOC for {req.router}. [{now_ist()}]"}

# ─────────────────────────────────────────────
# Human-in-the-Loop Endpoints
# ─────────────────────────────────────────────
@app.get("/api/pending-approvals")
def get_pending_approvals():
    return {"pending": list(PENDING_APPROVALS.values()), "count": len(PENDING_APPROVALS)}

@app.post("/api/approve")
def approve_action(req: ApprovalAction):
    if req.thread_id not in PENDING_APPROVALS:
        raise HTTPException(404, "No pending approval for this thread_id")
    try:
        from agent import resume_agent
        result = resume_agent(req.thread_id)
        approval_info = PENDING_APPROVALS.pop(req.thread_id, {})
        AGENT_LOGS.append({
            "id": str(uuid.uuid4())[:8],
            "timestamp": now_ist(),
            "trigger": "human_approved",
            "anomaly": approval_info.get("anomaly", {}),
            "result": result,
        })
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": f"{e}\n{traceback.format_exc()}"}

@app.post("/api/reject")
def reject_action(req: ApprovalAction):
    if req.thread_id not in PENDING_APPROVALS:
        raise HTTPException(404, "No pending approval for this thread_id")
    approval_info = PENDING_APPROVALS.pop(req.thread_id, {})
    AGENT_LOGS.append({
        "id": str(uuid.uuid4())[:8],
        "timestamp": now_ist(),
        "trigger": "human_rejected",
        "anomaly": approval_info.get("anomaly", {}),
        "result": {
            "logs": [f"[HUMAN_APPROVAL] Action REJECTED by NOC operator. [{now_ist()}]"],
            "action_result": "Rejected by human.",
            "recommended_action": approval_info.get("action", "N/A"),
            "risk_level": "high",
        },
    })
    return {"status": "rejected", "message": "Action rejected by NOC operator."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
