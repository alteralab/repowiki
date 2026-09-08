"""Infra/CI/text references between repos.
- declared:gitmodule   (.gitmodules url -> repo)
- infra:ci-ref         (.github/workflows: uses:/repository:/git clone of a sibling repo)
- infra:image          (docker-compose/helm values/Dockerfile FROM/Makefile image name -> repo that builds it)
- text:link            (README/docs/*.md links to a sibling repo)
Image->repo map is derived from Makefiles/workflows/Dockerfiles that build/tag/push the image (deterministic), and
falls back to the repo-name substring only when explicitly marked 'name-heuristic'."""
import re, os
from common import *
REPO_URL = re.compile(r'(?:https?://|git@)github\.com[:/]apache/(skywalking[\w-]*)(?:\.git)?')
SHORT = re.compile(r'(?<![\w/.-])apache/(skywalking[\w-]*)(?![\w-])')

def main():
    rs = set(repos())
    edges = []
    # 1. gitmodules
    for repo in rs:
        p = os.path.join(REPOS, repo, '.gitmodules')
        if os.path.exists(p):
            t = read_text(p)
            for m in re.finditer(r'^\s*url\s*=\s*(\S+)', t, re.M):
                mm = REPO_URL.search(m.group(1))
                tgt = mm.group(1) if mm else m.group(1)
                edges.append([repo, tgt, 'declared:gitmodule', m.group(1), '.gitmodules', line_of(t, m.start()), 'in-set' if tgt in rs else 'out-of-set'])
    # 2. images: who builds what
    builders = []  # (image, repo, file, line)
    IMG_BUILD = re.compile(r'(?:-t\s+|image[_ -]?name\s*[:=]\s*|IMAGE\s*[?:]?=\s*|images?:\s*\|?\s*)([\w./-]+(?:skywalking|oap|ui)[\w./-]*)', re.I)
    for repo in rs:
        for p in list(walk(repo, names={'Makefile', 'Makefile.in'})) + list(walk(repo, exts={'.yml', '.yaml'})):
            if '/.github/' not in p and not p.endswith(('Makefile', 'Makefile.in')): continue
            t = read_text(p)
            for m in re.finditer(r'(?:docker\s+(?:buildx\s+)?build[^\n]*?-t\s+|images:\s*\|?\s*\n?\s*|IMAGE_NAME\s*[:=]\s*|NAME\s*\?=\s*)([^\s"\']+)', t):
                builders.append([m.group(1), repo, rel(p), line_of(t, m.start())])
    write_csv('image_builders_raw.csv', builders, ['image_expr', 'repo', 'file', 'line'])
    # 3. image references + CI refs + text refs
    TXT_EXT = {'.md', '.adoc', '.txt', '.rst'}
    INFRA_EXT = {'.yml', '.yaml', '.tpl', '.env', '.in', '.mk', '.tf', '.json', '.properties'}
    for repo in rs:
        for p in walk(repo):
            ext = os.path.splitext(p)[1]; base = os.path.basename(p)
            is_ci = '/.github/' in p or base in ('.gitlab-ci.yml', 'Jenkinsfile')
            is_infra = ext in INFRA_EXT or base in ('Makefile', 'Makefile.in') or base.startswith('Dockerfile')
            is_txt = ext in TXT_EXT
            if not (is_ci or is_infra or is_txt): continue
            t = read_text(p)
            for m in REPO_URL.finditer(t):
                tgt = m.group(1)
                if tgt == repo: continue
                kind = 'infra:ci-ref' if is_ci else ('infra:ref' if is_infra else 'text:link')
                edges.append([repo, tgt, kind, m.group(0), rel(p), line_of(t, m.start()), 'in-set' if tgt in rs else 'out-of-set'])
            if is_ci:
                for m in re.finditer(r'^\s*(?:uses|repository):\s*(?:apache/)?(skywalking[\w-]*)', t, re.M):
                    tgt = m.group(1)
                    if tgt != repo: edges.append([repo, tgt, 'infra:ci-ref', m.group(0).strip(), rel(p), line_of(t, m.start()), 'in-set' if tgt in rs else 'out-of-set'])
            if is_infra or is_ci:
                for m in re.finditer(r'(?:image|repository|FROM|IMAGE\w*)\s*[:=]?\s*\??=?\s*["\']?((?:[\w.-]+/)*[\w.-]*skywalking[\w./-]*)(?::[\w.-]+)?', t):
                    img = m.group(1)
                    tgt = image_to_repo(img)
                    if tgt and tgt != repo:
                        edges.append([repo, tgt, 'infra:image', img, rel(p), line_of(t, m.start()), 'in-set' if tgt in rs else 'out-of-set'])
    write_csv('edges_infra.csv', edges, ['src_repo', 'dst_repo', 'kind', 'ref', 'evidence_file', 'line', 'resolution'])

# image -> producing repo: from verified build sites (see image_builders_raw.csv + manual confirmation in report)
IMAGE_MAP = {
    'apache/skywalking-oap-server': 'skywalking', 'skywalking/oap': 'skywalking', 'apache/skywalking/oap': 'skywalking',
    'apache/skywalking-ui': 'skywalking-horizon-ui', 'apache/skywalking-horizon-ui': 'skywalking-horizon-ui',  # helm values.yaml:195-208 says apache/skywalking-ui now ships Horizon UI
    'apache/skywalking/data-generator': 'skywalking', 'apache/skywalking-banyandb/banyandb': 'skywalking-banyandb',
    'skywalking-java': 'skywalking-java', 'apache/skywalking-java': 'skywalking-java', 'apache/skywalking-java/skywalking-java': 'skywalking-java',
    'apache/skywalking-satellite': 'skywalking-satellite', 'apache/skywalking-satellite/skywalking-satellite': 'skywalking-satellite',
    'apache/skywalking-rover': 'skywalking-rover', 'apache/skywalking-rover/skywalking-rover': 'skywalking-rover',
    'apache/skywalking-cli': 'skywalking-cli', 'apache/skywalking-banyandb': 'skywalking-banyandb', 'apache/skywalking-go/skywalking-go': 'skywalking-go',
    'apache/skywalking-python': 'skywalking-python', 'apache/skywalking-nodejs': 'skywalking-nodejs',
}
def image_to_repo(img):
    i = re.sub(r'^(ghcr\.io|docker\.io|skywalking\.docker\.scarf\.sh)/', '', img)
    i = i.rstrip('/')
    if i in IMAGE_MAP: return IMAGE_MAP[i]
    best = None
    for k, v in IMAGE_MAP.items():
        if (i.endswith('/' + k) or i.startswith(k + '/')) and (best is None or len(k) > len(best[0])): best = (k, v)
    return best[1] if best else None
main()
