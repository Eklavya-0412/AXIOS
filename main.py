"""
main.py — FastAPI Backend for Network Telemetry Simulation & Agent Orchestration.

Run:
    python -m uvicorn main:app --reload --port 8000
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

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ─────────────────────────────────────────────
# In-Memory Storage
# ─────────────────────────────────────────────
TELEMETRY_BUFFER = deque(maxlen=500)  # Rolling window of telemetry points
AGENT_LOGS = []  # Action log history
LATENCY_HISTORY = deque(maxlen=50)  # For Z-score calculation

# Load topology
TOPOLOGY_FILE = os.path.join("data", "topology.json")
with open(TOPOLOGY_FILE, "r") as f:
    TOPOLOGY = json.load(f)

ROUTERS = [r["name"] for r in TOPOLOGY["routers"]]
ANOMALY_INJECTED = False  # Flag for manual anomaly injection


# ─────────────────────────────────────────────
# Telemetry Generation & Anomaly Detection
# ─────────────────────────────────────────────
def calculate_zscore(value: float, history: deque) -> float:
    """Calculate Z-score for anomaly detection."""
    if len(history) < 10:
        return 0.0
    values = list(history)
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(variance) if variance > 0 else 1.0
    return (value - mean) / std


def generate_telemetry_point(force_anomaly: bool = False):
    """Generate a single telemetry data point."""
    router = random.choice(ROUTERS[:3])  # Focus on core routers

    if force_anomaly:
        router = "Core-Router-Mumbai"
        latency = random.uniform(250, 400)
        packet_loss = random.uniform(3.0, 8.0)
    else:
        latency = random.gauss(20, 5)
        latency = max(5, latency)  # No negative latency
        packet_loss = random.uniform(0.0, 0.3)

    point = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "router": router,
        "latency_ms": round(latency, 2),
        "packet_loss_pct": round(packet_loss, 3),
        "interface": "Gi0/1",
        "status": "anomaly" if force_anomaly else "normal",
    }

    return point


async def telemetry_background_task():
    """Background task: generates telemetry every 2 seconds and checks for anomalies."""
    while True:
        point = generate_telemetry_point()
        TELEMETRY_BUFFER.append(point)
        LATENCY_HISTORY.append(point["latency_ms"])

        # Z-score anomaly detection
        zscore = calculate_zscore(point["latency_ms"], LATENCY_HISTORY)
        if abs(zscore) > 2.5:
            point["status"] = "anomaly"
            point["zscore"] = round(zscore, 2)

            # Trigger agent
            anomaly_payload = {
                "router": point["router"],
                "metric": "latency",
                "value": point["latency_ms"],
                "threshold": 100,
                "zscore": round(zscore, 2),
                "timestamp": point["timestamp"],
                "recent_data": list(TELEMETRY_BUFFER)[-10:],
            }
            try:
                from agent import run_agent

                result = run_agent(anomaly_payload)
                AGENT_LOGS.append(
                    {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trigger": "auto_detection",
                        "anomaly": anomaly_payload,
                        "result": result,
                    }
                )
            except Exception as e:
                AGENT_LOGS.append(
                    {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trigger": "auto_detection",
                        "error": str(e),
                    }
                )

        await asyncio.sleep(2)


# ─────────────────────────────────────────────
# FastAPI App with Lifespan
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    """Start background telemetry task on startup."""
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
    """Returns the latest N telemetry data points."""
    data = list(TELEMETRY_BUFFER)[-limit:]
    return {"data": data, "count": len(data)}


@app.get("/topology")
def get_topology():
    """Returns the network topology."""
    return TOPOLOGY


@app.get("/agent-logs")
def get_agent_logs():
    """Returns all agent action logs."""
    return {"logs": AGENT_LOGS, "count": len(AGENT_LOGS)}


@app.post("/simulate-anomaly")
async def simulate_anomaly():
    """
    Injects a latency spike on Core-Router-Mumbai and triggers the agent.
    This is the 'demo button' endpoint.
    """
    # 1. Inject 5 anomalous data points
    anomaly_points = []
    for _ in range(5):
        point = generate_telemetry_point(force_anomaly=True)
        TELEMETRY_BUFFER.append(point)
        LATENCY_HISTORY.append(point["latency_ms"])
        anomaly_points.append(point)

    # 2. Package the anomaly payload
    anomaly_payload = {
        "router": "Core-Router-Mumbai",
        "metric": "latency",
        "value": anomaly_points[-1]["latency_ms"],
        "threshold": 100,
        "zscore": calculate_zscore(anomaly_points[-1]["latency_ms"], LATENCY_HISTORY),
        "timestamp": anomaly_points[-1]["timestamp"],
        "recent_data": anomaly_points,
    }

    # 3. Invoke the agent
    try:
        from agent import run_agent

        result = run_agent(anomaly_payload)
        log_entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger": "manual_simulation",
            "anomaly": anomaly_payload,
            "result": result,
        }
        AGENT_LOGS.append(log_entry)
        return {"status": "success", "agent_trace": log_entry}
    except Exception as e:
        error_entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger": "manual_simulation",
            "error": str(e),
        }
        AGENT_LOGS.append(error_entry)
        return {"status": "error", "detail": str(e), "log": error_entry}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
