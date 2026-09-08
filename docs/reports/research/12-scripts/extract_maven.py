"""Maven: produced coordinates (with parent inheritance) vs consumed <dependency> coordinates.
Evidence = file:line of the <artifactId> inside the <dependency> block. Properties resolved
from the pom + its in-repo parent chain (best effort, no build)."""
import re, os, sys, xml.etree.ElementTree as ET
from common import *

def strip_ns(root):
    for el in root.iter():
        if '}' in el.tag: el.tag = el.tag.split('}', 1)[1]
    return root

def parse_pom(p):
    try:
        root = strip_ns(ET.parse(p).getroot())
    except ET.ParseError as e:
        return None
    g = lambda tag, el=root: (el.findtext(tag) or '').strip()
    parent = root.find('parent')
    d = dict(path=p, groupId=g('groupId'), artifactId=g('artifactId'), version=g('version'),
             packaging=g('packaging') or 'jar', props={}, deps=[], parent=None)
    if parent is not None:
        d['parent'] = dict(groupId=g('groupId', parent), artifactId=g('artifactId', parent),
                           version=g('version', parent), relativePath=g('relativePath', parent) or '../pom.xml')
    props = root.find('properties')
    if props is not None:
        for el in props: d['props'][el.tag] = (el.text or '').strip()
    return d

def load_repo(repo):
    poms = {}
    for p in walk(repo, names={'pom.xml'}):
        d = parse_pom(p)
        if d: poms[p] = d
    # inherit groupId/version from in-repo parent (by relativePath, then by coordinates)
    by_coord = {}
    for d in poms.values():
        by_coord[(d['groupId'], d['artifactId'])] = d
    def resolve(d, depth=0):
        if depth > 10: return d
        par = d['parent']
        if not par: return d
        pp = os.path.normpath(os.path.join(os.path.dirname(d['path']), par['relativePath']))
        if os.path.isdir(pp): pp = os.path.join(pp, 'pom.xml')
        pd = poms.get(pp) or by_coord.get((par['groupId'], par['artifactId']))
        if pd:
            pd = resolve(pd, depth + 1)
            merged = dict(pd['props']); merged.update(d['props']); d['props'] = merged
        if not d['groupId']: d['groupId'] = par['groupId']
        if not d['version']: d['version'] = par['version']
        return d
    for d in poms.values(): resolve(d)
    return poms

PROP = re.compile(r'\$\{([^}]+)\}')
def subst(val, d):
    def rep(m):
        k = m.group(1)
        if k in ('project.version', 'pom.version', 'version'): return d['version']
        if k in ('project.groupId', 'pom.groupId'): return d['groupId']
        if k == 'project.parent.version' and d['parent']: return d['parent']['version']
        return d['props'].get(k, m.group(0))
    prev = None; cur = val
    for _ in range(5):
        if cur == prev: break
        prev, cur = cur, PROP.sub(rep, cur)
    return cur

DEP_BLOCK = re.compile(r'<dependency>(.*?)</dependency>', re.S)
TAG = lambda t, s: (re.search(rf'<{t}>\s*([^<]+?)\s*</{t}>', s) or [None, ''])[1]

def main():
    produced, consumed = [], []
    for repo in repos():
        poms = load_repo(repo)
        for p, d in poms.items():
            produced.append([repo, rel(p), d['groupId'], subst(d['version'], d), d['artifactId'], d['packaging']])
            text = read_text(p)
            for m in DEP_BLOCK.finditer(text):
                blk = m.group(1)
                gid, aid, ver = TAG('groupId', blk), TAG('artifactId', blk), TAG('version', blk)
                scope = TAG('scope', blk); typ = TAG('type', blk)
                # section: dependencyManagement vs dependencies
                before = text[:m.start()]
                in_dm = before.rfind('<dependencyManagement>') > before.rfind('</dependencyManagement>')
                line = line_of(text, m.start()) + blk[:blk.find('<artifactId>')].count('\n')
                consumed.append([repo, rel(p), line, subst(gid, d), aid, ver, subst(ver, d), scope, typ,
                                 'dependencyManagement' if in_dm else 'dependencies'])
    write_csv('maven_produced.csv', produced, ['repo', 'pom', 'groupId', 'version', 'artifactId', 'packaging'])
    write_csv('maven_consumed.csv', consumed, ['repo', 'pom', 'line', 'groupId', 'artifactId', 'version_raw', 'version_resolved', 'scope', 'type', 'section'])
    # cross-repo join
    prod = {}
    for r in produced: prod.setdefault((r[2], r[4]), set()).add((r[0], r[3]))
    edges = []
    for c in consumed:
        key = (c[3], c[4])
        for (prepo, pver) in prod.get(key, ()):
            if prepo != c[0]:
                drift = '' if not c[6] or c[6] == pver else f'consumer={c[6]} producer_head={pver}'
                edges.append([c[0], prepo, 'artifact:maven', f'{key[0]}:{key[1]}', c[6], pver, drift, c[1], c[2], c[9]])
    write_csv('edges_maven.csv', edges, ['src_repo', 'dst_repo', 'kind', 'coordinate', 'consumer_version', 'producer_head_version', 'version_drift', 'evidence_file', 'line', 'section'])
    # unresolved: org.apache.skywalking deps not produced by any cloned repo
    unres = [c for c in consumed if c[3].startswith('org.apache.skywalking') and (c[3], c[4]) not in prod]
    write_csv('maven_unresolved_internal.csv', unres, ['repo', 'pom', 'line', 'groupId', 'artifactId', 'version_raw', 'version_resolved', 'scope', 'type', 'section'])
main()
