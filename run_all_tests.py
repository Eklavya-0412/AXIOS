import requests
import time
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def print_status(msg, success):
    prefix = "[PASS]" if success else "[FAIL]"
    print(f"{prefix} {msg}")

def test_endpoint(endpoint, method="GET", payload=None, expected_status=200):
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            res = requests.get(url)
        else:
            res = requests.post(url, json=payload)
            
        success = res.status_code == expected_status
        try:
            data = res.json()
        except:
            data = res.text
            
        return success, data
    except Exception as e:
        print(f"Error on {endpoint}: {e}")
        return False, None

def run_tests():
    print("="*50)
    print("Starting Axios Agentic AI - Integration Test Suite")
    print("="*50)
    
    # 1. System Health & Config
    print("\n--- 1. System Health & Config ---")
    s_conf, d_conf = test_endpoint("/network-config")
    print_status("Fetch /network-config returns 200 OK and valid JSON", s_conf and isinstance(d_conf, dict))
    
    s_top, d_top = test_endpoint("/topology")
    print_status("Fetch /topology returns 200 OK and valid JSON", s_top and isinstance(d_top, dict))
    
    s_tel, d_tel = test_endpoint("/api/telemetry")
    print_status("Fetch /api/telemetry returns 200 OK and valid JSON", s_tel and (isinstance(d_tel, list) or isinstance(d_tel, dict)))


    # 2. Guardrails & State Mocks
    print("\n--- 2. Guardrails & State Mocks ---")
    s_bkp, d_bkp = test_endpoint("/api/config/backup", method="POST")
    print_status("Hit /api/config/backup returns 200 OK", s_bkp)
    
    s_rb, d_rb = test_endpoint("/api/config/rollback", method="POST")
    print_status("Hit /api/config/rollback returns 200 OK", s_rb)


    # 3. Gemini API & LLM Trigger
    print("\n--- 3. Gemini API & LLM Trigger ---")
    s_anom, d_anom = test_endpoint("/api/simulate-anomaly", method="POST", payload={"router": "Core-Router-Mumbai"})
    print_status("Hit /api/simulate-anomaly on Core-Router-Mumbai", s_anom)
    
    if s_anom:
        print("Waiting 10 seconds for Gemini API to reason and LangGraph to process...")
        time.sleep(10)
    else:
        print("Skipping LangGraph node progression due to anomaly failure.")


    # 4. LangGraph Node Progression
    print("\n--- 4. LangGraph Node Progression ---")
    s_logs, d_logs = test_endpoint("/agent-logs")
    if not s_logs:
        # Fallback to endpoint pattern sometimes seen
        s_logs, d_logs = test_endpoint("/api/agent-logs")
        
    print_status("Fetch /agent-logs returns 200 OK", s_logs)
    
    if s_logs:
        log_str = json.dumps(d_logs)
        nodes = ["[OBSERVE]", "[RETRIEVE]", "[INVESTIGATE]", "[REASON_AND_DECIDE]", "[ACT]", "[VERIFY]", "[LEARN]"]
        missing = []
        for n in nodes:
            # We check if the node label exists in the dumped logs
            # LangGraph logs usually emit these exact string tokens.
            if n not in log_str and n.strip("[]") not in log_str:
                missing.append(n)
        
        if not missing:
            print_status("Parsed agent logs verified progression through all required nodes", True)
        else:
            print_status(f"Agent failed to hit nodes: {missing}", False)


    # 5. Human-in-the-Loop Simulation
    print("\n--- 5. Human-in-the-Loop Simulation ---")
    # Inject HIGH-RISK anomaly. BGP down is high risk. We can try setting a known router.
    s_hi, d_hi = test_endpoint("/api/simulate-anomaly", method="POST", payload={"router": "Core-Router-Delhi", "type": "bgp_down"})
    print_status("Inject HIGH-RISK anomaly (BGP down) on Core-Router-Delhi", s_hi)
    
    print("Waiting 10 seconds for human-in-the-loop pause...")
    time.sleep(10)
    
    s_pend, d_pend = test_endpoint("/api/pending-approvals")
    print_status("Fetch /api/pending-approvals returns 200 OK", s_pend)
    
    has_pending = False
    thread_id = None
    if s_pend and isinstance(d_pend, dict) and d_pend.get("count", 0) > 0:
        has_pending = True
        thread_id = d_pend.get("pending", [])[0].get("thread_id")
        
    print_status("LangGraph successfully paused execution for Human Approval", has_pending)
    
    if has_pending and thread_id:
        s_app, d_app = test_endpoint("/api/approve", method="POST", payload={"thread_id": thread_id})
        print_status("Hit /api/approve to resume agent", s_app)
        
        print("Waiting 5 seconds for agent to resume and apply fix...")
        time.sleep(5)
    

    # 6. System Wipe
    print("\n--- 6. System Wipe ---")
    s_rst, d_rst = test_endpoint("/api/resolve/hard_reset", method="POST", payload={"router_name": "all"})
    if not s_rst:
        # try the other specific endpoint mentioned
        s_rst, d_rst = test_endpoint("/api/reset-all", method="POST")
        
    print_status("Hit system reset to restore pristine state", s_rst)

    print("\n" + "="*50)
    print("Test Suite Execution Complete")
    print("="*50)

if __name__ == "__main__":
    run_tests()
