---
name: repo-memory-maintenance
description: openwiki로 repo-memory(코드베이스 지식)를 생성·갱신하는 절차. AGENTS.md/CLAUDE.md 심링크 보호와 생성물 손편집 금지 포함.
---

# repo-memory-maintenance

## 언제 쓰는가

- `repo-memory/quickstart.md`가 없을 때 (첫 생성).
- 소스 수준 이해가 바뀌는 변경을 병합했을 때 (갱신).
- repo-memory 내용이 현재 코드와 어긋나는 것을 발견했을 때.

## 프로세스

1. **첫 생성**: Node.js 22+ 확인(`.nvmrc`) → `npm install --save-dev openwiki`
   (프로젝트 로컬 — `package-lock.json`이 버전을 고정하며 커밋 대상) →
   `openwiki/INSTRUCTIONS.md`가 요구되면 범위 브리프를 사람과 함께 작성 →
   `npx openwiki --init`. 출력은 저장소 루트 `openwiki/`(= `repo-memory` 심링크
   대상)에 생긴다.
2. **--init/--update 직후 반드시**: openwiki는 루트 `AGENTS.md`·`CLAUDE.md`에
   위키 포인터를 써넣는다. `git diff`로 확인하고 —
   - `CLAUDE.md`가 실파일로 바뀌었으면 내용을 `AGENTS.md`에 병합하고
     `ln -sf AGENTS.md CLAUDE.md`로 심링크를 복구한다.
   - `AGENTS.md`에 추가된 포인터는 "먼저 읽기" 절과 중복되지 않게 정리한다.
3. **갱신**: `npx openwiki --update`. 변경분을 훑어 명백히 틀린 명제가 있으면
   소스를 확인한다 — 틀렸으면 `INSTRUCTIONS.md`를 고치거나 이슈로 남기고
   재생성한다.
4. 명제의 근거가 의심되면 `openwiki/.claims/`의 앵커(repo://경로#줄)로 소스를
   직접 연다. 앵커가 가리키는 곳에 그 명제의 근거가 없으면 그 페이지를 믿지
   않는다.

## 입력과 출력

- 입력: 현재 저장소 상태.
- 출력: 갱신된 `openwiki/` (OKF v0.2 번들 — frontmatter type·generated·sources·
  verified·status), `.last-update.json`.

## 경고 신호 (red flags)

- openwiki 출력물을 손으로 고치고 있다 — 생성 계층이다. 다음 --update가
  덮는다. 고칠 것은 소스나 INSTRUCTIONS.md다.
- repo-memory의 명제를 `.claims` 확인 없이 구현 결정의 근거로 쓰고 있다.
- CLAUDE.md 심링크가 깨진 채 여러 커밋이 지나갔다.

## 검증

- `repo-memory/quickstart.md`가 열리고 현재 HEAD와 `.last-update.json`이
  맞물리는가.
- `CLAUDE.md`가 심링크인가 (`ls -la CLAUDE.md`).

## 거부할 흔한 합리화

- "한 줄만 고치면 되는데 재생성은 과하다" — 손편집 한 줄이 생성 계층의 신뢰
  전체를 깬다. 어느 명제가 손 것인지 아무도 모르게 된다.
- "위키가 그렇다고 하니 맞을 것이다" — 생성물은 검증할 단서이지 사실이
  아니다. 근거는 .claims 앵커 끝의 소스다.
