"""Go modules: module path produced vs require'd across repos, incl. replace directives."""
import re
from common import *
def main():
    mods, reqs, repl = [], [], []
    for repo in repos():
        for p in walk(repo, names={'go.mod'}):
            text = read_text(p); lines = text.split('\n')
            modname = ''
            in_req = in_repl = False
            for i, l in enumerate(lines, 1):
                s = l.split('//')[0].strip(); indirect = '// indirect' in l
                if s.startswith('module '): modname = s.split()[1]; mods.append([repo, rel(p), modname]); continue
                if s.startswith('require ('): in_req = True; continue
                if s.startswith('replace ('): in_repl = True; continue
                if s == ')': in_req = in_repl = False; continue
                m = re.match(r'require\s+(\S+)\s+(\S+)', s)
                if m: reqs.append([repo, rel(p), i, m.group(1), m.group(2), indirect]); continue
                if in_req:
                    m = re.match(r'(\S+)\s+(\S+)', s)
                    if m: reqs.append([repo, rel(p), i, m.group(1), m.group(2), indirect])
                m = re.match(r'(?:replace\s+)?(\S+)(?:\s+\S+)?\s*=>\s*(\S+)', s)
                if m and (in_repl or s.startswith('replace')): repl.append([repo, rel(p), i, m.group(1), m.group(2)])
    write_csv('go_modules.csv', mods, ['repo', 'gomod', 'module'])
    write_csv('go_requires.csv', reqs, ['repo', 'gomod', 'line', 'module', 'version', 'indirect'])
    prod = {}
    for r in mods: prod.setdefault(r[2], set()).add(r[0])
    edges = []
    for q in reqs:
        for prepo in prod.get(q[3], ()):
            if prepo != q[0]:
                edges.append([q[0], prepo, 'artifact:go', q[3], q[4], 'indirect' if q[5] else 'direct', q[1], q[2]])
    for r in repl:
        edges.append([r[0], '?', 'artifact:go-replace', r[3], r[4], '', r[1], r[2]])
    write_csv('edges_go.csv', edges, ['src_repo', 'dst_repo', 'kind', 'module', 'version', 'directness', 'evidence_file', 'line'])
    unres = [q for q in reqs if ('skywalking' in q[3]) and q[3] not in prod]
    write_csv('go_unresolved_internal.csv', unres, ['repo', 'gomod', 'line', 'module', 'version', 'indirect'])
main()
