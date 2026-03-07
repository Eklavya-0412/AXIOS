# Network SOPs & Past Incidents — IndiaNet ISP

## SOP-001: High Latency on Core-Router-Mumbai

**Severity:** P1 — Critical  
**Affected Components:** Core-Router-Mumbai, Mumbai-Delhi-Link-1  
**Symptoms:** Latency exceeding 200ms on Core-Router-Mumbai, packet loss > 2%  
**Root Cause Pattern:** Interface congestion or upstream provider degradation  

### Resolution Steps
1. Check interface utilization on Core-Router-Mumbai GigabitEthernet0/1.
2. If utilization > 85%, apply QoS policy `HIGH_PRIORITY_REROUTE`.
3. Reroute traffic from Mumbai-Delhi-Link-1 to Mumbai-Delhi-Link-2 (backup path via Core-Router-Hyderabad).
4. Monitor for 10 minutes. If latency normalizes, mark resolved.
5. If latency persists, escalate to NOC Tier 2.

---

## SOP-002: Link Flapping on Mumbai-Delhi-Link-1

**Severity:** P2 — High  
**Affected Components:** Mumbai-Delhi-Link-1, Core-Router-Mumbai, Core-Router-Delhi  
**Symptoms:** Link status oscillating between UP and DOWN every 30-60 seconds  
**Root Cause Pattern:** Faulty SFP module or fiber degradation  

### Resolution Steps
1. Restart interface on both ends: Core-Router-Mumbai Gi0/1 and Core-Router-Delhi Gi0/2.
2. If flapping continues after restart, reroute all traffic to Mumbai-Delhi-Link-2.
3. Create a maintenance ticket for physical layer inspection.
4. Escalate to NOC with fiber team dispatch request.

---

## SOP-003: Packet Loss on Edge-Router-Delhi

**Severity:** P2 — High  
**Affected Components:** Edge-Router-Delhi, Delhi-Kolkata-Link-1  
**Symptoms:** Packet loss > 5% on Edge-Router-Delhi, user complaints from Delhi metro  
**Root Cause Pattern:** Buffer overflow due to DDoS or misconfigured ACL  

### Resolution Steps
1. Check CPU and memory utilization on Edge-Router-Delhi.
2. Apply rate-limiting QoS policy `EDGE_PROTECT` to throttle excessive traffic.
3. If DDoS suspected, enable blackhole routing for offending source IPs.
4. If packet loss drops below 1%, mark as mitigated.
5. Escalate to security team if attack pattern persists.

---

## SOP-004: Core-Router-Hyderabad Unreachable

**Severity:** P1 — Critical  
**Affected Components:** Core-Router-Hyderabad, Mumbai-Hyderabad-Link-1, Hyderabad-Chennai-Link-1  
**Symptoms:** Complete loss of connectivity to Core-Router-Hyderabad, SNMP timeouts  
**Root Cause Pattern:** Power failure or OS crash on router  

### Resolution Steps
1. Attempt remote power cycle via IPMI/iLO console.
2. Immediately reroute all south-bound traffic via Core-Router-Chennai (backup path).
3. Dispatch on-site engineer to Hyderabad data center.
4. Escalate to NOC Tier 3 — this is a critical infrastructure failure.

---

## SOP-005: QoS Policy Degradation — VoIP Traffic

**Severity:** P2 — High  
**Affected Components:** All core routers, specifically Core-Router-Mumbai, Core-Router-Delhi  
**Symptoms:** VoIP call quality degradation, jitter > 30ms  
**Root Cause Pattern:** QoS policy misconfiguration after maintenance window  

### Resolution Steps
1. Verify current QoS policies on Core-Router-Mumbai and Core-Router-Delhi.
2. Apply `VOIP_PRIORITY` policy to prioritize RTP traffic.
3. Adjust DSCP markings to ensure EF (Expedited Forwarding) for VoIP.
4. Monitor jitter and MOS scores for 15 minutes.

---

## SOP-006: BGP Session Down with Upstream Provider

**Severity:** P1 — Critical  
**Affected Components:** Core-Router-Mumbai, Upstream-ISP-Tata  
**Symptoms:** BGP session flap, loss of default route, internet unreachable for Mumbai region  
**Root Cause Pattern:** Upstream provider maintenance or route policy change  

### Resolution Steps
1. Check BGP neighbor status on Core-Router-Mumbai.
2. If session is down, attempt `clear ip bgp * soft` to re-establish.
3. If BGP does not re-establish within 5 minutes, switch to backup upstream via Core-Router-Delhi.
4. Notify upstream provider NOC and log incident.

---

## Past Incident: INC-2024-0147 — Mumbai Latency Spike (2024-11-15)

**Duration:** 45 minutes  
**Affected:** Core-Router-Mumbai, 12,000 subscribers  
**Root Cause:** Memory leak in router firmware causing gradual latency increase.  
**Detection:** Z-score anomaly detection flagged latency at 340ms (normal baseline: 18ms).  
**Resolution:** Traffic rerouted to Core-Router-Hyderabad via `reroute_traffic("Core-Router-Mumbai", "Core-Router-Hyderabad")`. Firmware patched in next maintenance window.  
**Lesson Learned:** Proactive firmware monitoring SOP added. Auto-reroute is safe for latency-only anomalies with no packet loss.

---

## Past Incident: INC-2024-0203 — Delhi DDoS Attack (2024-12-02)

**Duration:** 2 hours  
**Affected:** Edge-Router-Delhi, 8,500 subscribers  
**Root Cause:** Volumetric DDoS attack targeting DNS infrastructure.  
**Detection:** Packet loss spiked to 15% on Edge-Router-Delhi.  
**Resolution:** Rate-limiting applied via `adjust_qos("Edge-Router-Delhi", "EDGE_PROTECT")`. Attack traffic blackholed. ISP upstream notified for scrubbing.  
**Lesson Learned:** QoS adjustment is a LOW-RISK first response for packet loss anomalies. Escalation required if attack sustains > 30 minutes.

---

## Past Incident: INC-2025-0019 — Hyderabad Power Outage (2025-01-10)

**Duration:** 3 hours  
**Affected:** Core-Router-Hyderabad, all south-bound traffic  
**Root Cause:** Data center UPS failure during grid power cut.  
**Detection:** SNMP timeout and complete packet loss to Core-Router-Hyderabad.  
**Resolution:** Traffic rerouted to Core-Router-Chennai. On-site team restored power from backup generator.  
**Lesson Learned:** Complete router unreachability should trigger HIGH-RISK alert requiring human approval before major rerouting. Auto-reroute approved only for single-link failures, not full router outages.
