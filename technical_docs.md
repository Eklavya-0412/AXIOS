# Full Technical Documentation & Tool Breakdown

This document provides a deep dive into the architecture, files, functions, and tools powering the Autonomous Network Operations Agent.

---

## 1. System Files Breakdown

### `network_config.json` (The Digital Twin)
The absolute source of truth for the entire simulation. 
- Contains a JSON object for every router in the topology (e.g., `Core-Router-Mumbai`).
- Maintains state variables: `status` (online/rebooting), `current_route` (defining where traffic flows), and anomaly flags (`is_congested`, `bgp_down`, `cpu_spiking`, `interface_flapping`).
- Both the FastAPI backend and the LangGraph agent constantly read and write to this file to simulate network shifts.

### `main.py` (The Telemetry Engine & API)
Runs the FastAPI server and the core background simulation loop.
- **`generate_telemetry_point()`:** Called every few seconds. Reads `network_config.json`. If it sees flags like `is_congested=True` AND the route is primary, it generates bad (high latency/loss) metrics. If the agent changes the route, it instantly generates healthy metrics.
- **`telemetry_background_task()`:** Runs infinitely using `asyncio`. Pushes telemetry into a fixed-size buffer, appends to `live_network_logs.jsonl`, calculates Z-scores for anomalies, and triggers `start_agent` when thresholds are breached. Implements a 25-second cooldown per router to prevent spam.
- **`/api/simulate-anomaly`:** Endpoint hit by Streamlit to artificially inject an anomaly into `network_config.json` for demo purposes.
- **`/api/approve` & `/api/reject`:** Endpoints for Human-in-the-Loop interactions. Resumes the frozen LangGraph agent state.

### `agent.py` (The Cognitive Brain)
Defines the LangGraph StateMachine and all LLM interactions.
- Builds a 5-node graph:
  1. **`observe_node`:** Parses the anomaly payload and reads the active config flags from the Digital Twin.
  2. **`retrieve_node`:** Pings ChromaDB to pull historical SOPs matching the anomaly context.
  3. **`reason_and_decide_node`:** The LLM prompt. Cross-references the active flags against the SOPs and binds to the available tools to make a decision. Output determines `risk_level`.
  4. **`human_approval_node`:** A checkpoint node. If `risk_level` is high, LangGraph pauses execution right before this node and waits for external API input to resume.
  5. **`act_node`:** Executes the chosen tool and records the result.
- Provides `start_agent()` and `resume_agent()` helper functions to safely stream graph events and capture tracebacks.

### `app.py` (The NOC Streamlit Dashboard)
The pure-Python frontend visualization layer.
- **Telemetry Chart:** Polling FastAPI to draw Plotly graphs of Latency, Packet Loss, and CPU usage.
- **Agent Action Log:** Displays the LLM's step-by-step reasoning trace, including tool outputs and explicit Traceback errors if something crashes.
- **Live Router Config:** A sidebar panel showing the real-time parsing of `network_config.json` so users can visually verify the agent's file modifications.
- **Human-in-the-Loop Panel:** Mounts approval/rejection buttons dynamically when pending approvals are detected in the backend.

### `setup_db.py` 
A pipeline script to populate the local vector database.
- Uses `RecursiveCharacterTextSplitter` to carve `data/sops.md` into contextual chunks.
- Uses Gemini Embeddings to store the text in an SQLite-backed ChromaDB instance (`./chroma_db`).

### `data/sops.md` 
The Standard Operating Procedures documentation. Contains explicit routing tables and "If this, then that" mappings for anomalies, allowing the LLM to ground its decisions in actual company policy rather than guessing.

---

## 2. Tools & Actions Breakdown

All tools are native Python functions decorated with LangChain's `@tool`. They are bound to the LLM so it knows their schemas. These tools do *not* rely on external APIs; they use `json.dump` to immediately mutate `network_config.json`.

### `reroute_traffic(source_router: str, target_router: str)`
- **Purpose:** Shifts traffic off a failing/congested network link to a backup path.
- **Risk Level:** **LOW**
- **How it works:** Opens `network_config.json`, locates `source_router`, updates `current_route` to `Backup-via-{target_router}`, and clears the `is_congested` boolean flag.
- **Trigger Scenario:** High latency, `is_congested=True`.

### `restart_interface(router: str, interface: str)`
- **Purpose:** Power-cycles a line card or port to clear hardware glitches or firmware locks.
- **Risk Level:** **LOW**
- **How it works:** Opens the config, sets `status` to `rebooting`, saves the file, invokes `time.sleep(5)` to simulate a cold boot duration, then sets `status` to `online` while aggressively clearing all anomaly bools (`cpu_spiking`, `interface_flapping`, etc.).
- **Trigger Scenario:** Link flapping, hardware degradation, aggressive CPU spiking.

### `adjust_qos(router: str, policy: str)`
- **Purpose:** Reprioritizes traffic queues (Quality of Service) to mitigate DDos overflow or prioritize VoIP.
- **Risk Level:** **LOW**
- **How it works:** Modifies `network_config.json` to clear the `is_congested` flag under the premise that rate-limiting successfully stopped the queue overflow.
- **Trigger Scenario:** Volumetric packet loss on an Edge router without BGP disruption.

### `reset_bgp_session(router: str, peer: str)`
- **Purpose:** Tears down and rebuilds peering with an external upstream provider to fix routing table corruption. 
- **Risk Level:** **HIGH** (Halts the agent).
- **How it works:** After human approval is granted, opens the config file and resets `bgp_down=False`.
- **Trigger Scenario:** 100% packet loss associated with `bgp_down=True` flags.

### `escalate_to_noc(issue_summary: str, router: str)`
- **Purpose:** Safely exits the autonomous loop if the LLM cannot confidently match the anomaly to a known tool, or if the SOP mandates human intervention (like an entire Datacenter power loss).
- **Risk Level:** **HIGH**
- **How it works:** Doesn't mutate the config. Generates a readable string passed to the action logs. 
- **Trigger Scenario:** Unrecognized errors, physical hardware failures, LLM parsing failures.
