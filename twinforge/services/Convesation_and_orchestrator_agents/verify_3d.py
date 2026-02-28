import requests

print("=== TWINFORGE 3D Verification ===\n")

# Test all API endpoints
endpoints = ['overview', 'components', 'assets', 'system', 'process', 'scene3d']
for ep in endpoints:
    try:
        r = requests.get(f'http://localhost:8001/api/dashboard/{ep}', timeout=5)
        d = r.json()
        print(f'  GET /api/dashboard/{ep}: {r.status_code}  keys={list(d.keys())[:4]}')
    except Exception as e:
        print(f'  GET /api/dashboard/{ep}: FAILED ({e})')

# Detailed scene3d check
r = requests.get('http://localhost:8001/api/dashboard/scene3d', timeout=5)
s = r.json()
print(f'\n  Scene3D: {s["total_machines"]} machines, {len(s["floors"])} floors')
print(f'  Building: {s["building"]}')
if s['floors']:
    f = s['floors'][0]
    print(f'  Floor {f["floor"]}: {f["machine_count"]} machines, {len(f["pipelines"])} pipelines')
    if f['machines']:
        m = f['machines'][0]
        print(f'  Machine: {m["twin_id"]} type={m["asset_type"]} pos=({m["world_x"]},{m["world_z"]})')

# Test static files
print('\n=== Static Files ===')
for path in ['/static/twin3d.js', '/static/app.js', '/static/styles.css', '/']:
    r = requests.get(f'http://localhost:8001{path}', timeout=5)
    print(f'  GET {path}: {r.status_code} ({len(r.text)} bytes)')

# Check HTML contains 3D elements
r = requests.get('http://localhost:8001/', timeout=5)
html = r.text
checks = ['twin3d', 'three-canvas', 'view3d-toolbar', 'hud-info', 'twin3d.js', 'three.min.js']
print('\n=== HTML Content Checks ===')
all_ok = True
for check in checks:
    found = check in html
    if not found:
        all_ok = False
    print(f'  "{check}": {"YES" if found else "MISSING"}')

print(f'\n{"SUCCESS: All checks passed!" if all_ok else "SOME CHECKS FAILED"}')
