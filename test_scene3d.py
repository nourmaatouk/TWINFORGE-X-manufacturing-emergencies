"""Verify scene3d fix and all 3D-related endpoints."""
import requests
import subprocess
import json
import sys

BASE = "http://localhost:18080"

result = subprocess.run(
    ["docker", "exec", "challenge_talan-auth-backend-1", "node", "-e",
     "const j=require('jsonwebtoken'),s=process.env.JWT_SECRET,"
     "t=j.sign({sub:'1',email:'saif.hlaimi@gmail.com',role:'user'},s,"
     "{algorithm:'HS256',expiresIn:'1h',issuer:'twinforge-auth',audience:'twinforge-ui'});"
     "console.log(t)"],
    capture_output=True, text=True, timeout=10
)
token = result.stdout.strip()
print(f"Token OK: {token[:40]}...\n")

AUTH = {"Cookie": f"auth_token={token}"}

tests = [
    ("scene3d (was 404)",           "GET",  "/dashboard/api/dashboard/scene3d"),
    ("overview",                    "GET",  "/dashboard/api/dashboard/overview"),
    ("assets",                      "GET",  "/dashboard/api/dashboard/assets"),
    ("components",                  "GET",  "/dashboard/api/dashboard/components"),
    ("process",                     "GET",  "/dashboard/api/dashboard/process"),
    ("predictions",                 "GET",  "/dashboard/api/dashboard/predictions"),
    ("static twin3d.js",            "GET",  "/dashboard/static/twin3d.js"),
]

passed = failed = 0
for label, method, path in tests:
    r = requests.request(method, BASE + path, headers=AUTH, timeout=10)
    ok = r.status_code == 200
    mark = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
        if r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
            keys = list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]"
            print(f"  [{mark}] {label:<35} {r.status_code} keys={keys}")
        else:
            print(f"  [{mark}] {label:<35} {r.status_code} ({r.headers.get('content-type','')[:40]})")
    else:
        failed += 1
        print(f"  [{mark}] {label:<35} {r.status_code}  body={r.text[:80]}")

print(f"\n{'='*60}")
print(f"  {passed}/{passed+failed} passed   {'ALL OK' if failed==0 else str(failed)+' FAILED'}")
print(f"{'='*60}")
sys.exit(0 if failed == 0 else 1)
