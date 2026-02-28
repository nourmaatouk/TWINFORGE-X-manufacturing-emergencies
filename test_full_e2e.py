"""
Full end-to-end diagnostic test for TwinForge Docker stack.
Tests: nginx routing, auth flow, dashboard accessibility, inter-service comms.
"""
import requests
import json
import sys

BASE = "http://localhost:18080"
DASHBOARD_INTERNAL = "http://localhost:18001"  # direct if port exposed


def ok(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    return cond


def section(title):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ─────────────────────────────────────────────
# 1. Basic health checks
# ─────────────────────────────────────────────
section("1. Health checks (unauthenticated)")

s = requests.Session()
s.headers["Origin"] = BASE

r = s.get(f"{BASE}/api/health")
ok("/api/health → 200", r.status_code == 200, r.text[:100])

r = s.get(f"{BASE}/dashboard/health", allow_redirects=False)
ok("/dashboard/health → 200", r.status_code == 200, r.text[:100])

r = s.get(f"{BASE}/dashboard/", allow_redirects=False)
ok("/dashboard/ (no auth) → 307 redirect", r.status_code == 307, r.headers.get("location", ""))

# ─────────────────────────────────────────────
# 2. Static assets through nginx
# ─────────────────────────────────────────────
section("2. Static asset routing via nginx")

r = s.get(f"{BASE}/dashboard/static/styles.css", allow_redirects=False)
ok("/dashboard/static/styles.css reachable (not redirect)", r.status_code in (200, 404), f"status={r.status_code}")

r = s.get(f"{BASE}/dashboard/static/app.js", allow_redirects=False)
ok("/dashboard/static/app.js reachable (not redirect)", r.status_code in (200, 404), f"status={r.status_code}")

# ─────────────────────────────────────────────
# 3. Login + OTP simulate
# ─────────────────────────────────────────────
section("3. Auth: Login")

r = s.post(f"{BASE}/api/auth/login", json={
    "email": "saif.hlaimi@gmail.com",
    "password": "SS123.123.###@@@Account_"
})
print(f"  POST /api/auth/login → {r.status_code}")
print(f"  Response: {r.text[:300]}")

login_ok = r.status_code == 200
ok("Login returns 200", login_ok)
if login_ok:
    data = r.json()
    challenge_id = data.get("challengeId", "")
    needs_real_otp = bool(data.get("message", "").startswith("OTP sent"))
    ok("challengeId present", bool(challenge_id), challenge_id[:20] if challenge_id else "MISSING")
    ok("OTP sent to email (Resend working)", needs_real_otp, data.get("message", ""))

    if not needs_real_otp and data.get("otpPreview"):
        otp = data["otpPreview"]
        print(f"  Dev mode OTP preview: {otp}")
        # Try to verify it
        r2 = s.post(f"{BASE}/api/auth/verify-otp", json={"challengeId": challenge_id, "otp": otp})
        ok("OTP verify (dev mode) → 200", r2.status_code == 200, r2.text[:150])
        if r2.status_code == 200:
            cookies = dict(s.cookies)
            ok("auth_token cookie set", "auth_token" in cookies, str(cookies))

# ─────────────────────────────────────────────
# 4. Dashboard accessibility with cookie
# ─────────────────────────────────────────────
section("4. Dashboard with auth cookie")
auth_cookie = s.cookies.get("auth_token", "")
if auth_cookie:
    r = s.get(f"{BASE}/dashboard/", allow_redirects=False)
    ok("/dashboard/ with auth cookie → 200", r.status_code == 200, f"status={r.status_code} body_len={len(r.text)}")

    r = s.get(f"{BASE}/dashboard/api/logs")
    ok("/dashboard/api/logs with auth → 200", r.status_code == 200, r.text[:100])

    r = s.get(f"{BASE}/dashboard/api/twins")
    ok("/dashboard/api/twins with auth → 200", r.status_code == 200, r.text[:100])
else:
    print("  [SKIP] No auth cookie — OTP requires real email. Checking direct backend access...")
    # Try direct to dashboard (bypasses auth gate for health only)
    r = s.get(f"{BASE}/dashboard/health")
    ok("/dashboard/health direct → 200", r.status_code == 200, r.text[:100])

# ─────────────────────────────────────────────
# 5. Inter-service connectivity tests (from host via docker exec)
# ─────────────────────────────────────────────
section("5. Nginx proxy config check")

r = s.get(f"{BASE}/api/health")
ok("nginx → auth-backend proxy works", r.status_code == 200, r.text[:80])

r = s.get(f"{BASE}/dashboard/health")
ok("nginx → twinforge-dashboard proxy works", r.status_code == 200, r.text[:80])

# ─────────────────────────────────────────────
# 6. Dashboard API (unauthenticated — should 307 or 401)
# ─────────────────────────────────────────────
section("6. Dashboard API auth gate")

s_noauth = requests.Session()
r = s_noauth.get(f"{BASE}/dashboard/api/logs", allow_redirects=False)
ok("/dashboard/api/logs no auth → 401 or 307", r.status_code in (401, 307), f"got {r.status_code}")

r = s_noauth.get(f"{BASE}/dashboard/api/twins", allow_redirects=False)
ok("/dashboard/api/twins no auth → 401 or 307", r.status_code in (401, 307), f"got {r.status_code}")

print()
print("=" * 60)
print("  Diagnostic complete")
print("=" * 60)
