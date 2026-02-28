"""Full end-to-end test of all Dashboard + Auth routes."""
import requests
import subprocess
import sys

BASE = "http://localhost:18080"

# Get a real JWT from the running container
result = subprocess.run(
    [
        "docker", "exec", "challenge_talan-auth-backend-1", "node", "-e",
        (
            "const j=require('jsonwebtoken'),s=process.env.JWT_SECRET,"
            "t=j.sign({sub:'1',email:'saif.hlaimi@gmail.com',role:'user'},s,"
            "{algorithm:'HS256',expiresIn:'1h',issuer:'twinforge-auth',audience:'twinforge-ui'});"
            "console.log(t)"
        ),
    ],
    capture_output=True, text=True, timeout=10
)
token = result.stdout.strip()
if not token:
    print("ERROR: could not obtain token:", result.stderr)
    sys.exit(1)
print(f"Token OK: {token[:40]}...\n")

AUTH  = {"Cookie": f"auth_token={token}"}
NOAUTH = {}

tests = [
    # label                         method  path                                    headers  expected
    ("Auth /me",                    "GET",  "/api/auth/me",                         AUTH,    200),
    ("Dashboard HTML (auth)",       "GET",  "/dashboard/",                          AUTH,    200),
    ("Dashboard /health",           "GET",  "/dashboard/health",                    AUTH,    200),
    ("Static CSS",                  "GET",  "/dashboard/static/styles.css",         NOAUTH,  200),
    ("Static JS",                   "GET",  "/dashboard/static/app.js",             NOAUTH,  200),
    ("Static index served at /",    "GET",  "/dashboard/static/index.html",         NOAUTH,  200),   # static mount serves it
    ("API overview (auth)",         "GET",  "/dashboard/api/dashboard/overview",    AUTH,    200),
    ("API components (auth)",       "GET",  "/dashboard/api/dashboard/components",  AUTH,    200),
    ("API assets (auth)",           "GET",  "/dashboard/api/dashboard/assets",      AUTH,    200),
    ("API process (auth)",          "GET",  "/dashboard/api/dashboard/process",     AUTH,    200),
    ("API twins via server (auth)", "GET",  "/dashboard/api/twins",                 AUTH,    200),
    ("API logs (auth)",             "GET",  "/dashboard/api/logs",                  AUTH,    200),
    ("API chat (auth)",             "POST", "/dashboard/api/chat",                  AUTH,    200),
    ("Dashboard no-auth -> 307",    "GET",  "/dashboard/",                          NOAUTH,  307),
    ("API no-auth -> 401",          "GET",  "/dashboard/api/dashboard/overview",    NOAUTH,  401),
    ("Bare /dashboard -> 301",      "GET",  "/dashboard",                           NOAUTH,  301),
]

passed = failed = 0
for label, method, path, hdrs, expected in tests:
    body = {"message": "list all twins", "session_id": "e2e-test"} if method == "POST" else None
    try:
        r = requests.request(
            method, BASE + path, headers=hdrs, json=body,
            timeout=15, allow_redirects=False
        )
        ok = r.status_code == expected
        mark = "PASS" if ok else "FAIL"
        extra = "" if ok else f"  body={r.text[:80].replace(chr(10),' ')}"
        print(f"  [{mark}] {label:<40} {r.status_code} (want {expected}){extra}")
        if ok:
            passed += 1
        else:
            failed += 1
    except Exception as exc:
        print(f"  [FAIL] {label:<40} ERROR: {exc}")
        failed += 1

print(f"\n{'='*60}")
print(f"  {passed}/{passed+failed} passed   {'ALL OK' if failed==0 else str(failed)+' FAILED'}")
print(f"{'='*60}")
sys.exit(0 if failed == 0 else 1)
