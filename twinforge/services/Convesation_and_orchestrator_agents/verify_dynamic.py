
import requests
import json
import time

BASE_URL = "http://localhost:8001"

def test_dynamic_dashboard():
    print("Testing Dynamic Dashboard API...")
    
    # 1. Check initial state (should be empty or minimal)
    try:
        r = requests.get(f"{BASE_URL}/api/dashboard/overview")
        initial_data = r.json()
        initial_twins = initial_data.get("aggregate_kpis", {}).get("total_twins", 0)
        print(f"Initial twins: {initial_twins}")
    except Exception as e:
        print(f"Failed to fetch initial state: {e}")
        return

    # 2. Create a twin via Chat API
    print("Creating a new twin via Chat API...")
    payload = {
        "message": "Create a CNC machine twin on floor 2, line B, 50 kWh energy, 3 spindles use SMIA protocol",
        "session_id": "test-session"
    }
    try:
        r = requests.post(f"{BASE_URL}/api/chat", json=payload)
        if r.status_code == 200:
            print("Chat response received.")
        else:
            print(f"Chat request failed: {r.text}")
    except Exception as e:
        print(f"Chat request error: {e}")
        return

    # 3. Check updated state (should have +1 twin)
    time.sleep(2)  # Allow async processing if any (though currently synchronous)
    try:
        r = requests.get(f"{BASE_URL}/api/dashboard/overview")
        updated_data = r.json()
        updated_twins = updated_data.get("aggregate_kpis", {}).get("total_twins", 0)
        print(f"Updated twins: {updated_twins}")
        
        if updated_twins > initial_twins:
            print("SUCCESS: Dashboard dynamically updated!")
        else:
            print("FAILURE: Dashboard count did not increase.")
            
        # Verify floor clustering
        floors = updated_data.get("floors", {})
        if "2" in floors or "Floor 2" in floors:
             print("SUCCESS: Floor grouping verified.")
    except Exception as e:
        print(f"Failed to fetch updated state: {e}")

if __name__ == "__main__":
    test_dynamic_dashboard()
