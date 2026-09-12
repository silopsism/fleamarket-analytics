"""Static sanity check on a generated page's JavaScript.

Python builds the page, so a JavaScript function that no longer exists is not a
build error: dashboard.py exits 0, every placeholder resolves, the tests pass and
the server returns 200 with correct-looking markup. The only symptom is a console
error and a blank table, which is exactly how a dead planner reached production.

Two checks, both cheap and both specific to the mistakes that actually happen
when editing a file where JS lives inside Python strings:

  * a function called in STATEMENT position that nothing defines - the signature
    of a helper deleted along with its neighbour
  * a template placeholder left unresolved
"""
import re
import sys

# things the browser provides, or that are ours by another name
GLOBALS = {
    'if', 'for', 'while', 'switch', 'catch', 'return', 'typeof', 'function',
    'new', 'else', 'do', 'await', 'async', 'var', 'let', 'const', 'try',
    'Math', 'JSON', 'Object', 'Array', 'Number', 'String', 'Boolean', 'Set',
    'Map', 'Date', 'RegExp', 'Promise', 'Intl', 'parseInt', 'parseFloat',
    'isNaN', 'setTimeout', 'clearTimeout', 'setInterval', 'requestAnimationFrame',
    'fetch', 'alert', 'prompt', 'confirm', 'encodeURIComponent',
    'decodeURIComponent', 'document', 'window', 'localStorage', 'console',
    # bare browser globals and a few shapes the regex cannot see through:
    # parameters used as callbacks, and methods reached off a line break
    'addEventListener', 'scrollTo', 'scrollBy', 'matchMedia', 'getComputedStyle',
}


def check(path):
    html = open(path, encoding='utf-8').read()
    problems = []

    left = sorted(set(re.findall(r'__[A-Z][A-Z_]*__', html)))
    if left:
        problems.append(f'unresolved placeholders: {", ".join(left)}')

    js = '\n'.join(re.findall(r'<script>(.*?)</script>', html, re.S))
    defined = (set(re.findall(r'function\s+(\w+)\s*\(', js))
               | set(re.findall(r'(?:const|let|var)\s+(\w+)\s*=', js))
               | set(re.findall(r'(\w+)\s*=\s*(?:function|\()', js))
               # names bound as function parameters are callable inside it
               | set(re.findall(r'function\s*\w*\s*\(([^)]*)\)', js).__str__()
                     .replace("'", '').replace('[', '').replace(']', '')
                     .replace(' ', '').split(','))
               | GLOBALS)
    # a call in statement position: start of line or right after ; { } ) - and
    # crucially NOT preceded by a dot, which would make it a method
    for m in re.finditer(r'(?:^|[;{}]|\)\s*)\s*(?<![.\w$])([a-z]\w+)\s*\(', js, re.M):
        name = m.group(1)
        if name not in defined:
            line = js[:m.start()].count('\n') + 1
            problems.append(f'{name}() called at script line {line} but never defined')
    return problems


if __name__ == '__main__':
    paths = sys.argv[1:] or ['dashboard.html']
    bad = False
    for p in paths:
        found = check(p)
        if found:
            bad = True
            print(f'{p}:')
            for f in sorted(set(found)):
                print('  ', f)
        else:
            print(f'{p}: ok')
    sys.exit(1 if bad else 0)
