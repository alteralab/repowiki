import re
from dockerfile_parse import DockerfileParser

HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")

def parse_with_heredoc(text: str):
    """Fold heredoc bodies into the owning instruction so dockerfile-parse sees one instruction.
    Returns dockerfile-parse structure whose startline/endline still index the ORIGINAL lines."""
    lines = text.split("\n")
    folded, origin = [], []      # origin[i] = (first_orig_line, last_orig_line) of folded line i
    i = 0
    while i < len(lines):
        line = lines[i]
        m = HEREDOC.search(line)
        if m and not line.lstrip().startswith("#"):
            end = m.group(1)
            j = i + 1
            while j < len(lines) and lines[j].strip() != end:
                j += 1
            body = " ".join(l.strip() for l in lines[i + 1:j])
            folded.append(line.replace(m.group(0), "").rstrip() + " " + body)
            origin.append((i, j)); i = j + 1
        else:
            folded.append(line); origin.append((i, i)); i += 1
    p = DockerfileParser()
    p.content = "\n".join(folded)
    out = []
    for s in p.structure:
        s = dict(s)
        s["startline"] = origin[s["startline"]][0]
        s["endline"] = origin[s["endline"]][1]
        out.append(s)
    return out

if __name__ == "__main__":
    for s in parse_with_heredoc(open("sample/Dockerfile").read()):
        print(f"{s['instruction']:5} L{s['startline']+1}-L{s['endline']+1} value={s['value'][:45]!r}")
