"""Protobuf: packages/services defined per repo, imports, and vendored copies (same content hash across repos).
Cross-repo edge kinds: contract:proto-import (import resolves to a file only another repo defines),
contract:proto-copy (identical file content in >=2 repos: one is the origin = the contract repo)."""
import re, hashlib, os
from common import *
def main():
    files = []
    for repo in repos():
        for p in walk(repo, exts={'.proto'}):
            t = read_text(p)
            pkg = (re.search(r'^\s*package\s+([\w.]+)\s*;', t, re.M) or [None, ''])[1]
            imps = [(line_of(t, m.start()), m.group(1)) for m in re.finditer(r'^\s*import\s+(?:public\s+)?"([^"]+)"\s*;', t, re.M)]
            svcs = re.findall(r'^\s*service\s+(\w+)', t, re.M)
            msgs = re.findall(r'^\s*message\s+(\w+)', t, re.M)
            go_pkg = (re.search(r'option\s+go_package\s*=\s*"([^"]+)"', t) or [None, ''])[1]
            java_pkg = (re.search(r'option\s+java_package\s*=\s*"([^"]+)"', t) or [None, ''])[1]
            norm = re.sub(r'\s+', ' ', re.sub(r'//.*', '', t)).strip()
            h = hashlib.sha1(norm.encode()).hexdigest()[:12]
            files.append(dict(repo=repo, path=rel(p), abspath=p, pkg=pkg, imports=imps, services=svcs, messages=msgs, go_pkg=go_pkg, java_pkg=java_pkg, hash=h, base=os.path.basename(p)))
    write_csv('proto_files.csv', [[f['repo'], f['path'], f['pkg'], ';'.join(f['services']), len(f['messages']), f['go_pkg'], f['java_pkg'], f['hash']] for f in files],
              ['repo', 'path', 'package', 'services', 'n_messages', 'go_package', 'java_package', 'hash'])
    # copies
    by_hash = {}
    for f in files: by_hash.setdefault(f['hash'], []).append(f)
    copies = []
    for h, fs in by_hash.items():
        rs = sorted({f['repo'] for f in fs})
        if len(rs) > 1:
            for f in fs:
                copies.append([h, f['repo'], f['path'], f['pkg'], ';'.join(f['services']), ','.join(rs)])
    # same (package, basename) in >=2 repos with different content => vendored copy with drift
    import difflib
    by_key = {}
    for f in files:
        if f['pkg']: by_key.setdefault((f['pkg'], f['base']), []).append(f)
    drift = []
    for (pkg, base), fs in by_key.items():
        rs = sorted({f['repo'] for f in fs})
        if len(rs) < 2: continue
        for a in fs:
            for b in fs:
                if a['repo'] < b['repo']:
                    ta, tb = read_text(a['abspath']).splitlines(), read_text(b['abspath']).splitlines()
                    nd = sum(1 for l in difflib.unified_diff(ta, tb, lineterm='', n=0) if l[:1] in '+-' and not l.startswith(('+++', '---')))
                    drift.append([pkg, base, a['repo'], a['path'], b['repo'], b['path'], 'identical' if a['hash'] == b['hash'] else f'differs:{nd}_lines'])
    write_csv('proto_copy_drift.csv', drift, ['package', 'file', 'repo_a', 'path_a', 'repo_b', 'path_b', 'status'])
    write_csv('proto_copies.csv', copies, ['hash', 'repo', 'path', 'package', 'services', 'repos_sharing'])
    # import resolution: by import path suffix
    by_suffix = {}
    for f in files:
        parts = f['path'].split('/')[1:]  # drop repo
        for i in range(len(parts)):
            by_suffix.setdefault('/'.join(parts[i:]), []).append(f)
    edges = []
    for f in files:
        for ln, imp in f['imports']:
            THIRD_PARTY = ('google/', 'validate/', 'envoy/', 'udpa/', 'xds/', 'opentelemetry/', 'istio/', 'prometheus/', 'gogoproto/', 'k8s.io/', 'protoc-gen-')
            if imp.startswith(THIRD_PARTY):
                edges.append([f['repo'], '(third-party)', 'contract:proto-import', imp, f['path'], ln, 'third-party-vendored']); continue
            cands = by_suffix.get(imp, [])
            same = [c for c in cands if c['repo'] == f['repo']]
            other = sorted({c['repo'] for c in cands if c['repo'] != f['repo']})
            edges.append([f['repo'], ','.join(other) if not same else '(local)', 'contract:proto-import', imp, f['path'], ln, 'resolved-local' if same else ('resolved-other' if other else 'unresolved')])
    write_csv('proto_imports.csv', edges, ['src_repo', 'dst_repos', 'kind', 'import', 'evidence_file', 'line', 'status'])
    # package-level summary
    pk = {}
    for f in files: pk.setdefault(f['pkg'], set()).add(f['repo'])
    write_csv('proto_packages.csv', [[p, ','.join(sorted(r)), len(r)] for p, r in sorted(pk.items())], ['package', 'repos', 'n_repos'])
main()
