# Safety Constraints & Autonomous Decision Boundaries

## Overview

This document formalizes the safety policies and decision boundaries for the NetOps Autonomous Agent. The agent operates under **partial observability** with explicit human-in-the-loop checkpoints for high-risk actions.

---

## Safety Policy Levels

### 1. **LOW-RISK (Auto-Execute)**
Actions automatically executed by the agent without human approval required.

| Action | Tool | Constraints | Rollback Strategy |
|---|---|---|---|
| Reroute Traffic | `reroute_traffic()` | Max 2 backup routes; max 2 consecutive reroutes per 5 min | Revert to primary route |
| Restart Interface | `restart_interface()` | Only if not already rebooting; skip core->core links | Full config rollback |
| Adjust QoS | `adjust_qos()` | Policy ID from predefined set; max 10 min duration | Reset to default policy |

**Blast Radius Limit:** ≤ 10 downstream nodes
**Recovery Time SLA:** ≤ 5 minutes
**Auto-Rollback Trigger:** Verification health check fails after 2 minutes

---

### 2. **HIGH-RISK (Human-in-the-Loop)**
Actions that halt the LangGraph pipeline and require explicit NOC approval.

| Action | Tool | Why High-Risk | Approval Criteria |
|---|---|---|---|
| BGP Reset | `reset_bgp_session()` | Can cause widespread routing chaos; affects all downstream peers | Confirmation of blast radius < 20 nodes |
| NOC Escalation | `escalate_to_noc()` | Requires manual intervention; may be unresolvable | N/A (info-only) |

**Blast Radius Limit:** ≤ 20 downstream nodes
**Approval Timeout:** 5 minutes (auto-reject if no decision)
**Audit Trail:** All approvals/rejections logged with NOC operator ID and timestamp

---

### 3. **Forbidden (Never Execute)**
Actions the agent is not permitted to perform under any circumstances.

| Forbidden Action | Reason |
|---|---|
| Hard reboot router (status = offline) | Too destructive; requires explicit manual intervention |
| Delete routes from topology | Could isolate network segments permanently |
| Modify firewall rules | Outside scope; requires security team approval |
| Change BGP AS number | Violates inter-AS routing contracts |
| Inject traffic / DDoS simulation | Reserved for authorized testing only |

---

## Partial Observability Constraints

### Constraint 1: Initial Blindness
**The agent receives ONLY the anomaly symptom at alert time.**

Example symptom-only payload:
```json
{
  "router": "Core-Router-Mumbai",
  "metric": "latency",
  "value": 350.5,
  "threshold": 100,
  "timestamp": "2026-03-08T14:35:22 IST"
}
```

**Root cause flags NOT included.** The agent is blind to `is_congested`, `bgp_down`, `cpu_spiking`, `interface_flapping`.

### Constraint 2: Mandatory Investigation
**Before reasoning and deciding, the agent MUST call:**

1. `run_device_diagnostics(router_name)` → discover root cause flags
2. `calculate_blast_radius(router_name)` → assess downstream impact

**Code Enforcement:** LangGraph node `investigate` is deterministic and always executes before `reason_and_decide`.

### Constraint 3: Observability Window
**The agent must complete diagnosis within a 10-second window:**

- Observe (0s) → Retrieve SOPs (1s) → Investigate (2s) → Reason (3s) → Act (5s) → Verify (10s)
- If diagnosis takes > 5 seconds, escalate to NOC instead of auto-acting

---

## Blast Radius Classification

The agent must assess downstream impact before acting.

```
IMPACT LEVEL    NODES AFFECTED    DECISION
──────────────────────────────────────────────
CRITICAL        > 20 nodes        Escalate to NOC
HIGH            11–20 nodes       Requires NOC approval (if BGP reset)
MODERATE        6–10 nodes        Auto-execute LOW-risk actions only
LOW             1–5 nodes         Auto-execute any eligible action
```

**Topology Dependency:** `calculate_blast_radius` reads `data/topology.json`.
**Connectivity Rules:**
- Core→Core link failure = HIGH impact (affects ≥10 nodes)
- Edge→Core link failure = MODERATE impact (affects 1–5 nodes)
- Edge→Edge link failure = LOW impact (affects 1–2 nodes)

---

## Audit Trail Requirements

Every action must be logged with:

1. **Action ID** (UUID)
2. **Timestamp** (Asia/Kolkata timezone)
3. **Anomaly Trigger** (symptom payload)
4. **Diagnostic Results** (root cause flags, blast radius)
5. **Decision Rationale** (LLM reasoning excerpt)
6. **Action Executed** (tool name, parameters)
7. **Verification Result** (post-action health check)
8. **Outcome** (success / rollback / escalation)

**Log Location:** `logs/audit_trail.jsonl` (append-only)
**Retention Policy:** Minimum 90 days; archive after 1 year
**Access Control:** Read-only for audit team; no deletion

---

## Verification & Rollback Contracts

### Verification Health Check
After any action, the agent calls `/api/config/verify_health?router_name=X`.

```json
{
  "is_healthy": bool,
  "flags": ["anomaly_flag_1", "anomaly_flag_2"],
  "status": "online" | "offline" | "rebooting"
}
```

**Success Criteria:**
- `is_healthy == true`
- No anomaly flags active
- Status = "online"

**Failure Triggers Rollback:**
- Restore backed-up `network_config.json`
- Escalate to NOC with incident summary
- Log: "Auto-rollback triggered: verification failed"

### Rollback Status API
Endpoint: `/api/action/{action_id}/rollback-status`

Returns:
```json
{
  "action_id": "abc123",
  "action": "reroute_traffic",
  "original_state": {...},
  "rollback_state": {...},
  "rollback_timestamp": "2026-03-08T14:40:15 IST",
  "status": "rolled_back" | "verified_success" | "pending_manual_review"
}
```

---

## Training & Constraints Enforcement

### LLM Constraints Prompt

When calling Gemini, the agent includes:

```
You are an autonomous network operations agent operating under SAFETY CONSTRAINTS:

1. AUTO-EXECUTE (no approval needed):
   - reroute_traffic, restart_interface, adjust_qos
   - Blast radius must be ≤ 10 nodes

2. REQUIRE APPROVAL:
   - reset_bgp_session, escalate_to_noc
   - Blast radius must be ≤ 20 nodes

3. FORBIDDEN:
   - Hard reboot, delete routes, modify firewall, change BGP AS

4. ALWAYS investigate before deciding:
   - Call run_device_diagnostics() + calculate_blast_radius()
   - Verify the fix worked via health check
   - Rollback if verification fails

Your reasoning must reference the blast radius and justify why it's safe to act.
```

### Code Enforcement Points

**In `agent.py`:**
- `investigate` node runs deterministically before `reason_and_decide`
- `reason_and_decide` node removes forbidden tool choices from LLM output
- `act` node checks blast radius before executing HIGH-risk tools
- `verify` node enforces rollback on health check failure

**In `main.py`:**
- `/api/approve` validates `thread_id` exists in `PENDING_APPROVALS`
- `/api/pending-approvals` shows only HIGH-risk actions awaiting approval
- Background task enforces 25-second cooldown per router
- ML anomaly detection falls back to Z-score if model unavailable

---

## Incident Response & Escalation

### When to Escalate

Escalate to NOC via `escalate_to_noc()` in these scenarios:

1. **Unknown Root Cause** → Diagnostics return no anomaly flags; metric spike unexplained
2. **Blast Radius Too High** → Action would affect > 20 nodes
3. **Conflicting Anomalies** → Multiple flags active simultaneously (e.g., BGP down + CPU spike)
4. **Repeated Failures** → Same router failed 3+ times in 1 hour
5. **Verification Failed** → Health check failed; auto-rollback triggered

**Escalation Payload:**
```json
{
  "severity": "critical" | "high" | "medium",
  "router": "Core-Router-Mumbai",
  "anomaly": {...},
  "diagnostics": {...},
  "blast_radius": {"impact": "HIGH", "affected_nodes": 15},
  "recommended_next_steps": ["Manual BGP inspection", "Traffic engineering review"]
}
```

---

## Testing & Validation

### Unit Test Coverage

- `test_partial_observability.py` — Verify symptom-only payload enforcement
- `test_blast_radius.py` — Validate impact calculations across topology
- `test_auto_rollback.py` — Verify rollback on health check failure
- `test_approval_timeout.py` — Verify 5-min auto-reject of unapproved HIGH-risk actions
- `test_forbidden_tools.py` — Verify agent never calls forbidden tools

### Simulation Scenarios

1. **Congestion Scenario** → Low-risk reroute succeeds
2. **BGP Down Scenario** → High-risk reset halts pipeline awaiting approval
3. **CPU Spike Scenario** → Low-risk restart interface succeeds
4. **Cascade Failure** → Multiple anomalies trigger escalation
5. **Verification Failure** → Rollback triggered automatically

---

## Change Management

**Any safety constraint changes require:**

1. Update this document
2. Update `data/safety_policy.json` with new risk levels
3. Update LLM constraints prompt in `agent.py`
4. Add unit test coverage
5. SVN commit with tag `safety-update-vX.X`
6. NOC team approval before deployment

---

## Definitions

| Term | Definition |
|---|---|
| **Partial Observability** | Agent initially blind to root cause; must investigate actively |
| **Blast Radius** | Count of downstream routers/links affected by an action |
| **Low-Risk Action** | Auto-executable; blast radius ≤ 10 nodes; auto-rollback enabled |
| **High-Risk Action** | Requires NOC approval; blast radius ≤ 20 nodes; manual decision needed |
| **Verification** | Health check confirming anomaly flags cleared and status = online |
| **Rollback** | Restore previous `network_config.json` if verification fails |
| **Audit Trail** | Immutable log of all actions, decisions, and outcomes |
| **SLA** | Service level agreement for resolution time and availability |

