"""npm: package.json name vs dependencies across repos."""
import json, re
from common import *
def main():
    prod, cons = [], []
    for repo in repos():
        for p in walk(repo, names={'package.json'}):
            text = read_text(p)
            try: j = json.loads(text)
            except Exception: continue
            name = j.get('name', '')
            if name: prod.append([repo, rel(p), name, j.get('version', ''), str(j.get('private', False))])
            for sec in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
                for dep, ver in (j.get(sec) or {}).items():
                    m = re.search(r'"%s"\s*:' % re.escape(dep), text)
                    cons.append([repo, rel(p), line_of(text, m.start()) if m else '', dep, ver, sec])
    write_csv('npm_produced.csv', prod, ['repo', 'file', 'name', 'version', 'private'])
    write_csv('npm_consumed.csv', cons, ['repo', 'file', 'line', 'name', 'range', 'section'])
    pm = {}
    for r in prod: pm.setdefault(r[2], set()).add(r[0])
    edges = [[c[0], pr, 'artifact:npm', c[3], c[4], c[1], c[2]] for c in cons for pr in pm.get(c[3], ()) if pr != c[0]]
    write_csv('edges_npm.csv', edges, ['src_repo', 'dst_repo', 'kind', 'package', 'range', 'evidence_file', 'line'])
    print('skywalking-ish npm deps:', [c for c in cons if 'skywalking' in c[3]], file=sys.stderr)
main()
