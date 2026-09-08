"""GraphQL: schema (Query/Mutation root fields) defined in *.graphqls vs operations used by clients
(.graphql files in skywalking-cli, gql template strings in booster-ui .ts). Edge = contract:graphql-field."""
import re, os
from common import *
ROOT_FIELD = re.compile(r'(?:extend\s+)?type\s+(Query|Mutation)\s*\{(.*?)\}', re.S)
def main():
    schema = {}  # field -> [(repo, path, line, root)]
    for repo in repos():
        for p in walk(repo, exts={'.graphqls'}):
            t = read_text(p)
            for m in ROOT_FIELD.finditer(t):
                body = m.group(2)
                for fm in re.finditer(r'^\s*(\w+)\s*(?:\(|:)', body, re.M):
                    schema.setdefault(fm.group(1), []).append((repo, rel(p), line_of(t, m.start(2) + fm.start()), m.group(1)))
    write_csv('graphql_schema_fields.csv', [[f, r, p, l, root] for f, v in schema.items() for (r, p, l, root) in v], ['field', 'repo', 'path', 'line', 'root'])
    # client operations: top-level selection fields in query/mutation operations
    OP = re.compile(r'\b(query|mutation)\s+\w*\s*(?:\([^)]*\))?\s*\{')
    uses = []
    for repo in repos():
        for p in list(walk(repo, exts={'.graphql'})) + list(walk(repo, exts={'.ts', '.js', '.vue'})):
            t = read_text(p)
            for m in OP.finditer(t):
                # walk braces to collect top-level fields
                i = m.end(); depth = 1; buf = ''
                while i < len(t) and depth:
                    c = t[i]
                    if c == '{': depth += 1
                    elif c == '}': depth -= 1
                    if depth == 1: buf += c
                    i += 1
                for fm in re.finditer(r'(?:^|[\s,{])(?:\w+\s*:\s*)?(\w+)\s*(?:\(|\{|$|\s)', buf, re.M):
                    f = fm.group(1)
                    if f in ('query', 'mutation', 'fragment', 'on'): continue
                    uses.append([repo, rel(p), line_of(t, m.start()), m.group(1), f])
    # booster-ui style: src/graphql/fragments/*.ts -> `export const X = { variable: "...", query: `field(args) {...}` }`
    for repo in repos():
        for p in walk(repo, exts={'.ts'}):
            if '/graphql/' not in p: continue
            t = read_text(p)
            for m in re.finditer(r'query:\s*`\s*(\w+)\s*[({]', t):
                uses.append([repo, rel(p), line_of(t, m.start()), 'query', m.group(1)])
    # dedupe
    uses = sorted({tuple(u) for u in uses})
    edges = []; unmatched = []
    for u in uses:
        hits = [s for s in schema.get(u[4], []) if s[0] != u[0]]
        if hits:
            for s in hits: edges.append([u[0], s[0], 'contract:graphql-field', u[4], u[1], u[2], s[1], s[2]])
        else: unmatched.append(list(u))
    write_csv('edges_graphql.csv', edges, ['src_repo', 'dst_repo', 'kind', 'field', 'evidence_file', 'line', 'schema_file', 'schema_line'])
    write_csv('graphql_unmatched_ops.csv', unmatched, ['repo', 'file', 'line', 'op', 'field'])
main()
