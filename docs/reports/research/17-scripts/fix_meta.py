"""Research 17: drop the explicit "index" entry from every meta.json (Fumadocs uses a folder's index.md as the folder node itself;
listing it again produced a duplicate child whose href resolved to <folder>/index.md and prefetch 404s under research 13)."""
import json, glob, sys
root = sys.argv[1]
n = 0
for f in glob.glob(f"{root}/**/meta.json", recursive=True):
    d = json.load(open(f, encoding="utf-8"))
    if "index" in d.get("pages", []):
        d["pages"] = [p for p in d["pages"] if p != "index"]; json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1); n += 1
print("patched meta.json:", n)
