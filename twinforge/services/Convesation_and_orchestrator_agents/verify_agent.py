"""
Agent 2 Verification: SMIA + TFT Integration Test
"""
import requests
import json
import sys

BASE = "http://localhost:8002"

def test(name, fn):
    try:
        result = fn()
        print(f"  ✅ {name}: {result}")
        return True
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        return False

passed = 0
total = 0

print("=" * 60)
print("  AGENT 2 VALIDATION: SMIA + TFT INTEGRATION")
print("=" * 60)

# 1. Health check
print("\n📡 1. Agent 2 Health Check")
total += 1
if test("Health", lambda: requests.get(f"{BASE}/health", timeout=5).json()):
    passed += 1

# 2. SMIA agents (before twin creation)
print("\n🤖 2. SMIA Agents (Pre-Creation)")
total += 1
if test("SMIA Agents", lambda: requests.get(f"{BASE}/smia/agents", timeout=5).json()):
    passed += 1

# 3. Create a twin via process_intent
print("\n🏭 3. Create Twin via process_intent")
total += 1
payload = {
    "intent_result": {
        "intent": "CREATE_TWIN",
        "entities": {
            "type": "CNC",
            "name": "CNC-Alpha",
            "floor": "2",
            "line": "B",
            "energy": "120 kWh",
            "protocol": "OPC-UA"
        },
        "confidence": 0.95,
        "raw_message": "Create a CNC machine twin on floor 2 line B 120 kWh",
        "session_id": "smia_test"
    },
    "data_response": {
        "sensor_data": {
            "temperature": {"value": 72.5, "unit": "C"},
            "vibration": {"value": 3.2, "unit": "mm/s"},
            "spindle_speed": {"value": 8500, "unit": "RPM"},
            "tool_wear": {"value": 42, "unit": "%"},
            "energy_consumption": {"value": 118, "unit": "kWh"},
            "coolant_flow": {"value": 12, "unit": "L/min"},
            "pressure": {"value": 85, "unit": "bar"},
            "current": {"value": 45, "unit": "A"}
        },
        "anomalies": [],
        "source": "test"
    }
}
try:
    r = requests.post(f"{BASE}/process_intent", json=payload, timeout=30)
    data = r.json()
    twin_id = data.get("twin_id", "")
    print(f"  ✅ Twin Created: {twin_id}")
    print(f"     OEE: {data.get('kpis', {}).get('oee', 'N/A')}%")
    print(f"     AAS: {data.get('aas_reference', 'N/A')}")
    print(f"     Reasoning: {len(data.get('reasoning_trace', []))} steps")
    passed += 1
except Exception as e:
    twin_id = ""
    print(f"  ❌ Create Twin: {e}")

# 4. SMIA agents (after creation)
print("\n🤖 4. SMIA Agents (Post-Creation)")
total += 1
try:
    r = requests.get(f"{BASE}/smia/agents", timeout=5)
    data = r.json()
    print(f"  ✅ Agent Count: {data.get('agent_count', 0)}")
    print(f"     Mode: {data.get('mode', 'N/A')}")
    for agent in data.get("agents", []):
        print(f"     Agent: {agent.get('twin_id', 'N/A')} | Alive: {agent.get('is_alive', False)}")
        css = agent.get("css_model", {})
        print(f"       Capabilities: {css.get('capabilities', [])}")
        print(f"       Skills: {css.get('skills', [])}")
        print(f"       Services: {css.get('services', [])}")
    passed += 1
except Exception as e:
    print(f"  ❌ SMIA Agents: {e}")

# 5. Specific SMIA agent status
if twin_id:
    print(f"\n🤖 5. SMIA Agent [{twin_id}]")
    total += 1
    try:
        r = requests.get(f"{BASE}/smia/agents/{twin_id}", timeout=5)
        data = r.json()
        print(f"  ✅ Agent JID: {data.get('agent_jid', 'N/A')}")
        print(f"     Twin Level: {data.get('twin_level', 'N/A')}")
        print(f"     Behaviours: {data.get('behaviours_count', 0)}")
        print(f"     Sensor Channels: {data.get('sensor_channels', 0)}")
        passed += 1
    except Exception as e:
        print(f"  ❌ SMIA Agent: {e}")

# 6. TFT Prediction
if twin_id:
    print(f"\n📈 6. TFT Prediction [{twin_id}]")
    total += 1
    try:
        r = requests.get(f"{BASE}/tft/predict/{twin_id}", timeout=10)
        data = r.json()
        print(f"  ✅ Horizon: {data.get('horizon_hours', 0)}h")
        print(f"     Anomaly Risk: {data.get('anomaly_risk', 'N/A')}")
        print(f"     Trend: {data.get('trend_direction', 'N/A')}")
        print(f"     History Points: {data.get('history_points', 0)}")
        print(f"     Model: {data.get('model_info', {}).get('architecture', 'N/A')}")
        q = data.get("quantiles", {})
        if q.get("p50"):
            print(f"     P50 (first 3): {q['p50'][:3]}")
        passed += 1
    except Exception as e:
        print(f"  ❌ TFT Prediction: {e}")

# 7. Dashboard overview
print("\n📊 7. Dashboard Overview")
total += 1
try:
    r = requests.get(f"{BASE}/dashboard/overview", timeout=10)
    data = r.json()
    kpis = data.get("aggregate_kpis", {})
    print(f"  ✅ Aggregate OEE: {kpis.get('avg_oee', 'N/A')}%")
    print(f"     Total Twins: {kpis.get('total_twins', 0)}")
    print(f"     Alerts: {len(data.get('alerts', []))}")
    print(f"     Floors: {data.get('floors', {})}")
    print(f"     Lines: {data.get('lines', {})}")
    passed += 1
except Exception as e:
    print(f"  ❌ Dashboard Overview: {e}")

# 8. Dashboard predictions
print("\n📈 8. Dashboard Predictions")
total += 1
try:
    r = requests.get(f"{BASE}/dashboard/predictions?sensor=temperature", timeout=10)
    data = r.json()
    preds = data.get("predictions", {})
    print(f"  ✅ Predictions: {len(preds)} twin(s)")
    if isinstance(preds, list):
        for p in preds[:2]:
            print(f"     {p.get('twin_id')}: risk={p.get('anomaly_risk', 0)}, trend={p.get('trend_direction', 'N/A')}")
    elif isinstance(preds, dict):
        for tid, p in list(preds.items())[:2]:
            risk = p.get("anomaly_risk", 0) if isinstance(p, dict) else "N/A"
            print(f"     {tid}: risk={risk}")
    passed += 1
except Exception as e:
    print(f"  ❌ Dashboard Predictions: {e}")

# 9. List twins
print("\n📋 9. List Twins")
total += 1
try:
    r = requests.get(f"{BASE}/twins", timeout=5)
    twins = r.json()
    print(f"  ✅ Total Twins: {len(twins)}")
    for t in twins:
        print(f"     {t.get('twin_id')}: {t.get('asset_type')} | Floor {t.get('floor')} | Line {t.get('line')}")
    passed += 1
except Exception as e:
    print(f"  ❌ List Twins: {e}")

print("\n" + "=" * 60)
print(f"  RESULTS: {passed}/{total} tests passed")
print("=" * 60)
