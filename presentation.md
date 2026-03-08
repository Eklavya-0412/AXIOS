# Autonomous Network Operations Agent - Presentation

This document outlines the detailed talking points for your Advanced Track Presentation.

## 1. What the Agent Does
**Core purpose:**
The agent completely automates Level 1 and Level 2 Network Operations Center (NOC) tasks for an ISP. Its primary mission is to minimize network downtime and degradation by instantly detecting anomalies, diagnosing their root causes based on historical SOPs, and executing deterministic configuration changes to restore service before customers even notice an issue.

**Role in the system:**
It serves as the "brain" connecting the observation layer (telemetry and logs) to the control plane (router configurations). By maintaining a continuous loop of Observe → Reason → Decide → Act, it sits directly in the critical path of network reliability, reducing Mean Time to Resolution (MTTR) from hours to seconds.

## 2. How the Agent Thinks
**Decision logic:**
The agent utilizes a LangGraph-based state machine powered by Gemini 2.5 Flash. Its reasoning framework follows a structured cognitive loop:
1. **Understand:** Parses incoming telemetry spikes (e.g., latency > 200ms).
2. **Contextualize:** Queries a local ChromaDB vector database (Retrieval-Augmented Generation) to pull up exact Standard Operating Procedures (SOPs) relevant to the failing router and specific metric.
3. **Decide:** Maps the active anomaly flags (e.g., `is_congested`, `bgp_down`) to a strict deterministic tool matrix to guarantee the exact correct response (e.g., congestion = reroute).

**When and how it acts:**
- **Trigger conditions:** Background tasks constantly calculate Z-scores and static thresholds for latency, packet loss, and CPU utilization. If a threshold breaks, the agent wakes up.
- **Action mechanisms:** It executes direct, atomic file writes to `network_config.json` (our Digital Twin). For low-risk issues (congestion, high CPU), it acts autonomously. For high-risk issues (BGP failures, complete outages), it explicitly pauses execution and awaits human NOC approval via the Streamlit dashboard.

## 3. System Structure
**Key components:**
1. **The Digital Twin (`network_config.json`):** The absolute single source of truth representing the live network state.
2. **The Telemetry Engine (`main.py`):** A FastAPI backend that reads the Digital Twin every tick and generates realistic, noisy network metrics based on the current configuration flags.
3. **The Cognitive Engine (`agent.py`):** The LangGraph agent, tools, and RAG integration that processes anomalies and modifies the Digital Twin.
4. **The NOC Dashboard (`app.py`):** A Streamlit interface providing human operators with live graphs, agent action traces, and approval controls.

**How they work together:**
Data flows in a perfect closed loop: `main.py` generates bad telemetry based on a flag in `network_config.json` → `agent.py` detects it, reasons using ChromaDB, and uses a tool to rewrite `network_config.json` → `main.py` instantly reads the new configuration and generates healthy telemetry.

## 4. Performance & Efficiency
**Speed considerations:**
- The agent eliminates HTTP overhead by having tools write *directly* to the configuration file.
- State-graph processing natively supports rapid iteration. From detection to resolution, the network is healed in roughly 3 to 5 seconds.

**Resource usage:**
- Extremely lightweight. The backend runs on a single FastAPI instance without heavy ORMs.
- Telemetry history is bounded by efficient collections (`collections.deque` with `maxlen=500`), guaranteeing a constant memory footprint O(1) regardless of uptime.
- RAG relies on a lightweight local ChromaDB instance, keeping vector searches instantaneous.

## 5. Built to Work in Reality
**Integration points:**
- Designed to easily scale beyond a PoC. The direct file writes to `network_config.json` mock what would be SSH/NETCONF calls or API pushes to real Cisco/Juniper controllers or an SDN orchestrator like Cisco NSO.

**Operational feasibility:**
- **Safety First:** The system enforces strict Risk Levels. The agent can only fully automate "Low Risk" tasks that cannot physically break the network (like a temporary traffic shift or edge QoS adjustment). Any "High Risk" manipulation (BGP resets) enters a Human-in-the-Loop holding pattern.
- Thread-safe file locks guarantee that concurrent anomaly triggers and agent interactions do not corrupt the configuration file.

## 6. Learning & Improvement
**Feedback signals:**
The agent immediately knows if its action succeeded because the telemetry stream instantly reflects the updated config file state. It logs exactly what tool was called and the arguments used.

**How it gets better over time:**
By logging all resolved incidents, failures, and manual human overrides into `live_network_logs.jsonl` and the agent logs, administrators can generate new markdown SOPs, ingest them back into ChromaDB using `setup_db.py`, and the agent will automatically handle the new edge-case identically the next time it occurs—achieving a "Learn" phase.

## 7. Advanced Intelligence
**ML usage:**
- **Generative AI (Gemini 2.5 Flash):** Translates unstructured network states and natural language SOPs into concrete, executable function calls via LLM Tool Binding.
- **Vector Embeddings (models/gemini-embedding-001):** Transforms textual SOPs and historical incident data into high-dimensional vectors for semantic retrieval, meaning the agent doesn't need exact keyword matches to know how to fix an issue.
- **Statistical Anomaly Detection:** Uses live Z-score calculation on latency histories to detect standard deviation drifts rather than relying purely on static, hardcoded thresholds.

**Why it adds value:**
Traditional rule-based systems (like a standard Bash or Python script) snap and fail when a log looks slightly different or an error code changes. By using an LLM equipped with RAG, the system is globally resilient—it can read and comprehend *intent* from the NOC's documentation and adapt to novel variations of network decay automatically.
