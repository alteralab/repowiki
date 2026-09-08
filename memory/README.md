# memory/

큐레이션된 장기 운영 메모리. 거버넌스 정본은
[docs/policies/memory-governance.md](../docs/policies/memory-governance.md).

구획: `inbox/`(후보 대기) → `semantic/`(사실·도메인 지식) ·
`episodic/`(과거 실패·사례) · `procedural/`(지속 루틴) → `archive/`(대체됨).
`source-index/`는 소스·docs·evals·메모리 사이의 링크.

구획에 **직접 쓰지 않는다** — 모든 항목은 `inbox/` 경유로 승격 3문을 통과해야
들어온다.

여기 넣지 않는 것: 코드베이스 사실(→ repo-memory), 승인 정책(→ docs),
반복 실패(→ tests/evals regression), 대화 기록(버린다).
