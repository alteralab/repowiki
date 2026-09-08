"""Research 17: the sample generator emits root-index links as `1-overview/index.md` (no `./`), which Fumadocs' createRelativeLink
does not resolve (research 13 row 10). Prefix `./` so the root page links resolve like every other page."""
import re, sys
f = sys.argv[1]; s = open(f, encoding="utf-8").read()
s2 = re.sub(r"\]\((?!\./|/|https?:)([^)]+index\.md)\)", r"](./\1)", s)
open(f, "w", encoding="utf-8").write(s2); print("root links prefixed:", len(re.findall(r"\]\(\./", s2)) - len(re.findall(r"\]\(\./", s)))
