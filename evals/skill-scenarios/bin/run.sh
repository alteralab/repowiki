#!/usr/bin/env bash
# 조회 스킬의 시나리오 eval 러너. 시나리오마다 격리된 작업 디렉터리를 만들어 Claude Code 를
# 비대화(-p)로 돌리고 트레이스와 답을 남긴다. 채점은 grade.py 가 트레이스에서 한다.
#
# 시나리오 규약(altera-skills evals 와 같다): scenarios/<스킬>-<이름>/{scenario.md, prompt.txt,
# skill-sets.yaml, context/}. context/ 는 디렉터리째 작업 디렉터리에 놓인다 — 위키는 디렉터리라
# 파일을 납작하게 옮기면 쪽 사이 링크가 죽는다. 스킬은 `.claude/skills/repowiki` 로 놓아
# 사람이 쓰는 배치와 같게 발견되게 한다.
#
# 사용: run.sh <출력 디렉터리> [--model <id>] [시나리오 이름 ...]   (이름이 없으면 전부)
#
# 한계: Bash 를 허용하므로 에이전트의 명령 범위를 작업 디렉터리로 가두지 못한다. 픽스처는
# 이 저장소가 만든 파일뿐이라 감수한다. 픽스처에 남의 글을 넣을 때는 이 점을 다시 본다.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../../.." && pwd)
out=${1:?출력 디렉터리}; shift || true
model=""
if [ "${1:-}" = "--model" ]; then model=${2:?모델 id}; shift 2; fi
skill="$root/src/repowiki/data/skills/repowiki"
mkdir -p "$out"
out=$(cd "$out" && pwd)   # 작업 디렉터리를 옮겨 실행하므로 절대 경로여야 한다
names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  for d in "$here"/../scenarios/*/; do names+=("$(basename "$d")"); done
fi
for name in "${names[@]}"; do
  scen="$here/../scenarios/$name"
  [ -f "$scen/prompt.txt" ] || { printf '시나리오가 없다: %s\n' "$name" >&2; exit 2; }
  run="$out/$name"
  [ ! -e "$run" ] || { printf '이미 있는 실행 디렉터리다: %s\n' "$run" >&2; exit 2; }
  mkdir -p "$run"
  ws=$(mktemp -d "${TMPDIR:-/tmp}/repowiki-eval-XXXXXX")
  cp -R "$scen/context/." "$ws/"
  # 배치는 번들과 같다: `<out>/skills/repowiki` 와 `<out>/wiki`. 그래야 스크립트의 기본 위키
  # 자리가 성립한다. Claude Code 가 스킬을 찾는 자리(`.claude/skills`)에는 링크만 둔다.
  mkdir -p "$ws/skills" "$ws/.claude/skills"; cp -R "$skill" "$ws/skills/repowiki"
  ln -s ../../skills/repowiki "$ws/.claude/skills/repowiki"
  prompt=$(cat "$scen/prompt.txt")
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  model_args=(); [ -z "$model" ] || model_args=(--model "$model")
  # 도구는 시나리오가 쓰는 것만 허용한다. Bash 는 스킬의 스크립트 때문에 필요하다.
  if ! (cd "$ws" && claude -p "$prompt" --output-format stream-json --verbose "${model_args[@]}" \
      --allowedTools "Read,Glob,Grep,Bash,Skill" --max-turns 30 > "$run/trace.jsonl" 2> "$run/stderr.txt"); then
    printf 'claude 실행 실패: %s (stderr: %s)\n' "$name" "$run/stderr.txt" >&2; exit 1
  fi
  python3 - "$run" "$name" "$started" <<'PY'
import json, sys, pathlib
run, name, started = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
result = {}
for line in (run / "trace.jsonl").read_text(encoding="utf-8").splitlines():
    try: obj = json.loads(line)
    except ValueError: continue
    if obj.get("type") == "result": result = obj
if not result or result.get("is_error"):
    raise SystemExit(f"{name}: 결과 이벤트가 없거나 오류다: {json.dumps(result, ensure_ascii=False)[:300]}")
(run / "output.md").write_text(str(result.get("result", "")), encoding="utf-8")
meta = {"scenario": name, "started": started, "model": None, "turns": result.get("num_turns"),
        "cost_usd": result.get("total_cost_usd"), "duration_ms": result.get("duration_ms"), "is_error": result.get("is_error")}
for line in (run / "trace.jsonl").read_text(encoding="utf-8").splitlines():
    try: obj = json.loads(line)
    except ValueError: continue
    if obj.get("type") == "system" and obj.get("model"): meta["model"] = obj["model"]; break
(run / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{name}: turns={meta['turns']} cost={meta['cost_usd']} model={meta['model']} error={meta['is_error']}")
PY
  rm -rf "$ws"
done
