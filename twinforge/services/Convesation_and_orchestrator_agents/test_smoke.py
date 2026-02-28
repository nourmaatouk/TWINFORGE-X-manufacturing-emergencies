"""Quick debug test - no unicode chars."""
import traceback
import sys

def test():
    print("=== TWINFORGE SMOKE TEST ===")
    
    try:
        print("[1] Importing modules...")
        from twinforge.core.config import get_settings
        from twinforge.graph.workflow import get_graph
        print("  OK: imports done")
        
        print("[2] Getting settings...")
        settings = get_settings()
        print(f"  OK: groq_key present = {bool(settings.groq_api_key)}")
        print(f"  OK: data_dir = {settings.data_dir}")
        
        print("[3] Creating graph...")
        graph = get_graph()
        print("  OK: graph created")
        
        print("[4] Running CREATE_TWIN...")
        result = graph.invoke("Create a digital twin for a CNC machine on floor 2")
        
        ir = result.get("intent_result")
        tr = result.get("twin_result")
        
        if ir:
            print(f"  Intent: {ir.intent.value}")
            print(f"  Confidence: {ir.confidence}")
        
        if tr:
            print(f"  Twin ID: {tr.twin_id}")
            print(f"  OEE: {tr.kpis.oee}")
            print(f"  Alerts: {len(tr.alerts)}")
        
        print(f"  Response: {result.get('final_response', 'NONE')[:300]}")
        
        print("[5] Running LIST_TWINS...")
        result2 = graph.invoke("List all twins")
        print(f"  Response: {result2.get('final_response', 'NONE')[:200]}")
        
        print("[6] Running GET_KPI...")
        result3 = graph.invoke("Show me the OEE and KPIs")
        print(f"  Response: {result3.get('final_response', 'NONE')[:200]}")
        
        print("\n=== ALL TESTS PASSED ===")
        
    except Exception as e:
        print(f"\nFAILED: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test()
