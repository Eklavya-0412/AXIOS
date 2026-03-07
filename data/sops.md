# Network SOPs & Past Incidents — IndiaNet ISP
# Source of Truth: network_config.json
# All tools modify network_config.json directly.

## SOP-001: High Latency / Congestion on Any Router

**Severity:** P1 — Critical
**Symptoms:** Latency exceeding 200ms, is_congested=true in network_config.json
**Root Cause Pattern:** Interface congestion, upstream provider degradation, traffic surge

### Resolution Steps
1. The FIRST action for congestion is ALWAYS: call `reroute_traffic(source_router="<affected_router>", target_router="Core-Router-Hyderabad")`.
   This changes `current_route` from "Primary-Link-A" to "Backup-Link-B" in network_config.json.
2. Once rerouted, the telemetry generator reads the new route and immediately produces healthy data.
3. If latency persists after rerouting, call `adjust_qos(router="<affected_router>", policy="HIGH_PRIORITY_REROUTE")`.
4. If still unresolved, call `escalate_to_noc()`.

**Tool Mapping:** congestion anomaly → reroute_traffic (LOW RISK)

---

## SOP-002: Interface Flapping / Link Instability

**Severity:** P2 — High
**Symptoms:** interface_flapping=true in network_config.json, packet loss 20-50%
**Root Cause Pattern:** Faulty SFP module, fiber degradation, hardware issue

### Resolution Steps
1. Call `restart_interface(router="<affected_router>", interface="Gi0/1")`.
   This sets `status="rebooting"` in network_config.json, waits 5s, then sets `status="online"` and clears all flags.
2. If flapping continues, call `reroute_traffic()` to move traffic off the bad link.
3. If physical issue suspected, call `escalate_to_noc()`.

**Tool Mapping:** interface_flapping anomaly → restart_interface (LOW RISK)

---

## SOP-003: CPU Spike / High CPU Utilization

**Severity:** P2 — High
**Symptoms:** cpu_spiking=true in network_config.json, CPU > 90%
**Root Cause Pattern:** DDoS attack, routing table explosion, firmware bug

### Resolution Steps
1. Call `restart_interface(router="<affected_router>", interface="Gi0/1")` to clear the CPU spike.
   The restart clears cpu_spiking flag in network_config.json.
2. If caused by DDoS, also call `adjust_qos(router="<affected_router>", policy="EDGE_PROTECT")`.
3. If CPU remains high after restart, call `escalate_to_noc()`.

**Tool Mapping:** cpu_spike anomaly → restart_interface (LOW RISK)

---

## SOP-004: BGP Session Down

**Severity:** P1 — Critical
**Symptoms:** bgp_down=true in network_config.json, packet_loss=100%, BGP flaps > 0
**Root Cause Pattern:** Upstream provider maintenance, route policy change, BGP misconfiguration

### Resolution Steps
1. Call `reset_bgp_session(router="<affected_router>", peer="upstream")`.
   This clears bgp_down flag in network_config.json.
2. If BGP does not re-establish, switch to backup upstream via rerouting.
3. Always notify upstream provider NOC.

**Tool Mapping:** bgp_down anomaly → reset_bgp_session (HIGH RISK — requires human approval)
**CRITICAL:** This is a HIGH RISK action. The agent MUST request human approval before executing.

---

## SOP-005: Packet Loss on Edge Routers (DDoS/ACL)

**Severity:** P2 — High
**Symptoms:** High packet_loss on edge routers (5-15%), no BGP flaps
**Root Cause Pattern:** DDoS attack, buffer overflow, ACL misconfiguration

### Resolution Steps
1. Call `adjust_qos(router="<affected_router>", policy="EDGE_PROTECT")` to throttle traffic.
2. If DDoS suspected, consider escalation.
3. If packet loss drops below 1%, mark resolved.

**Tool Mapping:** packet_loss on edge routers (without BGP down) → adjust_qos (LOW RISK)

---

## Router Routing Information

| Router | Primary Route | Backup Route | Type |
|--------|--------------|--------------|------|
| Core-Router-Mumbai | Primary-Link-A (Mumbai→Delhi) | Backup-Link-B (via Hyderabad) | Core |
| Core-Router-Delhi | Primary-Link-A (Delhi→Mumbai) | Backup-Link-B (via Kolkata) | Core |
| Core-Router-Hyderabad | Primary-Link-A (Hyderabad→Mumbai) | Backup-Link-B (via Chennai) | Core |
| Core-Router-Chennai | Primary-Link-A (Chennai→Hyderabad) | Backup-Link-B (via Hyderabad) | Core |
| Edge-Router-Delhi | Primary-Link-A (Edge→Core-Delhi) | Backup-Link-B (via Core-Mumbai) | Edge |
| Edge-Router-Kolkata | Primary-Link-A (Kolkata→Core-Delhi) | Backup-Link-B (via Core-Mumbai) | Edge |

**Core routers** handle backbone traffic between cities. **Edge routers** connect end users.
When rerouting from a core router, always target a different core router (e.g., Core-Router-Hyderabad).
When rerouting from an edge router, target a core router (e.g., Core-Router-Mumbai).

---

## ANOMALY → TOOL QUICK REFERENCE

| Anomaly Type | Flag in Config | Recommended Tool | Risk Level |
|-------------|---------------|-----------------|------------|
| Congestion (high latency) | is_congested | reroute_traffic | LOW |
| Interface Flapping | interface_flapping | restart_interface | LOW |
| CPU Spike | cpu_spiking | restart_interface | LOW |
| BGP Down | bgp_down | reset_bgp_session | HIGH |
| DDoS / Packet Loss (no BGP) | is_congested | adjust_qos | LOW |

---

## Past Incident: INC-2024-0147 — Mumbai Latency Spike

**Duration:** 45 minutes
**Root Cause:** Memory leak causing gradual latency increase.
**Resolution:** `reroute_traffic("Core-Router-Mumbai", "Core-Router-Hyderabad")` — network_config.json updated: current_route → Backup-Link-B.
**Lesson:** Auto-reroute is safe for latency anomalies. The moment current_route changes, telemetry normalizes.

---

## Past Incident: INC-2024-0203 — Delhi DDoS

**Duration:** 2 hours
**Root Cause:** Volumetric DDoS on Edge-Router-Delhi.
**Resolution:** `adjust_qos("Edge-Router-Delhi", "EDGE_PROTECT")` — is_congested cleared in network_config.json.
**Lesson:** QoS is a LOW-RISK first response for packet loss anomalies on edge routers.

---

## Past Incident: INC-2025-0019 — Hyderabad Power Outage

**Duration:** 3 hours
**Root Cause:** UPS failure.
**Resolution:** Traffic rerouted to Core-Router-Chennai. On-site team restored power.
**Lesson:** Full router outage = HIGH RISK, requires human approval.
