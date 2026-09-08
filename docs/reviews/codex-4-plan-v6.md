# Codex 4차 리뷰 (PLAN 6판, 2026-09-09) — 원문

## 처리 표

| ID | 원 내용 요약 | 상태 | 6판 근거(섹션) | 잔여 조치 |
|---|---|---|---|---|
| V5-C1 / 이전-4·5 | `SystemFlow` class ≤3 제약과 Phase 6의 class-4 `helm→image→repo` 흐름 모순 | partial | §2.3은 빌드 지점 기반 class-4 image 엣지를 허용하고 §2.8은 세 대표 흐름을 명시해 class 모순은 해소. 그러나 join이 모든 대상에 "같은 key의 `EntryPoint`"를 요구한다. 이미지 key와 코드 `EntryPoint` key가 같다는 계약은 없다 | image 홉은 `EntryPoint`가 아니라 이미지를 생산하는 `Container`/build site에서 종결하거나 image 전용 join 규칙 |
| V5-C2 / 이전-3 | `PageInput`에 MR, 모델·effort, calibration 등 누락 | partial | §2.9 12–14 추가, N=20 명시. 그러나 슬라이스 경계와 canonical serialization 미정의 | 페이지 종류별 slice closure와 canonical 직렬화/해시 규칙 |
| V5-I1 / 이전-8 | mutation oracle 커버리지와 waste 산식 | partial | 14 항목 × 4 연산 행렬, 24건, waste 산식, Phase 4 24/24 정정. 그러나 9 범주 × 4 연산 = 36칸과 "24건"의 관계가 설명되지 않음 | 24개 case ID와 (입력 항목, 연산) 셀 열거 |
| V5-I2 / 이전-4 | `Hop` 자료형과 join 부재 | partial | `Hop{...}`와 join 절차 추가. image 홉 동일-key 조건 미해결(C1과 같은 원인) | boundary kind별 terminal/matching 규칙 분리 |
| V5-I3 / 이전-5·12 | Phase 6 표본과 판정 규칙 | partial | 층화 무작위 10, seed, 검토자 2인, 제3자, 전수 검토 명시. "링크백 100%"의 분모 없음 | 링크백 대상 = resolved edge/flow endpoint |
| V5-I4 / 이전-2 | 타입 관계 "일치" 정의 | resolved | Jaccard ≥0.95, 100개 precision ≥0.98, 해석률 ≥0.90 | §3 요약 행 불일치는 신규 발견 |
| V5-I5 / 이전-12·18 | fixture·threshold 불완전 | partial | Phase 1 정답 자료와 ARI ≥0.9, Phase 2 리서치 07 기준값, §2.5 ELK. Phase 4 "연속 갱신 3회 일치", "대화형 페이지 렌더"의 exact 조건 없음 | `changes/` 비교 필드와 대화형 페이지 DOM assertion |
| V5-I6 / 이전-7 | "이전 판과 같은 사유" | resolved | §7 각 사유 직접 기재 | 없음 |
| V5-I7 / 이전-13 | code-maat 기본값 | resolved | §2.9 기본값과 공식과 입력 형식 | 없음 |
| V5-I8 | frontmatter 타입/enum | resolved | §2.4 enum과 타입 | `index.md`/`log.md` 예외 명시(신규) |
| V5-M1 / 이전-6 | 서빙 문구 반복 | unresolved | §1, §7, §11, §13에 범위 배제 문장 반복 | §1 정본, 나머지 참조 |
| V5-M2 / 이전-18 | ELK 선가정 | resolved | MkDocs Material custom JS ELK 로더 | 없음 |
| V5-M3 | V-REC-1 미래 표현 | partial | calibration 정본 명시. "Phase 0 뒤 docs/reports/research/"와 §11 "graph.json에서 만들 수 있으나"는 미래·미검증 표현 | relocation을 Phase 0 완료 항목으로, D2 capability 근거 또는 삭제 |
| V5-M4 / 이전-3 | 상위 N | resolved | N=20 | 없음 |
| V5-M5 | P-C 명령·환경 | resolved | Phase 5 명령과 환경 변수, §8 자산 | `network_calls: 0`은 자기보고, 보조 증거 |

## 신규 발견

### 치명
- **Image `SystemFlow`의 종점 조건이 충족 불가능** (§2.3, §2.8, Phase 6): 공통 join이 "같은 key의 `EntryPoint`"를 요구하나 image coordinate와 코드 entrypoint가 같은 key를 갖는 모델이 없다. → image boundary는 `Container{image, built_by}` 또는 build site에 연결하면 종료되는 2-hop deployment flow로 정의.

### 중요
- 24-case 행렬 기수 불일치(9 × 4 = 36 vs 24) → M01–M24 열거, 각 case에 (입력 항목, 연산, fixture, 재생성 페이지).
- `PageInput` hash의 canonical form 미정의 → canonical JSON, 정규화, 정렬 key, 해시 알고리즘.
- §3 타입 게이트 행이 §2.3보다 약함 → "§2.3 세 조건 전부"로 통일.
- Phase 6 링크백 100%의 분모 없음 → resolved edge/flow endpoint 집합.

### 사소
- `diagram-limits.yml`이 `PageInput` 9와 14에 중복 → 9는 analyzer/prompt만.
- frontmatter 적용 대상에 `index.md`/`log.md` 예외 미명시.
- 서빙/Pages 문면 반복 → §1 정본.

## 판정
**아니오.** 6판은 5판 문제 대부분을 해소했으나, 단일 차단 항목은 `SystemFlow`의 image join이 동일-key `EntryPoint`를 요구해 Phase 6 필수 `helm→image→repo` 흐름을 계약상 resolved로 만들 수 없다는 점이다. boundary-kind별 종점 규칙만 닫히면 나머지는 fixture와 명세 정밀도 보완 수준이다.
