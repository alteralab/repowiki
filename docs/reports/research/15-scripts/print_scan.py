import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
for r in sorted(rows, key=lambda r: (r['file'], r['range']['start']['line'], r['range']['start']['column'])):
    mv = r.get('metaVariables', {}).get('single', {}).get('NAME')
    name = mv['text'] if mv else r['text'].split('\n')[0][:40]
    print(f"{r['file'].split('/')[-1]:18} {r['message']:14} {name:22} L{r['range']['start']['line']+1}-L{r['range']['end']['line']+1}")
