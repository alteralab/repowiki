#!/usr/bin/env python3
"""Module-level import dependency edges. usage: depedges.py <repo> <mode> <out.csv>
mode=java-maven: module = top-level dir containing a pom.xml (or nested for dubbo: 2 levels); resolve import pkg -> module by scanning package decls.
mode=java-gradle: module = top-level dir listed in settings.gradle.
mode=python: module = top-level dir (airflow-core, providers/<x>, task-sdk...); resolve 'airflow.providers.x' -> providers/x, 'airflow.' -> airflow-core, 'airflow.sdk' -> task-sdk.
"""
import os,re,sys,csv,time,collections
root,mode,out=sys.argv[1],sys.argv[2],sys.argv[3]
t0=time.time()
SKIP={'.git','node_modules','build','target','.venv'}
def walk(ext):
    for dp,dns,fns in os.walk(root):
        dns[:]=[d for d in dns if d not in SKIP]
        for f in fns:
            if f.endswith(ext): yield os.path.join(dp,f)
edges=collections.Counter(); files=0; unresolved=0; total_imports=0
if mode.startswith('java'):
    # module of a file: for gradle -> first path component; for maven -> longest prefix dir with pom.xml among first two components
    def module_of(rel):
        parts=rel.split('/')
        if mode=='java-gradle': return parts[0]
        if len(parts)>2 and os.path.exists(os.path.join(root,parts[0],parts[1],'pom.xml')) and parts[0] in ('dubbo-plugin','dubbo-spring-boot-project','dubbo-demo','dubbo-distribution'):
            return parts[0]+'/'+parts[1]
        return parts[0]
    pkg2mod={}  # package -> module (from main sources only)
    srcs=[]
    for p in list(walk('.java'))+list(walk('.scala')):
        rel=os.path.relpath(p,root); files+=1
        try: txt=open(p,encoding='utf-8',errors='replace').read()
        except OSError: continue
        m=re.search(r'^\s*package\s+([\w.]+)',txt,re.M)
        pkg=m.group(1) if m else ''
        mod=module_of(rel)
        if '/src/test/' not in rel and pkg: pkg2mod.setdefault(pkg,mod)
        srcs.append((rel,mod,pkg,txt))
    def resolve(imp):
        # strip class / static / wildcard
        parts=imp.split('.')
        for i in range(len(parts),0,-1):
            cand='.'.join(parts[:i])
            if cand in pkg2mod: return pkg2mod[cand]
        return None
    for rel,mod,pkg,txt in srcs:
        if '/src/test/' in rel: continue
        for imp in re.findall(r'^\s*import\s+(?:static\s+)?([\w.]+)',txt,re.M):
            total_imports+=1
            if not imp.startswith(('org.apache.kafka','kafka.','org.apache.dubbo','org.apache.commons')): continue
            tgt=resolve(imp)
            if tgt is None: unresolved+=1; continue
            if tgt!=mod: edges[(mod,tgt)]+=1
elif mode=='python':
    def module_of(rel):
        parts=rel.split('/')
        if parts[0]=='providers': return 'providers/'+('/'.join(parts[1:3]) if parts[1] in ('apache','common','microsoft','atlassian','dbt','cncf') and len(parts)>2 else parts[1])
        return parts[0]
    provs=set()
    for d in os.listdir(os.path.join(root,'providers')):
        if os.path.isdir(os.path.join(root,'providers',d)):
            sub=os.path.join(root,'providers',d)
            if d in ('apache','common','microsoft','atlassian','dbt','cncf'):
                for s in os.listdir(sub):
                    if os.path.isdir(os.path.join(sub,s)): provs.add(d+'/'+s)
            else: provs.add(d)
    def resolve(imp):
        if imp.startswith('airflow.providers.'):
            p=imp.split('.')[2:5]
            for k in (2,1):
                c='/'.join(p[:k])
                if c in provs: return 'providers/'+c
            return None
        if imp.startswith('airflow.sdk'): return 'task-sdk'
        if imp.startswith('airflowctl'): return 'airflow-ctl'
        if imp.startswith('airflow_breeze'): return 'dev/breeze'
        if imp.startswith('airflow_shared'): return 'shared'
        if imp.startswith('airflow.'): return 'airflow-core'
        if imp.startswith('tests_common'): return 'devel-common'
        return None
    for p in walk('.py'):
        rel=os.path.relpath(p,root); files+=1
        if '/tests/' in rel or rel.startswith('tests') or '/test_' in rel: continue
        mod=module_of(rel)
        try: txt=open(p,encoding='utf-8',errors='replace').read()
        except OSError: continue
        for imp in re.findall(r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))',txt,re.M):
            imp=imp[0] or imp[1]; total_imports+=1
            if not imp.startswith(('airflow','tests_common')): continue
            tgt=resolve(imp)
            if tgt is None: unresolved+=1; continue
            if tgt!=mod: edges[(mod,tgt)]+=1
with open(out,'w',newline='') as f:
    w=csv.writer(f); w.writerow(['src_module','dst_module','import_count'])
    for (a,b),n in edges.most_common(): w.writerow([a,b,n])
print(f"{root} mode={mode} files={files} imports={total_imports} unresolved_internal={unresolved} edges={len(edges)} secs={time.time()-t0:.1f}")
for (a,b),n in edges.most_common(12): print(f"  {a} -> {b}: {n}")
