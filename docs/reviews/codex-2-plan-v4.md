# Codex 2차 리뷰 (PLAN 4판, 2026-09-09) — 원문 요지

## 치명
1. §0/§3/§5/§8 + v3 §5 + research 08: 완전 air-gap에서 핵심 위키 생성 경로가 성립하지 않는다. `count_tokens`는 네트워크이고 P-C는 결정층·재생만 실행한다. → 완전 차단 프로파일의 입력을 로컬 checkout/tar로 정의하고 LLM 경로를 핀·동봉해 새 위키 생성까지 시험하거나, "런타임 완전 air-gap 지원"을 주장하지 말고 P-C가 결정층·재생 시험임을 명시. `count_tokens` 불가 시 보정표+p95 로컬 게이트로 결정적 전환.
2. §0/§2.3/§3/§5 + audit 14 #3c/#3d: 타입/호출 결합 채택 게이트가 감사 판정을 절반만 반영(타입 ≥0.95 조건과 resolved field/param type이 빠지고 호출 정밀도만 남음, recall·언어별 coverage·실패 시 대체 경로 없음). → 타입과 호출 판정 분리, recall/coverage 하한, 미달 시 제공·제외 엣지와 흐름 페이지 한계 표기.
3. §2.9/§5 + v3 §1/§2.3/§2.9: 증분 재실행 정확성의 명세와 오라클이 없다(`PageInput` 구성 미정, 역의존 전파 규칙 없음, 9/10은 누락 1건 허용). → `PageInput` 완전 목록과 역의존 전파 규칙, 삭제·rename·모듈 이동·공유 타입·랭킹·분석기/프롬프트 판·교차 레포 계약 변화의 mutation oracle, 필수 집합 10/10, 불필요 재생성 별도 상한.

## 중요
1. 감사에서 제거한 의존성(language-pack, jproperties)이 정본 레지스트리 핀 목록에 남아 있음. → 락 목록에서 제거, 문법 휠 7종과 `tags.scm` SHA 등재.
2. 동봉 네이티브 자산 목록이 실제(ast-grep, tree-sitter, tiktoken, kiwipiepy, tfparse, cbm, sigma/ELK)보다 훨씬 작음. → "LangGraph 추가 휠 4종"으로 한정, 플랫폼별 전체 manifest + smoke test.
3. 조건부 임베딩(KURE-v2/bge-m3) 모델 동봉 계약 부재. → revision·checksum·cache·offline 환경변수·빈 캐시 `--network=none` 시험.
4. Helm/kustomize/kubectl 핀이 모순되고 "확인 후 핀"은 미래 조건절. → Helm 4.2.4 + kustomize 5.8.1로 고정.
5. LangGraph 판정 규칙이 §0·감사·Phase 0에서 다름. → 시나리오별 필수 불변조건·비교 지표·동률 규칙 한 표.
6. 다이어그램 실험에 행동을 정하는 임계값 없음. → 허용 교차 수·라벨 잘림·이해도 하한 사전 등록, `ELK → 분할 → 표+대화형` 결정 순서.
7. 사이트가 잠정인데 상속 본문은 MkDocs를 확정 사실로 취급. → 상속 예외 명시, 고유명사를 "채택 생성기"로.
8. 교차 레포 "관계"는 있으나 교차 레포 실행 흐름 추적이 완료 기준에 없음. → `SystemFlow`와 미해결 홉, SkyWalking 대표 흐름 hop별 span 정확도.
9. 인용 A/B와 맵 모델 선택이 비용 우선. → invalid citation 0과 근거 지지/완전성을 pass/fail로, 비용은 tie-breaker.
10. 완료 기준 일부가 측정 불가(오라클 불일치 시 정답, "흐름 ≥5", 표본 수·검토자·rubric 부재). → 고정 fixture·표본·독립 검토자·rubric·허용오차, 흐름은 hop별 precision.
11. GPL 0건 기준의 범위 불명(LGPL 허용, 테스트 오라클 GPL, pygit2 linking exception). → 산출물별 라이선스 정책과 SPDX 기준.

## 사소
1. GitLab Mermaid "19.4+ = 11.16.1" 근거 부족 → [unverified].
2. Mermaid 50블록 게이트가 Phase 1 완료 조건에 빠짐.
3. `outline` 비교가 개수 동수만 봄 → identity precision/recall, Scala 별도.
4. FTS5 사전 실험에 채택/기각 규칙 없음.
5. `llms-full.txt` 2 MB 초과 분할의 탐색 계약 없음.

## 확인했고 타당함
Mermaid 11 + 2,000자/50블록 + ELK 조건부; 15/25 재측정과 대화형 페이지; PageRank authority + reverse/HITS + RRF; networkx Leiden 제거와 Louvain/scikit-network; git 옵션 정리와 code-maat/codelore; PyYAML compose_all, HCL parses_to_tree, Dockerfile span, properties 파서; MCP CLI+SKILL 우선 + mcp 2.2.0; `.netrc` 제거; hanlint 강등; GraphQL 읽기/REST 쓰기; tiktoken 캐시 동봉; OKF 프로필과 `verified`/`stale_after`; copyleft 테스트 전용 분리.

## 종합
감사 14의 도구 교체는 대체로 반영돼 incumbent bias는 줄었으나, 완전 차단 LLM 경로, 타입/호출·교차 흐름 게이트, 증분 무효화 계약이 남아 "2026-current하고 목적에 비례한 실행 계획"으로 승인하기 어렵다.
