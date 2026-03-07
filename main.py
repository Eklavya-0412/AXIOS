"""
main.py — FastAPI Backend: Digital Twin Network Simulator.
Reads network_config.json as the single source of truth.
Agent tools write directly to the config file (no HTTP resolution needed).
FastAPI handles: telemetry generation, anomaly injection, human-in-the-loop, and live logging.
"""

import os
import json
import random
import asyncio
import math
import uuid
import traceback
import threading
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
# IST
# ─────────────────────────────────────────────
IST = ZoneInfo("Asia/Kolkata")

def now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S IST")

def now_ist_dt() -> datetime:
    return datetime.now(IST)

# ─────────────────────────────────────────────
# Config File I/O
# ─────────────────────────────────────────────
CONFIG_FILE = Path("network_config.json")
_config_lock = threading.Lock()

DEFAULT_CONFIG = {
    "Core-Router-Mumbai": {"status": "online", "current_route": "Primary-Link-A", "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False},
    "Core-Router-Delhi": {"status": "online", "current_route": "Primary-Link-A", "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False},
    "Core-Router-Hyderabad": {"status": "online", "current_route": "Primary-Link-A", "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False},
    "Core-Router-Chennai": {"status": "online", "current_route": "Primary-Link-A", "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False},
    "Edge-Router-Delhi": {"status": "online", "current_route": "Primary-Link-A", "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False},
    "Edge-Router-Kolkata": {"status": "online", "current_route": "Primary-Link-A", "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False},
}

def read_config() -> dict:
    with _config_lock:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            write_config_unsafe(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

def write_config(config: dict):
    with _config_lock:
        write_config_unsafe(config)

def write_config_unsafe(config: dict):
    """Write without acquiring lock (for use inside already-locked contexts)."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

if not CONFIG_FILE.exists():
    write_config(DEFAULT_CONFIG)

# ─────────────────────────────────────────────
# In-Memory Storage
# ─────────────────────────────────────────────
TELEMETRY_BUFFER = deque(maxlen=500)
AGENT_LOGS = []
LATENCY_HISTORY = deque(maxlen=50)
PENDING_APPROVALS = {}
LOG_FILE = Path("live_network_logs.jsonl")

# Load topology
TOPOLOGY_FILE = os.path.join("data", "topology.json")
try:
    with open(TOPOLOGY_FILE, "r") as f:
        TOPOLOGY = json.load(f)
    ROUTERS = [r["name"] for r in TOPOLOGY["routers"]]
except Exception:
    TOPOLOGY = {"routers": [], "links": []}
    ROUTERS = list(DEFAULT_CONFIG.keys())

# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class AnomalyRequest(BaseModel):
    anomaly_type: str
    router_name: str

class ApprovalAction(BaseModel):
    thread_id: str

# ─────────────────────────────────────────────
# Telemetry from Digital Twin
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
    """Reads network_config.json LIVE on every call."""
    config = read_config()
    router = force_router if force_router else random.choice(ROUTERS[:4])
    state = config.get(router, {})

    status = state.get("status", "online")
    route = state.get("current_route", "Primary-Link-A")

    # Rebooting → downtime
    if status == "rebooting":
        return {
            "timestamp": now_ist(), "router": router,
            "latency_ms": 0, "packet_loss_pct": 100.0, "cpu_utilization_pct": 0,
            "bgp_flaps_per_min": 0, "interface": "Gi0/1", "current_route": route, "status": "rebooting",
        }

    # Healthy baseline
    latency = max(5, random.gauss(20, 5))
    packet_loss = random.uniform(0.0, 0.3)
    cpu_util = random.uniform(10, 30)
    bgp_flaps = 0
    is_anomalous = False

    # Congestion on primary link → bad. On backup → healthy (agent fixed it!)
    if state.get("is_congested") and route == "Primary-Link-A":
        latency = random.uniform(250, 400)
        packet_loss = random.uniform(5.0, 15.0)
        is_anomalous = True
    elif state.get("is_congested") and route != "Primary-Link-A":
        latency = max(5, random.gauss(25, 5))
        packet_loss = random.uniform(0.0, 0.5)

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

    return {
        "timestamp": now_ist(), "router": router,
        "latency_ms": round(max(0, latency), 2), "packet_loss_pct": round(packet_loss, 3),
        "cpu_utilization_pct": round(cpu_util, 1), "bgp_flaps_per_min": bgp_flaps,
        "interface": "Gi0/1", "current_route": route,
        "status": "anomaly" if is_anomalous else "normal",
    }

def write_jsonl_log(point: dict):
    config = read_config()
    router = point["router"]
    r_state = config.get(router, {})
    is_active = any([
        r_state.get("is_congested") and r_state.get("current_route") == "Primary-Link-A",
        r_state.get("bgp_down"), r_state.get("cpu_spiking"), r_state.get("interface_flapping"),
        r_state.get("status") == "rebooting",
    ])
    entry = {
        "timestamp": point["timestamp"], "router_name": router,
        "current_traffic_route": r_state.get("current_route", "Primary-Link-A"),
        "traffic_amount_mbps": round(random.uniform(50, 200) if is_active else random.uniform(400, 900), 1),
        "anomaly_status": "active" if is_active else "resolved",
        "latency_ms": point["latency_ms"], "packet_loss_pct": point["packet_loss_pct"],
        "cpu_utilization_pct": point["cpu_utilization_pct"],
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

# ─────────────────────────────────────────────
# Background Task
# ─────────────────────────────────────────────
_last_agent_trigger: dict[str, datetime] = {}
AGENT_COOLDOWN_SECONDS = 25

async def telemetry_background_task():
    global _last_agent_trigger
    while True:
        point = generate_telemetry_point()
        TELEMETRY_BUFFER.append(point)
        LATENCY_HISTORY.append(point["latency_ms"])
        write_jsonl_log(point)

        is_bad = (
            point["packet_loss_pct"] > 10.0
            or point["cpu_utilization_pct"] > 90.0
            or abs(calculate_zscore(point["latency_ms"], LATENCY_HISTORY)) > 3.0
        )

        if is_bad and point["status"] != "rebooting":
            router = point["router"]
            now = now_ist_dt()
            last_trigger = _last_agent_trigger.get(router)
            if last_trigger and (now - last_trigger).total_seconds() < AGENT_COOLDOWN_SECONDS:
                await asyncio.sleep(2)
                continue

            _last_agent_trigger[router] = now

            metric = "latency"
            value = point["latency_ms"]
            threshold = 100
            if point["packet_loss_pct"] > 10.0:
                metric, value, threshold = "packet_loss", point["packet_loss_pct"], 5.0
            elif point["cpu_utilization_pct"] > 90.0:
                metric, value, threshold = "cpu_utilization", point["cpu_utilization_pct"], 80.0

            anomaly_payload = {
                "router": router, "metric": metric, "value": value,
                "threshold": threshold, "timestamp": point["timestamp"],
                "recent_data": list(TELEMETRY_BUFFER)[-10:],
            }

            try:
                from agent import start_agent
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, start_agent, anomaly_payload)

                AGENT_LOGS.append({
                    "id": str(uuid.uuid4())[:8], "timestamp": now_ist(),
                    "trigger": "auto_detection", "anomaly": anomaly_payload, "result": result,
                })

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
                AGENT_LOGS.append({
                    "id": str(uuid.uuid4())[:8], "timestamp": now_ist(),
                    "trigger": "auto_detection", "error": f"{e}\n{traceback.format_exc()}",
                })

        await asyncio.sleep(2)

# ─────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(telemetry_background_task())
    yield
    task.cancel()

app = FastAPI(title="NetOps Digital Twin API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def health_check():
    return {"status": "NetOps Digital Twin API online", "time": now_ist()}

@app.get("/telemetry")
def get_telemetry(limit: int = 100):
    return {"data": list(TELEMETRY_BUFFER)[-limit:], "network_state": read_config()}

@app.get("/topology")
def get_topology():
    return TOPOLOGY

@app.get("/agent-logs")
def get_agent_logs():
    return {"logs": AGENT_LOGS, "count": len(AGENT_LOGS)}

@app.get("/network-config")
def get_network_config():
    return read_config()

# ─────────────────────────────────────────────
# Anomaly Injection (writes to config file)
# ─────────────────────────────────────────────
@app.post("/api/simulate-anomaly")
def simulate_anomaly(req: AnomalyRequest):
    config = read_config()
    if req.router_name not in config:
        config[req.router_name] = {"status": "online", "current_route": "Primary-Link-A", "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False}

    type_map = {"congestion": "is_congested", "bgp_down": "bgp_down", "cpu_spike": "cpu_spiking", "interface_flap": "interface_flapping"}
    flag = type_map.get(req.anomaly_type)
    if not flag:
        raise HTTPException(400, "Unknown anomaly_type")

    config[req.router_name][flag] = True
    config[req.router_name]["current_route"] = "Primary-Link-A"  # Reset route so congestion is visible
    write_config(config)

    _last_agent_trigger.pop(req.router_name, None)

    for _ in range(3):
        p = generate_telemetry_point(force_router=req.router_name)
        TELEMETRY_BUFFER.append(p)
        LATENCY_HISTORY.append(p["latency_ms"])
        write_jsonl_log(p)

    return {"status": "success", "message": f"network_config.json updated: {req.anomaly_type}=true on {req.router_name}", "timestamp": now_ist()}

# ─────────────────────────────────────────────
# Human-in-the-Loop
# ─────────────────────────────────────────────
@app.get("/api/pending-approvals")
def get_pending_approvals():
    return {"pending": list(PENDING_APPROVALS.values()), "count": len(PENDING_APPROVALS)}

@app.post("/api/approve")
def approve_action(req: ApprovalAction):
    if req.thread_id not in PENDING_APPROVALS:
        raise HTTPException(404, "No pending approval")
    try:
        from agent import resume_agent
        result = resume_agent(req.thread_id)
        info = PENDING_APPROVALS.pop(req.thread_id, {})
        AGENT_LOGS.append({"id": str(uuid.uuid4())[:8], "timestamp": now_ist(), "trigger": "human_approved", "anomaly": info.get("anomaly", {}), "result": result})
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": f"{e}\n{traceback.format_exc()}"}

@app.post("/api/reject")
def reject_action(req: ApprovalAction):
    if req.thread_id not in PENDING_APPROVALS:
        raise HTTPException(404, "No pending approval")
    info = PENDING_APPROVALS.pop(req.thread_id, {})
    AGENT_LOGS.append({
        "id": str(uuid.uuid4())[:8], "timestamp": now_ist(), "trigger": "human_rejected",
        "anomaly": info.get("anomaly", {}),
        "result": {"logs": [f"[HUMAN_APPROVAL] REJECTED [{now_ist()}]"], "action_result": "Rejected.", "recommended_action": info.get("action", "N/A"), "risk_level": "high"},
    })
    return {"status": "rejected", "message": "Rejected by NOC."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
