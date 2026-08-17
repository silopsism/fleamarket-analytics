"""Trigger a Coolify redeploy. Reads credentials from .coolify.env (gitignored):

    COOLIFY_URL=http://192.168.3.60:8000
    COOLIFY_TOKEN=<api token>
    COOLIFY_APP_UUID=<application uuid>

Prints deployment status only — never the token.
"""
import json
import sys
import urllib.request

cfg = {}
try:
    for line in open('.coolify.env', encoding='utf-8'):
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.strip().split('=', 1)
            cfg[k.strip()] = v.strip()
except FileNotFoundError:
    sys.exit('.coolify.env not found - create it next to this script')

missing = [k for k in ('COOLIFY_URL', 'COOLIFY_TOKEN', 'COOLIFY_APP_UUID') if not cfg.get(k)]
if missing:
    sys.exit(f'.coolify.env missing: {", ".join(missing)}')

url = f"{cfg['COOLIFY_URL'].rstrip('/')}/api/v1/deploy?uuid={cfg['COOLIFY_APP_UUID']}"
req = urllib.request.Request(url, method='POST', headers={
    'Authorization': f"Bearer {cfg['COOLIFY_TOKEN']}",
    'Accept': 'application/json',
})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.loads(r.read().decode('utf-8'))
        print('deploy triggered:', json.dumps(body)[:300])
except urllib.error.HTTPError as e:
    print(f'HTTP {e.code}: {e.read().decode()[:300]}')
    sys.exit(1)
