"""Push, redeploy, and verify the server is actually running the new code.

    python deploy.py            # push main, trigger Coolify, wait for the sha
    python deploy.py --no-push  # redeploy whatever is already on origin

A plain `git push` does NOT deploy this app. Coolify lives on a LAN address
that GitHub cannot reach, so there is no webhook - the redeploy has to be asked
for. That gap is how the site came to serve three weeks of stale logic behind a
healthy hourly data refresh, looking green the whole time.

So this does the whole job and refuses to claim success it has not observed:
it waits until /health reports the commit that was just pushed.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import check_page

SITE = 'http://fpl.salwood.co.za'
POLL_SECONDS = 15
TIMEOUT_SECONDS = 420
UA = {'User-Agent': 'fleamarket-deploy'}


def sh(*args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f'{" ".join(args)} failed:\n{r.stderr.strip()}')
    return r.stdout.strip()


def health():
    try:
        req = urllib.request.Request(f'{SITE}/health', headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as exc:            # noqa: BLE001 - a restarting container
        return {'_error': f'{type(exc).__name__}: {exc}'}


def main():
    push = '--no-push' not in sys.argv

    dirty = sh('git', 'status', '--porcelain')
    if dirty and push:
        print('uncommitted changes - commit them first, or use --no-push:')
        print('\n'.join('  ' + ln for ln in dirty.splitlines()))
        sys.exit(1)

    # A dead JS function is not a Python error: the build exits 0, the tests
    # pass, the deploy verifies the sha and the page returns 200 with correct
    # markup. Only the console disagrees - which is how a blank planner shipped.
    for page in ('dashboard.html', 'my_dashboard.html'):
        if os.path.exists(page):
            bad = check_page.check(page)
            if bad:
                print(f'{page} is broken:')
                for b in sorted(set(bad)):
                    print('  ', b)
                sys.exit('refusing to deploy')
    print('page check ok')

    want = sh('git', 'rev-parse', 'HEAD')[:7]
    print(f'target  {want}  {sh("git", "log", "-1", "--format=%s")}')

    if push:
        print('push    ', end='', flush=True)
        print(sh('git', 'push', 'origin', 'HEAD') or 'ok')

    before = health().get('build', {}).get('sha')
    print(f'live    {before or "unreachable"}')
    if before == want:
        print('already running this commit')
        return

    print('trigger ', end='', flush=True)
    print(sh(sys.executable, 'deploy_trigger.py'))

    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        h = health()
        if '_error' in h:
            print(f'  ... {h["_error"]}')
            continue
        got = h.get('build', {}).get('sha')
        left = int(deadline - time.time())
        print(f'  ... live={got} status={h.get("status")} ({left}s left)')
        if got == want:
            stale = h.get('stale') or []
            print(f'\nDEPLOYED {want}')
            if stale:
                print(f'WARNING: stale data files: {", ".join(stale)}')
            return
    sys.exit(f'\nTIMED OUT: {SITE} is still not reporting {want}. '
             'The push landed but the deploy did not - check Coolify.')


if __name__ == '__main__':
    main()
