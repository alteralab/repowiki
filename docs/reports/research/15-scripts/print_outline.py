import json, sys
for l in sys.stdin:
    d = json.loads(l)
    def walk(items, ind=0):
        for it in items:
            r = it["range"]
            print(" " * ind + f"{it.get('role')}:{it.get('symbolType')} {it.get('name')} L{r['start']['line']+1}-L{r['end']['line']+1} sig={str(it.get('signature'))[:50]!r}")
            walk(it.get("members", []), ind + 2)
    walk(d["items"])
