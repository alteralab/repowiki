"""Build a k8s object graph from rendered manifests (helm template output or plain manifests).
Nodes: kind/namespace/name. Edges: Service.selector->workload labels, Ingress->Service,
workload env/envFrom/volumes -> ConfigMap/Secret, workload -> ServiceAccount, HPA -> target, image -> registry.
Usage: k8s_graph.py <dir-of-yaml> <outdir>"""
import sys, os, yaml, csv, collections
src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
objs=[]; bad=0
for f in sorted(os.listdir(src)):
    if not f.endswith('.yaml'): continue
    chart=f[:-5]
    with open(os.path.join(src,f)) as fh:
        try:
            for d in yaml.safe_load_all(fh):
                if isinstance(d,dict) and 'kind' in d: d['_chart']=chart; objs.append(d)
        except yaml.YAMLError as e: bad+=1; print('YAML error', f, str(e)[:80])
def nid(o): return f"{o['kind']}/{o.get('metadata',{}).get('name')}"
kinds=collections.Counter(o['kind'] for o in objs)
by_kind=collections.defaultdict(list)
for o in objs: by_kind[o['kind']].append(o)
edges=[]; images=set()
WORKLOADS={'Deployment','StatefulSet','DaemonSet','Job','CronJob'}
def pod_spec(o):
    s=o.get('spec',{}) or {}
    if o['kind']=='CronJob': s=s.get('jobTemplate',{}).get('spec',{})
    return (s.get('template',{}) or {}).get('spec',{}) or {}
def pod_labels(o):
    s=o.get('spec',{}) or {}
    if o['kind']=='CronJob': s=s.get('jobTemplate',{}).get('spec',{})
    return ((s.get('template',{}) or {}).get('metadata',{}) or {}).get('labels',{}) or {}
for o in objs:
    k=o['kind']; me=nid(o); chart=o['_chart']
    if k=='Service':
        sel=(o.get('spec',{}) or {}).get('selector') or {}
        if sel:
            for w in objs:
                if w['kind'] in WORKLOADS and w['_chart']==chart and all(pod_labels(w).get(a)==b for a,b in sel.items()):
                    edges.append((chart,me,'selects',nid(w)))
    if k=='Ingress':
        for r in (o.get('spec',{}) or {}).get('rules',[]) or []:
            for p in ((r.get('http') or {}).get('paths') or []):
                b=p.get('backend',{}); sname=(b.get('service') or {}).get('name') or b.get('serviceName')
                if sname: edges.append((chart,me,f"routes[{r.get('host','*')}]",f"Service/{sname}"))
    if k in WORKLOADS:
        ps=pod_spec(o)
        sa=ps.get('serviceAccountName')
        if sa: edges.append((chart,me,'runsAs',f"ServiceAccount/{sa}"))
        for c in (ps.get('containers') or [])+(ps.get('initContainers') or []):
            if c.get('image'): images.add((chart,me,c['image'])); edges.append((chart,me,'image',f"image:{c['image']}"))
            for e in c.get('env') or []:
                vf=e.get('valueFrom') or {}
                if 'configMapKeyRef' in vf: edges.append((chart,me,'env<-CM',f"ConfigMap/{vf['configMapKeyRef']['name']}"))
                if 'secretKeyRef' in vf: edges.append((chart,me,'env<-Secret',f"Secret/{vf['secretKeyRef']['name']}"))
            for ef in c.get('envFrom') or []:
                if 'configMapRef' in ef: edges.append((chart,me,'envFrom',f"ConfigMap/{ef['configMapRef']['name']}"))
                if 'secretRef' in ef: edges.append((chart,me,'envFrom',f"Secret/{ef['secretRef']['name']}"))
        for v in ps.get('volumes') or []:
            if 'configMap' in v: edges.append((chart,me,'mounts',f"ConfigMap/{v['configMap']['name']}"))
            if 'secret' in v: edges.append((chart,me,'mounts',f"Secret/{v['secret']['secretName']}"))
            if 'persistentVolumeClaim' in v: edges.append((chart,me,'mounts',f"PersistentVolumeClaim/{v['persistentVolumeClaim']['claimName']}"))
    if k=='HorizontalPodAutoscaler':
        t=(o.get('spec',{}) or {}).get('scaleTargetRef',{})
        edges.append((chart,me,'scales',f"{t.get('kind')}/{t.get('name')}"))
    if k in ('RoleBinding','ClusterRoleBinding'):
        rr=o.get('roleRef',{}); edges.append((chart,me,'grants',f"{rr.get('kind')}/{rr.get('name')}"))
        for s in o.get('subjects') or []:
            if s.get('kind')=='ServiceAccount': edges.append((chart,me,'to',f"ServiceAccount/{s.get('name')}"))
known={nid(o) for o in objs}
dangling=[e for e in edges if not e[3].startswith('image:') and e[3] not in known]
with open(os.path.join(out,'nodes.csv'),'w',newline='') as fh:
    w=csv.writer(fh); w.writerow(['chart','kind','name','namespace']); 
    for o in objs: w.writerow([o['_chart'],o['kind'],o.get('metadata',{}).get('name'),o.get('metadata',{}).get('namespace')])
with open(os.path.join(out,'edges.csv'),'w',newline='') as fh:
    w=csv.writer(fh); w.writerow(['chart','src','rel','dst']); w.writerows(edges)
regs=collections.Counter(i.split('/')[0] if '/' in i and ('.' in i.split('/')[0] or ':' in i.split('/')[0]) else 'docker.io' for _,_,i in images)
with open(os.path.join(out,'images.csv'),'w',newline='') as fh:
    w=csv.writer(fh); w.writerow(['chart','workload','image']); w.writerows(sorted(images))
# mermaid for one chart
target=sys.argv[3] if len(sys.argv)>3 else None
with open(os.path.join(out,'graph.mmd'),'w') as fh:
    fh.write('flowchart LR\n'); ids={}
    def m(x):
        if x not in ids: ids[x]=f"n{len(ids)}"
        return ids[x]
    for c,s,r,d in edges:
        if target and c!=target: continue
        if d.startswith('image:'): continue
        fh.write(f'  {m(s)}["{s}"] -->|{r}| {m(d)}["{d}"]\n')
print(f"objects={len(objs)} yaml_errors={bad} kinds={dict(kinds)}")
print(f"edges={len(edges)} by rel={dict(collections.Counter(e[2].split('[')[0] for e in edges))}")
print(f"dangling(refs to objects not in chart)={len(dangling)} e.g. {dangling[:6]}")
print(f"images={len(images)} registries={dict(regs)}")
