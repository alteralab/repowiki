---
status: 조사 완료 (2026-09-08) — 저장소 정독 + 웹. 근거 등급 A(심사·대규모) B(프리프린트·공개 코퍼스) C(큐레이션 관찰) D(의견). [unverified] 표기 항목은 미확인
scope: 생성 위키 산문의 "사람이 읽는 글" 규범 — fluent-korean 정체, slop 도구 지형, 한국어 결정적 검사, 근거 등급
---

# Prose style: fluent-korean, AI-slop tooling, Korean deterministic checks, evidence

## (A) fluent-korean 판정
**실재한다. Claude Code output-style 플러그인(프롬프트 전용)이며 린터도 번역투·AI투 제거기도 아니다.**

| 항목 | 값 |
|---|---|
| Repo | https://github.com/snflkd/fluent-korean |
| 종류 | 플러그인 안의 output-style 2종(`fluent-korean`, `fluent-korean-not-coding`). 실행물·검사기·훅·테스트 없음 |
| 저자 | GitHub `snflkd`; README: 국어국문학 전공자가 손으로 씀 |
| 라이선스/별 | MIT; 1,189★ (2026-07-10 생성, 2026-08-23 push) |
| 배포 | GitHub만(npm·PyPI 없음). `/plugin marketplace add snflkd/fluent-korean` → `/plugin install` → `/config`에서 output-style 선택 |
| 목표 | "수려한 문체보다는 확실한 의미 전달" — 조사·어미 탈락, 전보식 명사 나열, 비유어 치환 같은 **깨진 기계 한국어**를 고친다 |
| 명시적 비목표 | README: "번역체 교정, AI 표현 최소화, 맞춤법 오류 제거와 같은 skill을 원하신다면 im-not-ai, korean-skills, korean-humanizer를 참조" |

인용 조항(`plugins/fluent-korean/output-styles/fluent-korean.md`):
- 범위: "인용, 코드, 코드 주석에는 이 지침들을 적용하지 않습니다." "변수명과 주석, 커밋 메시지, 로그 문자열처럼 코드에 속하는 텍스트는 프로젝트의 기존 관례를 준수" "고유 명사와 기술 용어 등은, 통상적인 용례로 정착된 번역어 혹은 음차가 있다면 우선적으로 사용하고, 그렇지 않다면 원어를 유지"
- 문장: "의미가 있는 문장 성분을 생략하지 않습니다 … 관형격 조사인 '~의'를 필요 이상으로 사용한다면 … 유의" (예 `사본의 문구는 작업의 상황을 → 사본에 기재된 문구는 작업이 진행되는 상황을`); "(헤더와 목록에는 강제로 적용되는 사항이 아닙니다.) 명사구나 부사구, 연결어미로 문장을 끝내지 말고, 서술어와 종결어미를 사용하여 완성된 형태의 문장으로"
- 구: "필수적인 경우가 아니라면 조사와 어미를 생략하지 말아야 합니다. 또한 부사, 보조사와 선어말어미, 보조 용언을 적극적으로 활용"; "맥락에 적합한 한자어를 적극적으로 활용하고, 그 한자어에 조사와 어미를 붙여서"; "꼭 필요한 경우가 아니라면 비유적 어휘로 일반적인 명사나 동사를 대체하지 않습니다" (예 `분석의 흐름 → 분석의 방향성`, `코드로 박는 자리 → 코드에 명시하는 상황`); "엠대시(—)는 앞뒤 문장의 관계를 지나치게 함축하기 때문에 자제하고, 문맥과 형식에 따라 콜론이나 접속사로 대체"
- 선택 조항: 통용 어휘 우선("사용 빈도가 낮아서 통용되지 않는 어휘를 사용하면 소통의 효율성이 오히려 낮아지니 자제"), 출력 직전 자기 점검.
- 저자 단서(README 유의점): "생각보다 원하는 만큼 동작하지 않을 수 있습니다 … 지침 자체를 수정하기보다는 … 하네스를 구성 및 최적화" — 저자 스스로 검증 층을 권한다.

파생·근접 도구:
| Repo | 무엇 | ★/라이선스 | 결정적? |
|---|---|---|---|
| cwJohnPark/enhanced-korean | fluent-korean 포크 + **`kolint`**(정규식 Python) + 훅(`Stop` 재작성, `PostToolUse` md 린트, `SessionStart` 재주입). KO001 개조식 명사형 종결, KO002 서술어 없는 명사 종결, KO003 연결어미 종결, KO004 엠대시, KO005 '의' 연쇄, KO006 조사 빠진 명사 연쇄, KO007 비유·구어 어휘, KO008 높임 불일치, KO009 영어 문장 | 0 / MIT | 예(정규식) |
| epoko77-ai/im-not-ai | "Humanize KR" v2.3.2. 10 범주 × 70 패턴, LLM 재작성 + Python 게이트(`metrics_v2.py`: 이중피동, `에 의해`, 대명사 밀도, `들` 과용, 관형절 중첩, 이중 조사, `~고 있다`, 대구 `가 아니라`, 종결 다양성, TTR; `verify_change_rate.py` 30% warn/50% stop). 코퍼스 연구 있음(D) | 5,325 / MIT | 혼합 |
| eddmpython/hanlint | **순수 결정적 한국어 산문 린터**(Markdown). `pip install hanlint`/`npx hanlint`, 의존 0, Python·JS 동일 출력. 규칙: translationese, cliche, doublePassive, nounPile, euiChain, longSentence, endingRepeat, connectorRepeat, fillerOpener, danglingDeixis, dash, doubleNegative, japaneseLoan, hardWord, emojiBullet, headingSkip/Uniform, loneSubheading, sectionNoProse, paraFragment, spacing/spelling. exit 1; `hanlint baseline`; GitHub Action; pre-commit; 자기 규정 "좋은 글인지는 판정하지 않는다 … 세면 확정되는 결함만" | 1 / MIT(+국립국어원 어휘 공공누리 1유형, KLUE CC BY-SA) | 예 |
| DaleSeo/korean-skills | humanizer + grammar-checker 스킬(프롬프트) | 191 / MIT | 아니오 |
| sage724/Jieun_Korean_mal | 13 정규식 번역투 검사 | 0 / MIT | 예 |
| IsaacEryn/humanizer-ko, nathankim0/humanize-korean, pi/codex 포트 | 프롬프트 | 소수 | 아니오 |
| kiwipiepy 0.23.2 | 형태소 분석(LGPL-3) — XSV·보조용언 태그로 피동·명사화 검출 가능 | 401 / LGPL | 라이브러리 |
| hanspell/py-hanspell | Daum/Naver 비공식 엔드포인트 — 깨지기 쉬움 | MIT | 취약 |

## (B) 도구 비교
| Tool | 종류 | 한국어 | CI | 라이선스 |
|---|---|---|---|---|
| fluent-korean | 프롬프트(output-style) | 예 | 아니오 | MIT |
| enhanced-korean/kolint | 프롬프트+정규식+훅 | 예 | 예 | MIT |
| im-not-ai | LLM 재작성 + Python 게이트 | 예 | 부분 | MIT |
| hanlint | 결정적 린터 | 예 | 예(Action, pre-commit, baseline) | MIT |
| blader/humanizer v3.0.0 | LLM 스킬(25 패턴, Wikipedia "Signs of AI writing" 기반; **Anthropic 것 아님**, Siqi Chen) 45,156★ | 영어 예시 | 아니오 | MIT |
| stop-slop / skill-deslop / deslop-text | LLM 스킬 | 아니오 | 아니오 | MIT |
| Vale | 결정적(YAML, regexp2 RE2+lookaround); 기본 `\b`가 ASCII라 한글은 `nonword: true` 필요, 한국어 스타일 패키지 없음 **[CJK 미검증]** | 조건부 | 예(공식 Action) | MIT |
| Vale styles Google/Microsoft/write-good/proselint/alex | 결정적 | 영어만 | 예 | MIT/BSD |
| textlint | 프레임워크, `--mcp` 모드; **한국어 프리셋 없음**; 일본어 `@textlint-ja/textlint-rule-preset-ai-writing`(1,121★)이 이식 모델 | 아니오 | 예 | MIT |
| AI 탐지기(KatFishNet 등) | 분류기 | 예 | — | — |
탐지 ≠ 품질: Wikipedia 페이지 자체가 탐지기 오류율·사람의 우연 수준 판별을 적는다.

humanizer 25 패턴 요지: (A) not-X-but-Y, 한 줄 결어, 격언, 도입 연출("Let's dive in"), 가상의 반론; (B) 3항 나열, 반복 문두, 대시(하드 룰 "no em dashes"), 한정어 중첩, 하이픈 쌍, 피동·주어 생략; (C) 과용 어휘 25개(delve, meticulous, intricate, pivotal, robust, tapestry, testament, underscore…), 의미 과장, 막연한 연관, -ing 부가절, 판매 언어, 권위 차용, is/are 회피("serves as"); (D) 장식 볼드·볼드 라벨 불릿, 장식 헤딩·이모지·수평선, 곱슬 따옴표; (E) 챗봇 잔재, 지식 한계 고지, 헤딩 반복 첫 문장. "Word habits change with every model release. The structural habits above persist."

## (C) 두 층 권고
원칙: **구조 신호는 모델 세대를 넘어 지속하고, 단어 목록은 소멸한다.** 구조는 프롬프트에, 셀 수 있는 것은 린터에, 빈도 규칙을 금지로 바꾸지 않는다.

### Layer 1 — 프롬프트 제약 (한국어)
문장 형태(fluent-korean, kolint): 본문 문장은 서술어+종결어미로 끝낸다(헤더·표·목록 예외); 조사·어미 생략 금지, 명사 3개 이상 조사 없이 잇지 않기; `~의` 한 문장 2회 이상 연쇄 금지; 문장 길이 섞기(문단마다 짧은 문장 1~2개 + 100자 안팎 긴 문장 1개), 같은 종결어미 4문장 연속 금지, 문서 전체 한 문체.
번역투(빈도, 금지 아님): 이중 피동 금지; `~에 의해` 피동 → 행위자 주어; `~에 있어서`→`~에서`, `~을 필요로 한다`→`~이 필요하다`, `~을 가지고 있다`→`~이 있다`, `가장 ~한 것 중 하나` 금지; `~에 대해`, `~를 통해`, `~할 수 있다`, `~을 위해`는 문단당 2회까지(전면 금지 안 함: 사람이 더 쓴다); 문두 대명사 대신 명사 반복; `당신/여러분` 금지; 관형절 3어절 이상 쌓이면 분할.
AI 관용구·구조: `A가 아니라 B`/`단순한 X를 넘어 Y` 문서당 1회 이하(가장 강한 실측 신호 9.2×); 도입구(`다음은 ~입니다`, `크게 세 가지로`) 삭제; 분열문(`핵심은 ~이다`) 삭제; 결산구(`결론적으로`, `요약하면`, `시사하는 바가 크다`) 삭제, 절 끝 요약 문장 금지, 마지막 문장은 구체적 사실; 문두 접속사 문단 2회 이하; hype 어휘 대신 수치·동작; 연결어미 뒤 쉼표 금지(KatFish 4.8×); 헤딩 반복 첫 문장 금지.
서식: 이모지 금지; 볼드는 UI 요소·경고 라벨만; `- **라벨:** 설명` 불릿은 대응 관계 있을 때만, 3연속 불릿 블록 금지; 엠대시 금지(콜론·쉼표·괄호·접속사); 헤딩은 명사구, 레벨 건너뛰기 금지; 사용자에게 말 걸지 않기.
어휘: 정착 번역어/음차 우선, 없으면 원어, 영어 병기 첫 등장만; 비유·구어 동사(`박다/얹다/치우다/훑다/갈아엎다`) 대신 일반 동사; 코드·식별자·경로·인용은 손대지 않는다.
운영: 출력 직전 자기 점검 조항; 컨텍스트 압축 후 재주입(enhanced-korean `SessionStart` 훅이 그 이유로 존재).

### Layer 1 — 영어
humanizer §1–5 + §12/13/18/19/20/22/24 하드 룰; Google/Microsoft 톤(2인칭, 능동, 현재, sentence-case, "you can" 삭제); 소규모 금지어(delve, meticulous, intricate, pivotal, crucial, robust(비유), seamless, leverage, showcase, underscore, testament, landscape, tapestry, "plays a key role", "serves as", "stands as", "In conclusion", "Overall,", "It's important to note"); 절은 마지막 구체 사실로 끝내고 요약 문단 없음; 챗봇 잔재·컷오프 고지 없음.

### Layer 2 — 결정적 사후 검사
- 한국어: **hanlint**를 CI 게이트로(버전 핀, `src/hanlint/data/*` 사전 검토; 1★·2026-08-27 생성·단일 유지자). 대안 `kolint.py`(단일 파일). GitHub Action: `uses: eddmpython/hanlint@main`, `errors-only: "true"`.
- 사용자 정의 정규식: **error** = `되어지|돼지(?=[다게고])`, `[을를] 필요로 (하|한|합|해)`, `아무리 강조해도 지나치지 않`, 코드 밖 `[—–]`, 이모지 범위, `^\s*-\s*\*\*[^*]+\*\*\s*:`(절당 계수), `(?:^|\n)(?:다음은|다음과 같습니다|크게 .{1,6} 가지로)`, 분열문 `(?:핵심|관건|중요한 것|필요한 것)은 .{0,40}(?:이다|입니다)\.`, 결산구, 연결어미 뒤 쉼표(문서당 6+), 본문 문장의 `(?:함|됨|임)\.?$`. **warn**(문단당 ≥3) = `에 대해서?|에 대한`, `[을를] 통해`, `할 수 있(?:다|습니다)`, `[을를] 위해`, `에 있어서?`, `로 인해`, `에도 불구하고`, 문두 `또한|따라서|즉|나아가|아울러|게다가`. `(?:가|이) 아니라` 문서당 ≥2 flag. `에 대해`/`통해`/`것이다`는 자동 수정 금지.
- 선택: kiwipiepy로 `XSV+EP` 피동 중첩·`NNG NNG NNG` 연쇄 검출 **[미시제품]**.
- 영어: **Vale** + Google 스타일 + 사용자 `AIslop` 스타일(Vocab existence error; NotButY `\bnot (?:just|only|merely) [^.]{1,60}, but\b` warning; EmDash `—` error). 한글에는 Vale 대신 hanlint/Python.
- textlint `--mcp`(AI 쓰기→린트→수정 루프)와 일본어 ai-writing 프리셋은 한국어 포팅 템플릿.
- **충실성 게이트**(im-not-ai·hanlint guard): 다듬기 후 초안과 diff — 숫자·코드 span·식별자·링크·인용문 변경 시 실패, 문자 변경률 30% 초과 실패.

### 사람 리뷰에 남기는 것
모호·잘못된 지시 대상(정규식 밖); 레지스터·과잉 존댓말(일관성 검사 외 도구 없음); 헤지 적절성(`~로 보인다`는 불확실한 아키텍처 명제에 옳다; im-not-ai는 헤지→단정 변환 금지); 불릿이 진짜 구조 데이터인지; 강한 개인 문체의 오탐(Pebblous: ChatGPT 이전 사람 원고가 연결어미 쉼표만으로 6/6 고위험) — **error는 결함, warn은 빈도**.

## (D) 근거 등급
| 주장 | 근거 | 등급 |
|---|---|---|
| delve/showcasing/underscores/crucial/intricate/meticulously/pivotal 급증 | Kobak et al., Science Advances 2025, PubMed 15M+ 초록, ≥13.5% LLM 처리; 문체어이지 내용어 아님 https://arxiv.org/abs/2406.07016 | A |
| commendable 9.8×, meticulous 34.7×, intricate 11.2×; 개별 귀속은 불신뢰, 사람 판별 "barely exceeds random" | Liang et al., ICML 2024 https://arxiv.org/abs/2403.07183 | A (영어 학술) |
| AI 텍스트: 더 격식·명사·한정사, 낮은 어휘 다양성, 반복 | Terčon & Dobrovoljc 서베이 arXiv 2510.05136 | A- |
| 한국어 LLM 텍스트: **띄어쓰기·POS 다양성·쉼표** 차이; KatFishNet +19.78% AUROC | Park et al., ACL 2025 https://aclanthology.org/2025.acl-long.1030/ | A (한국어) |
| 한국어 전문가는 LLM 에세이를 학생보다 높이 평가; 학생이 이기는 것은 "자연스러운 한국어 표현" | Park & Han arXiv 2601.19913 (n 작음) | B |
| 사람은 AI 텍스트를 우연 수준으로 판별 | Jakesch et al., PNAS 2023 | A |
| 한국어: `A가 아니라 B` 9.2×, 쉼표 1.5×, `~한다` 집중 1.8×, **100자+ 문장 부재**(AI 8.1 vs 사람 91.3/1k) | im-not-ai 코퍼스 2026-07(AI 60 vs 2022 이전 사설 60, G²) https://github.com/epoko77-ai/im-not-ai/blob/main/docs/en/evidence.md | B |
| **AI 표지 아님**: `~를 통해`(사람 2×), `것이다`(사람 2×) | 같은 연구; 최희경 2016 [2차, 미확인] | B / C |
| 연결어미 뒤 쉼표 4.8×(19.83% vs 4.10%); 개인 저자 오탐 | Pebblous 2026-08 https://blog.pebblous.ai/report/korean-ai-humanizer-teardown-2026-08/en/ | B- |
| 한국어 판별력 있는 자질: 통사 피동 `-아/어 지다`, `-에 의하여`, 2·3인칭 대명사, 의존명사 `것/때문` | 김혜영 2009 (im-not-ai 경유, 미열람) | C |
| 영어 구조 표지(not-X-but-Y, 결어, 3항, 대시, 볼드 라벨, "serves as", 챗봇 잔재) | Wikipedia:Signs_of_AI_writing("descriptive, not prescriptive"; Ineffective/Historical 목록 유지); humanizer SKILL.md | C |
| 번역투 정전(`~에 대하여`, `~에 있어서`, `~에 의해`, 이중 피동) | 나무위키 번역체; 김한식 새국어생활 2012-1 | C |
| 국립국어원 「쉬운 공문서 쓰기 길잡이」(2022), 「공공언어 바로 쓰기(개정판)」(2022): 문장 길이·피동·명사 나열·번역투·일본어 투 50 | korean.go.kr etc_seq=700, 699. **문장 길이 수치(50자/60자)는 미검증**; hanlint·im-not-ai는 ~100자 | C |
| 한국어 민간 표지(주어·목적어 과잉 완결, 반복 어순, 균일 길이; 명언형 짧은 문장, 셋 묶기, 문단 끝 교훈) | brunch @maven/527, 오마이뉴스 2026-09-06 | D (대구·균일 길이만 B 지지) |
| `~할 수 있습니다` 남발, `다음은 ~입니다`, `핵심은 ~입니다`, 이모지, 볼드 남발, 요약 문장, 영어 직역 구조 | 도구에 인코딩; 독립 빈도 근거는 C-8/E-1 측정뿐. 과잉 존댓말은 어느 도구·연구도 다루지 않음 | C / D |
| Paul Graham "Writes and Write-Nots" | 의견 에세이 | D |
| Vale 한국어 지원 | regexp2, `nonword: true`; 한글 미시험 | [unverified] |

결론: fluent-korean은 실재하나 문법 완결성용 프롬프트이고 저자가 slop 제거는 im-not-ai를 가리킨다. 결정적·CI 가능한 한국어 린터는 hanlint가 유일(어린 프로젝트), kolint·Jieun이 소형 대안. 가장 근거가 강한 한국어 AI 표지는 구조(대구, 연결어미 뒤 쉼표, 균일·짧은 문장, `~한다` 단조, 띄어쓰기·POS 분포)이고, 인기 있는 어휘 금지(`~를 통해`, `것이다`)는 실측에 반하므로 빈도 경고로만 둔다.
