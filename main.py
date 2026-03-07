"""
main.py — FastAPI Backend for Network Telemetry Simulation & Agent Orchestration.
Includes a persistent network state and control plane endpoints to simulate a real closed-loop system.
"""

import os
import json
import random
import asyncio
import math
import uuid
from datetime import datetime, timezone
from collections import deque
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ─────────────────────────────────────────────
# In-Memory Storage & State
# ─────────────────────────────────────────────
TELEMETRY_BUFFER = deque(maxlen=500)  # Rolling window of telemetry points
AGENT_LOGS = []  # Action log history
LATENCY_HISTORY = deque(maxlen=50)  # For Z-score calculation

# Load topology
TOPOLOGY_FILE = os.path.join("data", "topology.json")
try:
    with open(TOPOLOGY_FILE, "r") as f:
        TOPOLOGY = json.load(f)
    ROUTERS = [r["name"] for r in TOPOLOGY["routers"]]
except Exception:
    TOPOLOGY = {"routers": [], "links": []}
    ROUTERS = ["Core-Router-Mumbai", "Edge-Router-Delhi", "Core-Router-Delhi"]

# Global Network State
# Tracks persistent anomalies on routers
NETWORK_STATE = {
    router: {
        "is_congested": False,
        "bgp_down": False,
        "cpu_spiking": False,
        "interface_flapping": False
    } for router in ROUTERS
}

# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────
class AnomalyRequest(BaseModel):
    anomaly_type: str  # "congestion", "bgp_down", "cpu_spike", "interface_flap"
    router_name: str

class ResolveRequest(BaseModel):
    router: str
    target_router: str | None = None
    interface: str | None = None
    policy: str | None = None

# ─────────────────────────────────────────────
# Telemetry Generation & Anomaly Detection
# ─────────────────────────────────────────────
def calculate_zscore(value: float, history: deque) -> float:
    if len(history) < 10:
        return 0.0
    values = list(history)
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 1.0
    return (value - mean) / std

def generate_telemetry_point():
    """Generates telemetry, applying persistent penalties if NETWORK_STATE flags are True."""
    # We round-robin or randomly pick a router
    router = random.choice(ROUTERS[:3])  # Focus on a few core/edge routers for noise
    
    state = NETWORK_STATE.get(router, {})
    
    # Baseline
    latency = random.gauss(20, 5)
    packet_loss = random.uniform(0.0, 0.3)
    cpu_utilization = random.uniform(10, 30)
    bgp_flaps = 0
    status = "normal"
    
    # Apply persistent state effects
    is_anomalous = False
    
    if state.get("is_congested"):
        latency = random.uniform(250, 400)
        packet_loss = random.uniform(5.0, 15.0)
        is_anomalous = True
        
    if state.get("bgp_down"):
        packet_loss = 100.0
        bgp_flaps = random.randint(1, 5)
        is_anomalous = True
        
    if state.get("cpu_spiking"):
        cpu_utilization = random.uniform(90, 99)
        latency += random.uniform(50, 100)
        is_anomalous = True
        
    if state.get("interface_flapping"):
        packet_loss = random.uniform(20.0, 50.0)
        latency += random.uniform(20, 50)
        is_anomalous = True

    latency = max(5, latency)  # Ensure no negative latency
    
    point = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "router": router,
        "latency_ms": round(latency, 2),
        "packet_loss_pct": round(packet_loss, 3),
        "cpu_utilization_pct": round(cpu_utilization, 1),
        "bgp_flaps_per_min": bgp_flaps,
        "interface": "Gi0/1",
        "status": "anomaly" if is_anomalous else "normal",
    }
    
    return point

async def telemetry_background_task():
    """Generates telemetry every 2 seconds and triggers agent on critical Z-scores."""
    while True:
        point = generate_telemetry_point()
        TELEMETRY_BUFFER.append(point)
        
        # We track latency specifically for Core-Router-Mumbai for the Z-score logic, 
        # or use a global one for simplicity. Let's track the point's latency.
        LATENCY_HISTORY.append(point["latency_ms"])
        
        zscore = calculate_zscore(point["latency_ms"], LATENCY_HISTORY)
        
        # Simple threshold check for trigger (latency spike or high packet loss)
        if abs(zscore) > 3.0 or point["packet_loss_pct"] > 10.0 or point["cpu_utilization_pct"] > 90.0:
            point["zscore"] = round(zscore, 2)
            
            # Determine primary fault metric for the payload
            metric = "latency"
            value = point["latency_ms"]
            threshold = 100
            
            if point["packet_loss_pct"] > 10.0:
                metric = "packet_loss"
                value = point["packet_loss_pct"]
                threshold = 5.0
            elif point["cpu_utilization_pct"] > 90.0:
                metric = "cpu_utilization"
                value = point["cpu_utilization_pct"]
                threshold = 80.0

            anomaly_payload = {
                "router": point["router"],
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "zscore": round(zscore, 2),
                "timestamp": point["timestamp"],
                "recent_data": list(TELEMETRY_BUFFER)[-10:],
            }
            
            # Avoid re-triggering constantly while broken
            # We check if an agent run for this router happened in the last 15 seconds
            recently_triggered = False
            now = datetime.now(timezone.utc)
            for log in reversed(AGENT_LOGS):
                if log.get("anomaly", {}).get("router") == point["router"]:
                    try:
                        log_time = datetime.fromisoformat(log["timestamp"])
                        if (now - log_time).total_seconds() < 15:
                            recently_triggered = True
                            break
                    except:
                        pass
            
            if not recently_triggered:
                try:
                    from agent import run_agent
                    # Run agent asynchronously to not block telemetry
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, run_agent, anomaly_payload)
                    
                    AGENT_LOGS.append({
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trigger": "auto_detection",
                        "anomaly": anomaly_payload,
                        "result": result,
                    })
                except Exception as e:
                    AGENT_LOGS.append({
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trigger": "auto_detection",
                        "error": str(e),
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@app.get("/")
def health_check():
    return {"status": "NetOps API is online", "telemetry_points": len(TELEMETRY_BUFFER)}

@app.get("/telemetry")
def get_telemetry(limit: int = 100):
    data = list(TELEMETRY_BUFFER)[-limit:]
    return {"data": data, "count": len(data), "network_state": NETWORK_STATE}

@app.get("/topology")
def get_topology():
    return TOPOLOGY

@app.get("/agent-logs")
def get_agent_logs():
    return {"logs": AGENT_LOGS, "count": len(AGENT_LOGS)}

@app.post("/api/simulate-anomaly")
async def simulate_anomaly(req: AnomalyRequest, background_tasks: BackgroundTasks):
    """
    Injects a PERSISTENT anomaly into the network state.
    """
    if req.router_name not in NETWORK_STATE:
        NETWORK_STATE[req.router_name] = {
            "is_congested": False, "bgp_down": False, "cpu_spiking": False, "interface_flapping": False
        }
        
    if req.anomaly_type == "congestion":
        NETWORK_STATE[req.router_name]["is_congested"] = True
    elif req.anomaly_type == "bgp_down":
        NETWORK_STATE[req.router_name]["bgp_down"] = True
    elif req.anomaly_type == "cpu_spike":
        NETWORK_STATE[req.router_name]["cpu_spiking"] = True
    elif req.anomaly_type == "interface_flap":
        NETWORK_STATE[req.router_name]["interface_flapping"] = True
    else:
        raise HTTPException(status_code=400, detail="Unknown anomaly type")

    # Generate an immediate spike packet to fast-track detection
    for _ in range(3):
        p = generate_telemetry_point()
        # Force the router name to ensure the spike is visible
        p["router"] = req.router_name 
        TELEMETRY_BUFFER.append(p)
        LATENCY_HISTORY.append(p["latency_ms"])

    return {"status": "success", "message": f"{req.anomaly_type} injected on {req.router_name}"}

# ─────────────────────────────────────────────
# Control Plane Endpoints (Resolution)
# ─────────────────────────────────────────────
@app.post("/api/resolve/reroute")
def resolve_reroute(req: ResolveRequest):
    """Fixes congestion or interface flapping by rerouting traffic."""
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["is_congested"] = False
        NETWORK_STATE[req.router]["interface_flapping"] = False
        return {"status": "success", "message": f"Traffic rerouted from {req.router} to {req.target_router}. Congestion/Flapping cleared."}
    return {"status": "error", "message": "Router not found"}

@app.post("/api/resolve/reset_bgp")
def resolve_reset_bgp(req: ResolveRequest):
    """Fixes a BGP down issue."""
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["bgp_down"] = False
        return {"status": "success", "message": f"BGP session reset on {req.router}. Session UP."}
    return {"status": "error", "message": "Router not found"}

@app.post("/api/resolve/restart_interface")
def resolve_restart_interface(req: ResolveRequest):
    """Fixes interface errors or CPU spikes affecting an interface."""
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["interface_flapping"] = False
        NETWORK_STATE[req.router]["cpu_spiking"] = False  # Assume process restart tied to interface
        return {"status": "success", "message": f"Interface {req.interface} restarted on {req.router}. Degradation cleared."}
    return {"status": "error", "message": "Router not found"}

@app.post("/api/resolve/adjust_qos")
def resolve_adjust_qos(req: ResolveRequest):
    """Fixes congestion through QoS adjustments."""
    if req.router in NETWORK_STATE:
        NETWORK_STATE[req.router]["is_congested"] = False
        return {"status": "success", "message": f"QoS policy '{req.policy}' applied on {req.router}. Congestion cleared."}
    return {"status": "error", "message": "Router not found"}

@app.post("/api/resolve/escalate")
def resolve_escalate(req: ResolveRequest):
    """Acknowledgement of NOC escalation."""
    return {"status": "success", "message": f"Ticket escalated to NOC for {req.router}. Manual intervention required."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
