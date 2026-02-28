"""
TWINFORGE Agent 3 — Test Telemetry Simulator Script
Standalone script that sends test telemetry to Agent 3 via REST API.

Usage:
    python test_telemetry_simulator.py [--url http://localhost:8003] [--count 50] [--interval 1]
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime

try:
    import httpx
except ImportError:
    print("httpx required: pip install httpx")
    sys.exit(1)


def generate_telemetry(machine_id: str) -> dict:
    """Generate a single telemetry data point."""
    return {
        "timestamp": datetime.now().isoformat(),
        "machine_id": machine_id,
        "energy_kwh": round(random.uniform(5.0, 20.0), 2),
        "water_liters": round(random.uniform(1.0, 8.0), 2),
        "vibration": round(random.uniform(0.5, 6.0), 2),
        "temperature": round(random.uniform(55.0, 85.0), 1),
        "status": random.choice(["running", "running", "running", "idle"]),
        "failure_flag": random.random() < 0.02,  # 2% failure rate
        "failure_risk_score": round(random.uniform(0.0, 0.3), 3),
    }


def main():
    parser = argparse.ArgumentParser(description="Send test telemetry to Agent 3")
    parser.add_argument("--url", default="http://localhost:8003", help="Agent 3 base URL")
    parser.add_argument("--count", type=int, default=50, help="Number of batches to send")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between batches")
    parser.add_argument("--machines", type=int, default=5, help="Number of machines")
    args = parser.parse_args()

    machines = [f"M{i+1}" for i in range(args.machines)]

    print(f"🏭 Sending telemetry to {args.url}/ingest")
    print(f"   Machines: {machines}")
    print(f"   Batches: {args.count}, Interval: {args.interval}s")
    print()

    client = httpx.Client(timeout=10.0)
    total_accepted = 0
    total_rejected = 0
    total_alerts = 0

    for i in range(args.count):
        batch = [generate_telemetry(m) for m in machines]

        try:
            resp = client.post(f"{args.url}/ingest", json={"data": batch})
            if resp.status_code == 200:
                result = resp.json()
                accepted = result.get("accepted", 0)
                rejected = result.get("rejected", 0)
                alerts = len(result.get("alerts", []))
                total_accepted += accepted
                total_rejected += rejected
                total_alerts += alerts

                status = "✅" if rejected == 0 else "⚠️"
                alert_str = f" 🚨 {alerts} alerts" if alerts > 0 else ""
                print(f"  {status} Batch {i+1}/{args.count}: {accepted} accepted, {rejected} rejected{alert_str}")
            else:
                print(f"  ❌ Batch {i+1}/{args.count}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ❌ Batch {i+1}/{args.count}: {e}")

        if i < args.count - 1:
            time.sleep(args.interval)

    print()
    print(f"📊 Summary:")
    print(f"   Total accepted: {total_accepted}")
    print(f"   Total rejected: {total_rejected}")
    print(f"   Total alerts:   {total_alerts}")


if __name__ == "__main__":
    main()
