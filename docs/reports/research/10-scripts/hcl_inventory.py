"""Parse every .tf under ROOT with python-hcl2; count top-level blocks, module sources,
resource types, data sources, providers, backend, remote_state. Writes module_graph.csv + mermaid."""
import sys, os, json, csv, collections, time
import hcl2
root = sys.argv[1]; out = sys.argv[2]
os.makedirs(out, exist_ok=True)
t0=time.time()
counts = collections.Counter(); res_types = collections.Counter(); data_types=collections.Counter()
providers=collections.Counter(); backends=collections.Counter(); failures=[]; nfiles=0
modules=[]  # (stack_dir, module_name, source)
remote=[]   # (stack_dir, name, backend, key)
variables=collections.Counter(); outputs=collections.Counter()
for dp, dn, fn in os.walk(root):
    if '.git' in dp or '.terraform' in dp: continue
    for f in fn:
        if not f.endswith('.tf'): continue
        p=os.path.join(dp,f); nfiles+=1
        try:
            with open(p) as fh: d=hcl2.load(fh)
        except Exception as e:
            failures.append((p, str(e).splitlines()[0][:120])); continue
        stack=os.path.relpath(dp, root)
        for k,v in d.items():
            counts[k]+=len(v) if isinstance(v,list) else 1
            if k=='resource':
                for r in v:
                    for rt in r: res_types[rt]+=1
            if k=='data':
                for r in v:
                    for dt,body in r.items():
                        data_types[dt]+=1
                        if dt=='terraform_remote_state':
                            for name,cfg in body.items():
                                remote.append((stack,name,cfg.get('backend'),json.dumps(cfg.get('config'))[:100]))
            if k=='provider':
                for r in v:
                    for pt in r: providers[pt]+=1
            if k=='terraform':
                for r in v:
                    for b in r.get('backend',[]) or []:
                        for bt in b: backends[bt]+=1
            if k=='module':
                for r in v:
                    for name,body in r.items():
                        modules.append((stack,name,body.get('source'),p))
            if k=='variable':
                for r in v: variables[stack]+=len(r)
            if k=='output':
                for r in v: outputs[stack]+=len(r)
dt=time.time()-t0
print(f"files={nfiles} parsed_ok={nfiles-len(failures)} failures={len(failures)} time={dt:.2f}s")
for f in failures: print("  FAIL", f)
print("top-level block counts:", dict(counts))
print("resource types (top 25):", res_types.most_common(25)); print("distinct resource types:", len(res_types))
print("data sources:", data_types.most_common()); print("providers:", providers.most_common())
print("backends:", backends.most_common()); print("remote_state:", remote)
print("variables per stack:", dict(variables)); print("outputs per stack:", dict(outputs))
with open(os.path.join(out,'module_graph.csv'),'w',newline='') as fh:
    w=csv.writer(fh); w.writerow(['stack_dir','module_name','source','source_kind','file'])
    for s,n,src,p in modules:
        kind='local' if isinstance(src,str) and src.startswith('.') else ('git' if isinstance(src,str) and ('git' in src or '::' in src) else 'registry')
        w.writerow([s,n,src,kind,os.path.relpath(p,root)])
with open(os.path.join(out,'module_graph.mmd'),'w') as fh:
    fh.write('flowchart LR\n')
    ids={}
    def nid(x):
        if x not in ids: ids[x]=f"n{len(ids)}"
        return ids[x]
    seen=set()
    for s,n,src,p in modules:
        e=(s,src)
        if e in seen: continue
        seen.add(e)
        fh.write(f'  {nid(s)}["{s}"] -->|module.{n}| {nid(str(src))}["{src}"]\n')
print("modules:", len(modules), "distinct sources:", len({m[2] for m in modules}))
srck=collections.Counter('local' if str(m[2]).startswith('.') else 'git/registry' for m in modules); print("source kinds:", dict(srck))
