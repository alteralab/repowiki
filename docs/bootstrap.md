# Phase 0 부트스트랩 절차

> 상태: 초안, 2026-09-08. 일회성 절차라 PLAN.md에 두지 않고 여기 둔다. macOS `sed` 문법(`-i ''`)에 묶여 있다.

리서치 파일과 PLAN.md가 이미 있어 `tpl_init.py`의 빈 디렉토리 가드에 걸린다. 순서는 이렇다.

```sh
mv ~/workspace/repowiki ~/workspace/_scratch/repowiki-pre-tpl
cd ~/workspace/agentic-project-tpl && scripts/tpl_init.py ~/workspace/repowiki repowiki
cd ~/workspace/repowiki
mkdir -p docs/reports
mv ~/workspace/_scratch/repowiki-pre-tpl/docs/research docs/reports/research
mv ~/workspace/_scratch/repowiki-pre-tpl/docs/bootstrap.md docs/bootstrap.md
mv ~/workspace/_scratch/repowiki-pre-tpl/PLAN.md PLAN.md
sed -i '' 's/^rev: HEAD.*/rev: rules-v0.10.0/' altera-rules.yml
printf '  - review\n' >> altera-rules.yml
sed -i '' 's#docs/research/#docs/reports/research/#g' PLAN.md
grep -n "docs/research" PLAN.md && echo "참조 갱신 누락" || echo "참조 갱신 완료"
```

이어서 Claude Code 세션에서:

1. `/rules-install` 실행 → `install_surfaces.py --check` 0건 확인 → `selftest.sh --census .` 결과를 읽고 `scripts/RUNLOG.md`에 기록.
2. `npm install --save-dev openwiki@0.5.0 && npx openwiki --init` → `git diff`로 `AGENTS.md`, `CLAUDE.md` 확인 → `CLAUDE.md`가 실파일이면 `ln -sf AGENTS.md CLAUDE.md`.
3. `SPEC.md`의 TODO를 PLAN §1과 §5로 채운다. 성공 기준은 §5 완료 판정과 1:1.
4. `scripts/gate_chain.sh` 첫 완주 결과를 RUNLOG에 남긴다.
