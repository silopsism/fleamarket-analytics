"""What build is this, and when was it made.

The app spent three weeks serving stale logic behind a perfectly healthy data
refresh: bootstrap.json updated every hour, the page rebuilt every hour, and
the code underneath was three weeks old because a push had never reached the
server. Nothing on the page or in any endpoint said which commit it came from,
so there was nothing to notice.

Resolution order is git, then the build-time stamp baked in by dashboard.py,
then whatever the platform injected. A container built from a tarball has no
.git, so git alone is not enough.
"""
import json
import os
import subprocess
from datetime import datetime, timezone

STAMP = 'build_stamp.json'          # written by dashboard.py, read in prod
_ENV_KEYS = ('SOURCE_COMMIT', 'GIT_COMMIT', 'COMMIT_SHA', 'RENDER_GIT_COMMIT',
             'COOLIFY_GIT_COMMIT_SHA')


def _git(*args):
    try:
        out = subprocess.run(('git',) + args, capture_output=True, text=True,
                             timeout=5, cwd=os.path.dirname(os.path.abspath(__file__)))
        return out.stdout.strip() if out.returncode == 0 else ''
    except Exception:          # noqa: BLE001 - no git, no repo, no problem
        return ''


def _stamp():
    try:
        with open(STAMP, encoding='utf-8') as f:
            return json.load(f)
    except Exception:          # noqa: BLE001
        return {}


def sha(short=True):
    """Commit this code came from, or 'unknown'."""
    s = _git('rev-parse', 'HEAD')
    if not s:
        s = _stamp().get('sha') or ''
    if not s:
        for k in _ENV_KEYS:
            if os.environ.get(k):
                s = os.environ[k]
                break
    if not s:
        return 'unknown'
    return s[:7] if short else s


def dirty():
    """True when the working tree has uncommitted changes (dev only)."""
    if not _git('rev-parse', 'HEAD'):
        return False
    return bool(_git('status', '--porcelain'))


def info():
    st = _stamp()
    return {
        'sha': sha(),
        'dirty': dirty(),
        'subject': _git('log', '-1', '--format=%s') or st.get('subject', ''),
        'committed_at': _git('log', '-1', '--format=%cI') or st.get('committed_at', ''),
        'built_at': st.get('built_at', ''),
    }


def write_stamp():
    """Bake the current commit into a file the container can read later."""
    d = {'sha': sha(False) or 'unknown',
         'subject': _git('log', '-1', '--format=%s'),
         'committed_at': _git('log', '-1', '--format=%cI'),
         'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    with open(STAMP, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
    return d


if __name__ == '__main__':
    print(json.dumps(info(), indent=1))
