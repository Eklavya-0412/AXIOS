# NetOps Autonomous Agent — Architecture & Design Patterns

## Executive Summary

The NetOps Autonomous Agent is a **closed-loop, autonomous network operations platform** built on LangGraph that detects network anomalies, reasons about root causes under partial observability, and automatically resolves issues with explicit human-in-the-loop checkpoints for high-risk decisions.

**Core Design Principle:** *Autonomous where safe; human-controlled where risky.*

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER                              │
├────────────────────────────────────────────────────────────────┤
│  Dashboard.py (Streamlit NOC Dashboard)                        │
│  ├─ Live Topology Map (network graph visualization)            │
│  ├─ Metric Cards (latency, packet loss, CPU, BGP flaps)       │
│  ├─ Router Config Sidebar (network_config.json state)         │
│  ├─ Telemetry Time-Series Chart (Plotly)                      │
│  ├─ Human-in-the-Loop Approval Panel (high-risk actions)      │
│  └─ Agent Action Log (color-coded trace)                      │
└─────────────────────┬──────────────────────────────────────────┘
                      │ HTTP REST APIs
┌─────────────────────▼──────────────────────────────────────────┐
│              BACKEND ORCHESTRATION LAYER                        │
├────────────────────────────────────────────────────────────────┤
│  main.py (FastAPI Backend)                                     │
│  ├─ Telemetry Generation (background task, 2s interval)        │
│  ├─ ML Anomaly Detection (Random Forest classifier)            │
│  ├─ Digital Twin State Management (network_config.json)        │
│  ├─ Control Plane (tool execution, rollback, verification)     │
│  ├─ Human-in-the-Loop Queue (pending approvals)               │
│  └─ Stress Testing & Chaos Engineering                        │
└─────────────────────┬──────────────────────────────────────────┘
                      │ Calls start_agent() with symptom payload
┌─────────────────────▼──────────────────────────────────────────┐
│           AUTONOMOUS REASONING LAYER (LangGraph)               │
├────────────────────────────────────────────────────────────────┤
│  agent.py (Stateful Agent Graph)                               │
│  ├─ observe: Log symptom alert (partial observability)         │
│  ├─ retrieve: Query ChromaDB for relevant SOPs (RAG)          │
│  ├─ investigate: Run diagnostics & blast radius (mandatory)    │
│  ├─ reason_and_decide: LLM selects tool via Gemini            │
│  ├─ human_approval: [INTERRUPT] for high-risk tools            │
│  ├─ act: Execute mitigation tool (writes to config)           │
│  ├─ verify: Health check; auto-rollback if failed             │
│  └─ learn: Post-mortem to ChromaDB + incident_history.md      │
└─────────────────────┬──────────────────────────────────────────┘
                      │ Reads/Writes
┌─────────────────────▼──────────────────────────────────────────┐
│          DIGITAL TWIN & DATA LAYER                              │
├────────────────────────────────────────────────────────────────┤
│  network_config.json (Single Source of Truth)                  │
│  ├─ 6 routers with status, route, anomaly flags               │
│  └─ Direct read/write; no HTTP middleman                        │
│                                                                │
│  data/topology.json (Network Graph)                           │
│  ├─ 6 routers (core + edge), 10 links (primary + backup)      │
│  └─ Used by blast_radius calculation                          │
│                                                                │
│  chroma_db/ (Vector Store)                                    │
│  ├─ SOPs and incident reports (RAG knowledge base)            │
│  └─ Populated by setup_db.py (one-time)                       │
│                                                                │
│  logs/audit_trail.jsonl (Immutable Audit Log)                │
│  └─ All actions, decisions, outcomes with timestamps          │
│                                                                │
│  models/telecom_anomaly_model.pkl (ML Classifier)             │
│  └─ Random Forest; trained on historical telemetry            │
│                                                                │
│  data/incident_history.md (Post-Mortems)                      │
│  └─ Auto-generated after each successful resolution           │
└────────────────────────────────────────────────────────────────┘
```

---

## Design Patterns

### 1. **Partial Observability Pattern**

**Problem:** Real networks lack complete observability. The agent shouldn't assume root-cause knowledge.

**Solution:**
- Agent receives **symptom-only payload** at alert time: `{router, metric, value, threshold, timestamp}`
- No root-cause flags (`is_congested`, `bgp_down`, etc.) included
- Agent is blind to the actual problem and must investigate

**Implementation:**
```python
# Symptom-only payload (agent is blind)
anomaly_payload = {
    "router": "Core-Router-Mumbai",
    "metric": "latency",
    "value": 350.5,
    "threshold": 100,
    "timestamp": "2026-03-08T14:35:22 IST"
}

# Agent calls investigate node to discover root cause
diagnostics = run_device_diagnostics("Core-Router-Mumbai")
# Returns: {"is_congested": true, "bgp_down": false, "cpu_spiking": false, ...}
```

**Benefits:**
- Enforces active diagnosis before action
- Prevents blind assumptions
- Mirrors real NOC workflows
- Trains agent to be thorough

---

### 2. **Blast Radius Assessment Pattern**

**Problem:** Before changing network state, the agent must understand downstream impact.

**Solution:**
- `calculate_blast_radius(router_name)` reads `data/topology.json`
- Counts connected downstream nodes and links
- Classifies impact: CRITICAL (>20) / HIGH (11-20) / MODERATE (6-10) / LOW (1-5)
- Routes decisions based on impact level

**Implementation:**
```python
blast_radius = calculate_blast_radius("Core-Router-Mumbai")
# Returns: {"impact": "HIGH", "affected_nodes": 15, "affected_links": 8}

# LLM reasoning must reference blast radius
if blast_radius["impact"] == "CRITICAL":
    # Escalate to NOC
elif blast_radius["impact"] == "HIGH" and tool == "reset_bgp_session":
    # Require human approval (interrupt)
else:
    # Auto-execute low-risk tool
```

**Benefits:**
- Topology-aware decisions
- Prevents cascading failures
- Explicit impact justification
- Competitive differentiator

---

### 3. **Digital Twin (Config-as-State) Pattern**

**Problem:** Reading real network state requires vendor APIs; writing state requires CLI/SSH access.

**Solution:**
- `network_config.json` is the single source of truth
- Agent tools write directly to it (no HTTP middleman)
- Telemetry engine reads it live to generate realistic metrics
- Dashboard reads it for UI state

**Benefits:**
- Decoupled from real network APIs
- Deterministic state transitions
- Simpler testing and debugging
- Fast iteration for demo/eval

**Constraints:**
- Single file; requires threading locks
- All tools must respect lock protocol
- Backup/rollback are JSON restore operations

---

### 4. **Human-in-the-Loop with LangGraph Interrupts**

**Problem:** High-risk actions need human approval before execution, but synchronous approval isn't practical.

**Solution:**
- LangGraph `interrupt_before` on high-risk tool choices
- Pipeline pauses; action queued in `PENDING_APPROVALS`
- NOC approves via dashboard `/api/approve` endpoint
- `resume_agent(thread_id)` continues pipeline from interrupt point

**Implementation:**
```python
@app.post("/api/approve")
def approve_action(req: ApprovalAction):
    result = resume_agent(req.thread_id)  # Continue from interrupt
    PENDING_APPROVALS.pop(req.thread_id)
    return result
```

**Benefits:**
- True async approval (no blocking)
- Full audit trail of approval decisions
- Scales to multiple high-risk actions in parallel
- Prevents runaway autonomous actions

---

### 5. **RAG-Powered Reasoning Pattern**

**Problem:** LLM should reason with domain knowledge (SOPs, past incidents).

**Solution:**
- `setup_db.py` ingests `data/sops.md` into ChromaDB
- `retrieve` node queries ChromaDB for relevant SOPs
- Retrieval results sent to LLM in reasoning context

**Implementation:**
```python
# In retrieve node
relevant_sops = retriever.get_relevant_documents(anomaly)
# Returns top-3 SOPs matching the anomaly

# LLM context
f"Relevant SOPs:\n{relevant_sops}\n\nChoose a mitigation tool that aligns with these procedures."
```

**Benefits:**
- Knowledge-grounded decisions
- Faster resolution (SOP shortcut)
- Audit trail: which SOP informed the decision
- Scalable knowledge base

---

### 6. **Verification & Auto-Rollback Pattern**

**Problem:** Actions may fail or make things worse; need automatic recovery.

**Solution:**
- `verify` node calls `/api/config/verify_health` after action
- Success criteria: `is_healthy=true`, no flags, status="online"
- On failure: auto-rollback to backed-up config
- Escalate to NOC if rollback triggered

**Implementation:**
```python
# After act node
health = verify_health(router)
if not health["is_healthy"]:
    # Auto-rollback
    rollback_config()
    # Log to audit trail
    # Escalate to NOC
else:
    # Continue to learn node
```

**Benefits:**
- Automatic recovery from mistakes
- Bounded blast radius (action undone within seconds)
- Audit trail: rollback reason + timestamp
- Trust in autonomous actions

---

## LangGraph Node Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│           CLOSED-LOOP PIPELINE (with Partial Observability)  │
└─────────────────────────────────────────────────────────────┘

       OBSERVE
         │
         ▼
    ┌─────────────────────────┐
    │ Receive symptom alert   │
    │ (blind to root cause)   │
    │ Log: timestamp, metric  │
    └────────────┬────────────┘
                 │
       RETRIEVE (RAG)
         │
         ▼
    ┌─────────────────────────┐
    │ Query ChromaDB for SOPs │
    │ Top-3 matching docs     │
    └────────────┬────────────┘
                 │
       INVESTIGATE (Mandatory)
         │
         ▼
    ┌─────────────────────────────────────────┐
    │ 1. run_device_diagnostics               │
    │    → discover root-cause flags          │
    │ 2. calculate_blast_radius               │
    │    → assess downstream impact           │
    │ (Agent now "sees" the problem)          │
    └────────────┬────────────────────────────┘
                 │
       REASON & DECIDE
         │
         ▼
    ┌──────────────────────────────────────────────┐
    │ LLM receives:                                │
    │ - Symptom + diagnostics + blast_radius     │
    │ - Relevant SOPs                             │
    │ - Safety constraints                        │
    │ Output: Selected tool + justification      │
    └────────────┬─────────────────────────────────┘
                 │
                 │ (Branch based on risk)
         ┌───────┴───────┐
         │               │
    LOW-RISK         HIGH-RISK
         │               │
         │               ▼
         │           HUMAN APPROVAL [INTERRUPT]
         │               │
         │               │ (NOC reviews via dashboard)
         │               │
         │         APPROVE / REJECT
         │        /              \
         │       ▼                ▼
         │   (resume)           (logged as rejected)
         │       │                │
         └───────┴────────────────┘
                 │
            ACT (Execute Tool)
         │
         ▼
    ┌─────────────────────────┐
    │ Execute mitigation tool │
    │ Write to config file    │
    │ (digital twin updated)  │
    └────────────┬────────────┘
                 │
            VERIFY
         │
         ▼
    ┌──────────────────────────────────┐
    │ Health check on affected router  │
    │ is_healthy? flags cleared?       │
    └────────────┬─────────────────────┘
                 │
         ┌───────┴──────┐
         │              │
       SUCCESS       FAILURE
         │              │
         │              ▼
         │          ROLLBACK
         │          (restore config)
         │              │
         ▼              ▼
      LEARN      ESCALATE TO NOC
         │              │
         ▼              ▼
    ┌────────────────────────────────┐
    │ Write post-mortem to           │
    │ data/incident_history.md       │
    │ Embed into ChromaDB            │
    │ Log to logs/audit_trail.jsonl  │
    └────────────────────────────────┘
         │
         ▼
      [END]
```

---

## Autonomous Decision Boundaries

### Tools Classified by Risk

| Risk Level | Tools | Auto-Execute? | Approval Required? | Blast Radius Limit |
|---|---|---|---|---|
| **LOW** | reroute_traffic, restart_interface, adjust_qos | ✅ Yes | ❌ No | ≤ 10 nodes |
| **HIGH** | reset_bgp_session, escalate_to_noc | ❌ No | ✅ Yes | ≤ 20 nodes |
| **FORBIDDEN** | hard_reboot, delete_routes, modify_firewall | ❌ Never | N/A | N/A |

### Decision Tree

```
anomaly detected
    │
    ├─ run_device_diagnostics() → discover root cause
    ├─ calculate_blast_radius() → assess impact
    │
    ├─ blast_radius > 20 nodes?
    │  ├─ YES → escalate_to_noc() [REQUIRED]
    │  └─ NO → continue
    │
    ├─ tool is HIGH-risk (BGP reset)?
    │  ├─ YES → halt for human_approval [INTERRUPT]
    │  └─ NO → continue to act
    │
    ├─ tool is FORBIDDEN?
    │  ├─ YES → escalate_to_noc() (should never happen)
    │  └─ NO → execute tool
    │
    └─ verify health
        ├─ is_healthy=true → learn & end
        └─ is_healthy=false → rollback → escalate → end
```

---

## Data Flow & Timing

### Anomaly-to-Resolution Timeline

| Step | Component | Duration | Output |
|---|---|---|---|
| 1. Generate Telemetry | main.py (background) | 2s | 1 data point per 2s |
| 2. ML Detection | main.py (inline) | <100ms | anomaly score |
| 3. Trigger Agent | main.py → agent.py | 10ms | start_agent() called |
| 4. Observe | agent.py | <100ms | symptom logged |
| 5. Retrieve | agent.py (ChromaDB) | 500ms | top-3 SOPs |
| 6. Investigate | agent.py (tools) | 1s | diagnostics + blast_radius |
| 7. Reason & Decide | agent.py (LLM via Gemini) | 2-3s | tool selection |
| [8] Human Approval | Dashboard | variable | NOC decision |
| 9. Act | agent.py (tool execution) | 100-500ms | config updated |
| 10. Verify | main.py (/verify endpoint) | 1s | health check result |
| 11. Learn | agent.py | 500ms | post-mortem written |
| **Total** | **end-to-end** | **~8-12 seconds** (+ approval time if high-risk) | **anomaly resolved** |

**Key Insight:** Low-risk actions resolve in <10 seconds autonomously. High-risk actions pause for NOC.

---

## Audit Trail & Compliance

Every action generates an immutable audit log entry:

```json
{
  "action_id": "abc123xy",
  "timestamp": "2026-03-08T14:35:22 IST",
  "anomaly_trigger": {
    "router": "Core-Router-Mumbai",
    "metric": "latency",
    "value": 350.5,
    "threshold": 100
  },
  "diagnostic_results": {
    "is_congested": true,
    "bgp_down": false,
    "cpu_spiking": false,
    "interface_flapping": false
  },
  "blast_radius": {
    "impact": "HIGH",
    "affected_nodes": 15,
    "affected_links": 8
  },
  "decision_rationale": "Congestion detected on Core-Mumbai; rerouting to backup link (LOW-risk) for 15 downstream nodes (within HIGH-risk threshold of 20).",
  "action_executed": {
    "tool": "reroute_traffic",
    "parameters": {
      "source": "Core-Router-Mumbai",
      "target": "Backup-Link-B"
    }
  },
  "verification_result": {
    "is_healthy": true,
    "flags": [],
    "status": "online"
  },
  "outcome": "success",
  "logs": [
    "[OBSERVE] Latency spike on Core-Router-Mumbai",
    "[RETRIEVE] Found SOP-001 (high latency response)",
    "[INVESTIGATE] Congestion on Primary-Link-A",
    "[REASON] Blast radius=15 nodes; safe to reroute",
    "[ACT] Switched traffic to Backup-Link-B",
    "[VERIFY] Health check passed; anomaly cleared",
    "[LEARN] Post-mortem saved to incident_history.md"
  ]
}
```

**File:** `logs/audit_trail.jsonl` (append-only)
**Compliance:** Immutable; 90-day retention; archive after 1 year

---

## Extensibility & Future Enhancements

### Bonus Point Opportunities

1. **ML Model Enhancement**
   - Train on telecom-specific anomaly patterns
   - Multi-class classification (congestion vs. BGP vs. CPU vs. flapping)
   - Anomaly score confidence (0-100% instead of binary)

2. **Predictive Failover**
   - Detect trending metrics (latency increasing over 1 min)
   - Proactively reroute before critical threshold
   - "Prevent" anomaly rather than "resolve" it

3. **Multi-Step Reasoning**
   - Complex scenarios: congestion + BGP down simultaneously
   - Sequenced tool execution: fix BGP, then reroute
   - Dependency graph of tools

4. **Topology-Aware Recovery**
   - Prefer backup routes matching remaining bandwidth
   - Load balancing across multiple backup paths
   - Predict future link failures

5. **Custom SOP Development**
   - Agent learns new SOPs from successful resolutions
   - Community-contributed SOP library
   - Version control + rollback of SOP changes

---

## Deployment Considerations

### Safety Checklist

- [ ] All tools locked behind blast radius limits
- [ ] High-risk tools require explicit NOC approval
- [ ] Verification + auto-rollback on failure
- [ ] Audit trail immutable and retained for 90 days
- [ ] Cooldown per router prevents alert spam
- [ ] Partial observability enforced (symptom-only payload)
- [ ] Dashboard shows all pending approvals
- [ ] LLM constraints prompt prevents forbidden tools

### Monitoring & Alerting

- Track resolution time by anomaly type
- Alert if high-risk decisions escalate frequently
- Monitor rollback frequency (indicates instability)
- Track NOC approval decision time
- Detect agent loop cycles (same router repeatedly failing)

### Incident Response

1. **Agent Stuck:** Check LangGraph threads; resume manually via `/api/approve`
2. **Config Corruption:** Restore from backup via `/api/config/rollback`
3. **Telemetry Spike:** Review logs/audit_trail.jsonl for decision chain
4. **ML Model Failure:** Falls back to Z-score anomaly detection automatically

---

## Glossary

| Term | Definition |
|---|---|
| **Partial Observability** | Agent initially blind to root cause; must investigate |
| **Blast Radius** | Count of routers/links affected by an action |
| **Digital Twin** | network_config.json as system state single source of truth |
| **Interrupt** | LangGraph pause point for human decision |
| **Verification** | Health check confirming action success |
| **Rollback** | Automatic restoration of previous config on failure |
| **Audit Trail** | Immutable log of all actions and decisions |
| **RAG** | Retrieval-Augmented Generation (SOPs from ChromaDB) |
| **Auto-Rollback** | Automatic config restoration triggered by failed verification |

