# Codex 3차 리뷰 (PLAN 5판, 2026-09-09) — 원문

## 이전 발견 처리 표

Codex could not locate the 18 prior findings verbatim in the repo — no separate review artifact exists, so it reconstructed the list from PLAN.md's own change summary and diffs against PLAN-v4.md, marking every row **[reconstructed]**.

| # | 심각도 | 발견 요약 | 상태 | 5판 근거 | 남은 최소 변경 |
|---|---|---|---|---|---|
| 1 | 치명 | air-gap에서 LLM으로 새 위키 생성 가능한 것처럼 기술 | resolved | §1 L47, Phase 5 L272 | 없음 |
| 2 | 치명 | 타입/호출 채택 게이트 불충분 | partial | §2.3 L112 | 타입 관계 골든셋·precision/recall 하한 명시 |
| 3 | 치명 | 증분 무효화 계약이 열려 있음 | partial | §2.9 L190–203 | `UpdateWindow`/모델·effort/토큰 보정 등 누락 입력 포함, N 정의 |
| 4 | 중요 | `SystemFlow` 생성/실패 표현 불명확 | partial | §2.3 L122, §2.8 L185 | Hop 자료형·join 알고리즘 정의 |
| 5 | 중요 | Phase 6 기준 정성적 | partial | Phase 6 L273 | 표본 추출법·정답 집합·판정 규칙 |
| 6 | 중요 | SERVING/Pages 범위 혼재 | resolved | §0 L8, §1 L41–42, §11 L332 | (신규 발견 참조) |
| 7 | 중요 | 이전 판 상속 문구로 자립성 훼손 | unresolved | §7 L302 "이전 판과 같은 사유" 잔존 | 기각 사유 직접 기재 |
| 8 | 중요 | mutation ≥9/10만 요구 | partial | §2.9 L205, Phase 4 L271 (12/12로 강화) | coverage matrix, waste 산식 |
| 9 | 중요 | 오케스트레이터 재개 안전성 미검증 | resolved | §2.1 L81, Phase 0 L266 | 없음 |
| 10 | 중요 | 사이트 생성기 확정처럼 설계에 반영 | resolved | §0 L22, §3 L236 | 없음 |
| 11 | 중요 | 정적 사이트 로컬 사용 조건 부재 | resolved | §1 L37, Phase 4 L271 | 없음 |
| 12 | 중요 | 사람 평가 표본/검토자 미정의 | partial | §5 L262 | Phase별 rubric·seed 연결 |
| 13 | 중요 | 이력 오라클 불일치·재현 조건 없음 | partial | §2.9 L209 (4판에 있던 기본값 삭제됨) | code-maat 기본값·공식 복원 |
| 14 | 사소 | outline 판정이 개수 동수라 identity 오류 미검출 | resolved | §2.7 L178 | 없음 |
| 15 | 사소 | language-pack ABI 문제로 P-C 훼손 | resolved | §2.7 L176, §8 L317/320 | 없음 |
| 16 | 사소 | jproperties 줄 번호 미제공 | resolved | §2.7 L174 | 없음 |
| 17 | 사소 | kustomize 버전/오프라인 미고정 | resolved | §2.7 L172, §8 L317 | 없음 |
| 18 | 사소 | 다이어그램 가독성 한도 임의적 | partial | §2.5 L155–157 | 측정 도구/브라우저 고정 |

## 신규 발견

**치명**
1. Phase 6 필수 흐름 `helm→image→repo`가 §2.8의 `SystemFlow` class ≤3 제약과 모순 — config/infra는 class 4로 분류되어 문서 자체 규칙상 생성 불가능한 내부 모순.
2. `PageInput`(§2.9)이 "닫힌 목록"이라 주장하지만 `UpdateWindow`, MR 설명, 모델/effort, calibration 등 실제 출력에 영향을 주는 입력이 스키마에서 빠져 있어 무효화 정확성을 보장하지 못함.

**중요**
1. 12-case mutation oracle이 11개 계약 항목 × add/change/delete/rename을 다 덮지 못하고 waste 산식도 미정.
2. `SystemFlow`/`Hop` 자료형이 열거되지 않아 구현자마다 다르게 구현 가능.
3. Phase 6 수치 기준(≥30, ≥9/10, 100% 등)에 표본 추출법과 판정 규칙이 없어 재현 불가.
4. 타입 관계 채택 게이트의 "일치" 정의(precision/recall/Jaccard 등) 불명.
5. 여러 Phase 성공 기준(10시드 안정, ±1%p 등)이 여전히 threshold/fixture 미연결.
6. §7에 "이전 판과 같은 사유" 문구가 남아 자립 문서 주장과 모순.
7. code-maat 기본값(`--min-revs 5` 등)이 4판에서 5판으로 오면서 삭제되어 재현 불가.
8. frontmatter 필드별 타입/enum이 §2.4에 명시되지 않아 SPEC 원천 역할 불완전.

**사소**
1. GitLab Pages/서빙 언급이 비목표 문장으로는 남아 있어 "전면 제거" 요구와 문자적으로 어긋남(다만 모두 명시적 범위 배제).
2. `layout: elk` 폴백이 채택 생성기의 ELK 지원 여부를 선가정.
3. V-REC-1 관점 미검증 미래형 표현 3곳 잔존(표제 relocation, 보정표 확정 표현, graph.json capability 주장).
4. `PageInput`의 두 "상위 N"(FileRank/History)이 동일 값인지 불명.
5. P-C 봉인이 텍스트상 네트워크 의존은 없으나 smoke test 명령/환경변수가 구체화되지 않아 완전 입증은 Phase 5 구현에 의존.

## 종합 판정
5판은 air-gap 범위 축소, 최신 문법 휠/kustomize/MCP/2026년 모델 반영 등으로 대체로 2026-current하고 과도한 설계는 아니나, `SystemFlow` class 제약과 Phase 6 필수 흐름의 정면 모순, 닫히지 않은 `PageInput`, 불충분한 mutation oracle이 SPEC의 핵심 성공 조건을 흔들어 **현재 상태로는 SPEC.md 성공 기준 원천으로 승인할 준비가 되지 않았다**는 것이 Codex의 판정입니다.

Note: Codex found no separate artifact preserving the original 18 findings verbatim (PLAN.md and docs/plan-history/PLAN-v4.md were the only sources), so the table above is reconstructed rather than verified against an original list.
