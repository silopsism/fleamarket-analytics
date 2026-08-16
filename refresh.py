"""Daily data refresh: pull fresh FPL API snapshots, regenerate dashboard.html.

Run from the app directory (Coolify scheduled task / cron):  python refresh.py
app.py notices bootstrap.json's new mtime and reloads its model cache itself.
"""
import subprocess
import sys
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (fleamarket-analytics; personal FPL tool)'}

for url, path in [
    ('https://fantasy.premierleague.com/api/bootstrap-static/', 'bootstrap.json'),
    ('https://fantasy.premierleague.com/api/fixtures/', 'fixtures.json'),
]:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    with open(path, 'wb') as f:
        f.write(data)
    print(f'{path}: {len(data):,} bytes')

subprocess.run([sys.executable, 'dashboard.py'], check=True)
print('dashboard.html regenerated')
