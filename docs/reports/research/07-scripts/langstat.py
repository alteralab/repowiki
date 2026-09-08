#!/usr/bin/env python3
"""Walk a repo; count files/lines/chars/tokens by language, test vs main split, big files, non-utf8, symlinks."""
import os, sys, json, time
from collections import defaultdict

EXT = {
 '.java':'Java','.scala':'Scala','.kt':'Kotlin','.groovy':'Groovy','.py':'Python','.pyi':'Python',
 '.ts':'TypeScript','.tsx':'TypeScript','.js':'JavaScript','.jsx':'JavaScript','.mjs':'JavaScript','.cjs':'JavaScript',
 '.go':'Go','.rs':'Rust','.c':'C','.h':'C','.cpp':'C++','.cc':'C++','.hpp':'C++','.cs':'C#',
 '.sh':'Shell','.bash':'Shell','.zsh':'Shell','.bat':'Batch','.ps1':'PowerShell',
 '.xml':'XML','.pom':'XML','.yaml':'YAML','.yml':'YAML','.json':'JSON','.toml':'TOML','.properties':'Properties','.ini':'INI','.cfg':'INI',
 '.md':'Markdown','.rst':'reST','.txt':'Text','.adoc':'AsciiDoc','.html':'HTML','.htm':'HTML','.css':'CSS','.scss':'CSS',
 '.sql':'SQL','.proto':'Protobuf','.thrift':'Thrift','.avsc':'JSON','.gradle':'Gradle','.kts':'Kotlin',
 '.dockerfile':'Dockerfile','.j2':'Jinja','.jinja':'Jinja','.jinja2':'Jinja','.svg':'SVG','.csv':'CSV','.tsv':'CSV',
 '.ipynb':'Notebook','.puml':'PlantUML','.mdx':'Markdown','.vm':'Velocity','.ftl':'Freemarker','.tpl':'Template',
}
NAMES = {'Dockerfile':'Dockerfile','Makefile':'Makefile','pom.xml':'XML','build.gradle':'Gradle','settings.gradle':'Gradle'}
SOURCE = {'Java','Scala','Kotlin','Groovy','Python','TypeScript','JavaScript','Go','Rust','C','C++','C#','Shell','SQL','Protobuf','Gradle','Jinja'}
SKIP_DIRS = {'.git','node_modules','.venv','venv','__pycache__','target','build','dist','.gradle','.idea','vendor','third_party','thirdparty','.mypy_cache','.pytest_cache','.tox','out','_build'}
TEST_MARKERS = ('/test/','/tests/','/testing/','/src/test','/it/','/integration-tests/','/integration_tests/','/e2e/','/__tests__/','/test_utils/','/testkit/','/tests_')

def is_test(rel):
    r='/'+rel
    if any(m in r for m in TEST_MARKERS): return True
    b=os.path.basename(rel)
    return b.startswith('test_') or b.endswith('_test.py') or b.endswith('Test.java') or b.endswith('Tests.java') or b.endswith('IT.java') or b.endswith('.test.ts') or b.endswith('.test.tsx') or b.endswith('.spec.ts') or b.endswith('Spec.scala') or b.endswith('Test.scala')

def lang_of(path):
    b=os.path.basename(path)
    if b in NAMES: return NAMES[b]
    e=os.path.splitext(b)[1].lower()
    return EXT.get(e)

def main(root):
    t0=time.time()
    stats=defaultdict(lambda: {'files':0,'lines':0,'chars':0,'test_files':0,'test_lines':0,'main_lines':0})
    big=[]; nonutf8=[]; symlinks=0; total_files=0; unknown=defaultdict(int); dir_sizes=defaultdict(int)
    for dp,dns,fns in os.walk(root):
        dns[:]=[d for d in dns if d not in SKIP_DIRS]
        for f in fns:
            p=os.path.join(dp,f); rel=os.path.relpath(p,root)
            if os.path.islink(p): symlinks+=1; continue
            total_files+=1
            try: sz=os.path.getsize(p)
            except OSError: continue
            top=rel.split('/')[0]; dir_sizes[top]+=sz
            if sz>1_000_000: big.append((sz,rel))
            L=lang_of(p)
            if not L:
                unknown[os.path.splitext(f)[1].lower() or f]+=1; continue
            try:
                data=open(p,'rb').read()
            except OSError: continue
            try: txt=data.decode('utf-8')
            except UnicodeDecodeError:
                nonutf8.append(rel); txt=data.decode('latin-1')
            n=txt.count('\n')+(1 if txt and not txt.endswith('\n') else 0)
            s=stats[L]; s['files']+=1; s['lines']+=n; s['chars']+=len(txt)
            if is_test(rel): s['test_files']+=1; s['test_lines']+=n
            else: s['main_lines']+=n
    out={'root':root,'seconds':round(time.time()-t0,1),'total_files':total_files,'symlinks':symlinks,
         'langs':dict(sorted(stats.items(),key=lambda kv:-kv[1]['lines'])),
         'source_chars':sum(v['chars'] for k,v in stats.items() if k in SOURCE),
         'source_lines':sum(v['lines'] for k,v in stats.items() if k in SOURCE),
         'all_text_chars':sum(v['chars'] for v in stats.values()),
         'big_files':sorted(big,reverse=True)[:15],'nonutf8':nonutf8[:20],'nonutf8_count':len(nonutf8),
         'unknown_ext_top':sorted(unknown.items(),key=lambda kv:-kv[1])[:12],
         'top_dirs_by_bytes':sorted(dir_sizes.items(),key=lambda kv:-kv[1])[:12]}
    out['source_tokens_est']=out['source_chars']//4
    out['all_text_tokens_est']=out['all_text_chars']//4
    print(json.dumps(out,indent=1))
if __name__=='__main__': main(sys.argv[1])
