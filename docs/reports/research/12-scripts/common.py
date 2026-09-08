"""Shared helpers for cross-repo relation extraction (stdlib only)."""
import os, csv, sys, json, re
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
REPOS = os.path.join(ROOT, 'repos')
OUT = os.path.join(ROOT, 'out')
SKIP_DIRS = {'.git', 'node_modules', 'target', 'dist', 'build', '.idea'}

def repos():
    return sorted(d for d in os.listdir(REPOS) if os.path.isdir(os.path.join(REPOS, d)))

def walk(repo, exts=None, names=None, max_size=2_000_000):
    base = os.path.join(REPOS, repo)
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if (exts and os.path.splitext(f)[1] in exts) or (names and f in names) or (not exts and not names):
                p = os.path.join(dp, f)
                try:
                    if os.path.getsize(p) <= max_size:
                        yield p
                except OSError:
                    pass

def rel(p):
    return os.path.relpath(p, REPOS)

def write_csv(name, rows, header):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with open(p, 'w', newline='') as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f'wrote {p} ({len(rows)} rows)', file=sys.stderr)
    return p

def read_text(p):
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

def line_of(text, idx):
    return text.count('\n', 0, idx) + 1
