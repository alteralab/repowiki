"""Config-level shared string literals across repos: docker image names, host:port / URL endpoints,
SW_* env var names, Kafka topic literals. Reports tokens present in >=2 repos with evidence (first 3 spans per repo)."""
import re, os, json, subprocess
from common import *
CFG_EXT = {'.yml', '.yaml', '.env', '.properties', '.in', '.tpl', '.conf', '.toml', '.json', '.sh', '.mk'}
PATTERNS = {
    'endpoint': re.compile(r'(?<![\w./-])((?:https?|grpc)://[\w.-]+(?::\d+)?|\b(?:oap|skywalking-oap|satellite|banyandb|ui|skywalking-ui|elasticsearch|kafka|zookeeper)[\w-]*:\d{2,5})(?![\w-])'),
    'envvar': re.compile(r'\b(SW_[A-Z0-9_]{3,})\b'),
    'topic': re.compile(r'(?<![\w-])(skywalking-(?:segments|metrics|profilings|managements|meters|logs|json-logs|log|trace|segment)[\w-]*)(?![\w-])'),
}
def main():
    hits = {}  # (kind, token) -> repo -> [(file,line)]
    for repo in repos():
        for p in walk(repo):
            ext = os.path.splitext(p)[1]; base = os.path.basename(p)
            if not (ext in CFG_EXT or base in ('Makefile', 'Makefile.in') or base.startswith('Dockerfile') or base.startswith('.env')): continue
            if '/test/' in p or '/e2e' in p: continue  # exclude test fixtures for the config layer
            t = read_text(p)
            for kind, rx in PATTERNS.items():
                for m in rx.finditer(t):
                    hits.setdefault((kind, m.group(1)), {}).setdefault(repo, []).append((rel(p), line_of(t, m.start())))
    rows = []
    for (kind, tok), per in sorted(hits.items()):
        if len(per) >= 2:
            for repo, spans in per.items():
                rows.append([kind, tok, len(per), repo, len(spans), ';'.join(f'{f}:{l}' for f, l in spans[:3])])
    write_csv('shared_strings.csv', rows, ['kind', 'token', 'n_repos', 'repo', 'n_hits', 'evidence'])
    # Java/Go string literals via ast-grep (topic-like literals) — code layer, includes tests flagged
    rule = os.path.join(os.path.dirname(__file__), 'sg_topic_literal.yml')
    lits = []
    for repo in repos():
        for lang, exts in (('java', '.java'), ('go', '.go')):
            r = subprocess.run(['ast-grep', 'scan', '--rule', rule, '--json', os.path.join(REPOS, repo)], capture_output=True, text=True)
            try: js = json.loads(r.stdout or '[]')
            except Exception: js = []
            for h in js:
                if not h['file'].endswith(exts): continue
                ft = read_text(h['file'])
                role = 'producer' if re.search(r'KafkaProducer|ProducerRecord|\.send\(|Sender|Reporter|producer', ft) else ('consumer' if re.search(r'KafkaConsumer|@KafkaListener|\.subscribe\(|Fetcher|Consumer|consumer', ft) else 'unknown')
                lits.append([repo, h['text'].strip('"`'), rel(h['file']), h['range']['start']['line'] + 1, 'test' if '/test' in h['file'] else 'main', role])
            break  # ast-grep scan handles both langs in one call
    write_csv('code_string_literals.csv', lits, ['repo', 'literal', 'file', 'line', 'scope', 'role'])
main()
