"""Merge edge CSVs into a single typed SystemGraph edge list + summary by (src,dst,kind) with evidence counts."""
import csv, os, collections
from common import *
CONF = {'declared': 1, 'artifact': 2, 'contract': 3, 'infra': 4, 'config': 4, 'text': 5}
def rows(name):
    p = os.path.join(OUT, name)
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []
def contract_repos():
    # a repo is a 'contract repo' if >=50% of its non-doc files are schema files
    out = set()
    for repo in repos():
        fs = [p for p in walk(repo)]
        n = len([p for p in fs if not p.endswith(('.md', 'LICENSE', 'NOTICE', '.txt'))]) or 1
        k = len([p for p in fs if p.endswith(('.proto', '.graphqls', '.graphql', '.avsc', '.avdl', 'openapi.yaml', 'openapi.json', 'swagger.yaml', 'swagger.json'))])
        if k / n >= 0.3 or repo.endswith(('-proto', '-protocol', '-contracts', '-api-spec')): out.add(repo)  # name suffix = convention, reported as such
    return out
CONTRACT_REPOS = contract_repos()
def main():
    print('contract repos (>=30% schema files or *-proto/-protocol name):', sorted(CONTRACT_REPOS))
    edges = []
    for r in rows('edges_maven.csv'): edges.append((r['src_repo'], r['dst_repo'], r['kind'], r['coordinate'], r['evidence_file'], r['line']))
    for r in rows('edges_go.csv'):
        if r['dst_repo'] != '?': edges.append((r['src_repo'], r['dst_repo'], r['kind'], r['module'], r['evidence_file'], r['line']))
    for r in rows('edges_npm.csv'): edges.append((r['src_repo'], r['dst_repo'], r['kind'], r['package'], r['evidence_file'], r['line']))
    for r in rows('proto_imports.csv'):
        if r['status'] == 'resolved-other':
            for d in r['dst_repos'].split(','): edges.append((r['src_repo'], d, r['kind'], r['import'], r['evidence_file'], r['line']))
    for r in rows('edges_graphql.csv'): edges.append((r['src_repo'], r['dst_repo'], r['kind'], r['field'], r['evidence_file'], r['line']))
    for r in rows('edges_infra.csv'):
        if r['dst_repo'] != r['src_repo']: edges.append((r['src_repo'], r['dst_repo'], r['kind'], r['ref'], r['evidence_file'], r['line']))
    # proto copies -> contract:proto-copy edges toward the contract repo (repo whose only content is protos)
    copies = rows('proto_copies.csv')
    by_hash = collections.defaultdict(list)
    for c in copies: by_hash[c['hash']].append(c)
    for h, cs in by_hash.items():
        origins = [c for c in cs if c['repo'] in CONTRACT_REPOS]
        for c in cs:
            for o in origins:
                if o['repo'] != c['repo']: edges.append((c['repo'], o['repo'], 'contract:proto-copy', c['package'], c['path'], ''))
    # config:kafka-topic edges from code string literals shared by >=2 repos (main scope only)
    lits = [r for r in rows('code_string_literals.csv') if r['scope'] == 'main' and r['literal'].startswith('skywalking-') and not r['literal'].startswith('apache/')]
    by_lit = collections.defaultdict(list)
    for r in lits: by_lit[r['literal']].append(r)
    for lit, rs in by_lit.items():
        rps = {r['repo'] for r in rs}
        if len(rps) < 2: continue
        for a in rs:
            for b in rs:
                if a['repo'] != b['repo'] and a['role'] == 'consumer' and b['role'] == 'producer':
                    edges.append((a['repo'], b['repo'], 'config:kafka-topic', lit, a['file'], a['line']))
    for r in rows('proto_copy_drift.csv'):
        a, b = r['repo_a'], r['repo_b']
        if b in CONTRACT_REPOS and a not in CONTRACT_REPOS: edges.append((a, b, 'contract:proto-copy', f"{r['package']}/{r['file']} {r['status']}", r['path_a'], ''))
        elif a in CONTRACT_REPOS and b not in CONTRACT_REPOS: edges.append((b, a, 'contract:proto-copy', f"{r['package']}/{r['file']} {r['status']}", r['path_b'], ''))
    edges = sorted(set(edges))
    def scope(path):
        p = '/' + path
        return 'test' if ('/test/' in p or '/tests/' in p or '/e2e' in p or '/.github/' in p or '/ci/' in p) else 'main'
    write_csv('system_edges.csv', [list(e) + [CONF.get(e[2].split(':')[0], 9), scope(e[4])] for e in edges], ['src_repo', 'dst_repo', 'kind', 'ref', 'evidence_file', 'line', 'confidence_class', 'scope'])
    sc = collections.Counter((e[2], scope(e[4])) for e in edges)
    print('\n== kind x scope:', sorted(sc.items()))
    agg = collections.Counter((e[0], e[1], e[2]) for e in edges)
    write_csv('system_edges_summary.csv', [[s, d, k, n] for (s, d, k), n in sorted(agg.items())], ['src_repo', 'dst_repo', 'kind', 'n_evidence'])
    pair = collections.defaultdict(set)
    for (s, d, k), n in agg.items(): pair[(s, d)].add(k.split(':')[0])
    print('\n== repo pairs (src -> dst): signal classes')
    for (s, d), ks in sorted(pair.items()): print(f'{s:34s} -> {d:34s} {sorted(ks)}')
    print('\n== edge kinds:', collections.Counter(e[2] for e in edges))
main()
