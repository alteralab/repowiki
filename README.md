# repowiki

저장소 하나를 받아 사람이 읽을 아키텍처 위키를 만든다. Markdown과 Mermaid로 내고,
Fumadocs 정적 사이트로 띄운다.

만드는 문장마다 저장소의 줄 번호가 근거로 붙는다. 인용은 분석한 커밋에 고정된 소스 링크가
되므로, 위키를 읽다가 그 자리를 누르면 그때의 코드가 열린다.

## 무엇을 내는가

한 저장소에서 다음이 나온다.

- **개요** 저장소가 무엇으로 나뉘고 무엇이 무엇에 기대는지
- **개념 쪽** 타입 관계와 호출로 묶은 개념 단위. 빌드 모듈이 아니라 개념이 쪽의 단위다
- **언어와 라이브러리 버전** 빌드 파일에서 읽은 버전 표. 값마다 그 값을 적은 자리가 붙는다
- **빌드와 검사 파이프라인** CI 정의에서 읽은 것. 자격 증명은 가린다
- **사용 예** 테스트가 확인하는 입력의 경우들
- **변경 핫스팟** 자주 바뀐 자리와 함께 바뀌는 짝
- **교차 모듈 흐름** 진입점에서 시작해 모듈 경계를 넘는 경로 (모듈이 여럿일 때)
- **데이터 모델** 저장소가 선언한 테이블과 외래 키 (엔티티가 있을 때)

도식은 여섯 종류다. 묶음 그림(flowchart), 모듈 그림(flowchart), 타입 상세(classDiagram),
협력(flowchart), 호출 순서(sequenceDiagram), 변경 이력(timeline), 데이터 모델(erDiagram).

## 요구 사항

| 항목 | 판 | 왜 |
|---|---|---|
| Python | 3.12 이상 | |
| uv | 최신 | 의존을 잠금 파일로 고정한다 |
| git | 최신 | 이력과 원격 URL을 읽는다 |
| Node.js | 22 이상 | Mermaid 파서 게이트와 Fumadocs 사이트 |
| ast-grep | 0.45.3 | Python 의존으로 함께 설치된다 |

`ast-grep`은 `ast-grep-cli` 패키지로 함께 들어오므로 따로 설치하지 않는다.
Node.js는 사이트를 만들 때만 필요하다. 위키 Markdown까지만 낼 것이면 없어도 된다.

## 설치

```sh
git clone <이 저장소> repowiki
cd repowiki
uv sync                       # 잠금 파일 그대로 설치한다
uv run repowiki --help
```

사이트를 만들 것이면 Node 의존도 함께 받는다. 처음 `repowiki site`를 돌릴 때 자동으로
`npm ci`가 돌지만, 미리 받아 두려면 이렇게 한다.

```sh
npm ci --prefix src/repowiki/data/site-template
```

## 쓰는 법

세 단계다. 분석하고 계획하고, 쪽을 쓰고, 묶는다.

```sh
# 1. 분석과 계획을 한 번에. 종료 코드가 0이어야 한다.
uv run repowiki run ~/work/commons-cli --out ./out

# 2. 쪽을 쓴다. 아래 "쪽을 쓰는 두 가지 길"을 보라.

# 3. 묶는다.
uv run repowiki bundle --out ./out

# 4. 사이트로 띄운다 (선택).
uv run repowiki site --out ./out --open
```

`run`은 `analyze`와 `write`를 이어 돌린다. 따로 돌려야 하면 그 둘을 직접 부른다.

`./out`에 이런 것이 생긴다.

```
out/
  facts.json          결정층이 낸 사실 전부
  source-root.txt     분석한 작업본의 자리
  .repowiki/
    jobs/<작업 id>/
      job.json        그 쪽이 볼 사실과 근거와 도식과 표
      brief.md        쓰는 층이 읽을 지시문 (근거의 원문 포함)
      page.json       제출한 쪽
    store.sqlite      작업 상태
  wiki/               최종 Markdown, llms.txt, llms-full.txt
  site/out/           Fumadocs 정적 사이트
```

### 쪽을 쓰는 두 가지 길

**세션 드라이버 (기본).** Claude Code 같은 세션 안에서 사람이나 에이전트가 한 쪽씩 받아
쓴다. API 키가 필요 없다. Claude Code에서는 `.claude/skills/write-wiki`가 이 흐름을 굳혀 둔다.

```sh
uv run repowiki job status --out ./out                 # 무엇이 남았는지
uv run repowiki job take concept-help --out ./out      # 이름으로 지정해 받는다
uv run repowiki job next --out ./out                   # 또는 대기 순서대로

uv run repowiki job show concept-help --out ./out                    # 사실과 근거 목록
uv run repowiki job show concept-help --out ./out --source E1,E5     # 근거의 원문

# page.json을 그 작업 디렉토리에 쓴 뒤
uv run repowiki job submit ./out/.repowiki/jobs/concept-help/page.json --out ./out
```

`page.json`의 형식은 이렇다.

```json
{
  "job_id": "concept-option-optiongroup",
  "title": "Option와 OptionGroup",
  "description": "한 문장 설명",
  "tags": ["concept", "java"],
  "body_markdown": "본문...",
  "citations": ["E1", "E2"]
}
```

### 도식과 표는 자리표시자로 넣는다

게이트는 작업이 준 도식과 표가 **글자 그대로** 있어야 통과시킨다. 손으로 옮겨 적으면
옮기다 틀리는 일이 규칙 위반과 구별되지 않는다. 그래서 자리표시자를 쓴다.

```markdown
{{diagram:TYPE-Option}}

{{table:members-Option}}
```

제출할 때 도구가 사실의 소스로 편다. 쓸 수 있는 이름은 `job show`의 "자리표시자" 절에
그대로 나온다. 없는 이름을 쓰면 제출이 거부된다.

**API 드라이버.** 배치로 돌릴 때 쓴다.

```sh
uv sync --extra api
export ANTHROPIC_API_KEY=...
```

### 게이트가 무엇을 거부하는가

제출한 쪽은 게이트를 지나야 위키에 실린다. 거부되면 그 작업이 다시 대기로 돌아간다.

| 규칙 | 무엇을 본다 |
|---|---|
| `citation-out-of-range` | 그 작업이 주지 않은 근거 id를 인용했다 |
| `too-few-citations` | 산문 60단어에 인용 한 건이 안 된다 |
| `too-short` | 그 쪽 종류의 목표 분량의 절반에 못 미친다 |
| `diagram-missing` / `diagram-not-from-facts` | 작업이 준 도식을 빼거나 없는 도식을 그렸다 |
| `table-missing` / `table-not-from-facts` | 작업이 준 표를 빼거나 없는 표를 만들었다 |
| `html-table` | 표를 HTML로 썼다. 표의 값은 사실에서 와야 한다 |
| `em-dash` / `interpunct` / `emoji` / `double-passive` | 산문 규범 |
| `empty-description` | 설명이 비었다 |

## 설정

값의 정본은 전부 `src/repowiki/data/` 아래에 있다. 코드를 고치지 않고 여기를 고친다.

| 파일 | 무엇을 정한다 |
|---|---|
| `languages.yml` | 확장자에서 언어로. 분석 가능한 언어 목록 |
| `exclude.yml` | 제외 경로와 테스트 표식 |
| `buildfiles.yml` | 모듈 경계를 만드는 빌드 파일 |
| `diagram-limits.yml` | 도식의 노드 상한과 레이아웃, 쪽 종류별 도식·분량 예산 |
| `forges.yml` | 호스팅별 소스 링크 규칙. 사내 GitLab 이름을 여기 더한다 |
| `secrets.yml` | 값을 가릴 설정 키. 자격 증명이 위키에 실리지 않게 한다 |
| `issue-links.yml` | 커밋 메시지에서 이슈 키를 찾는 규칙 |
| `rules/{java,python,scala}/` | ast-grep 규칙 |

### 사내 GitLab에서 쓰기

원격이 사내 GitLab이면 `forges.yml`의 `gitlab.match`에 그 호스트를 더한다.

```yaml
forges:
  gitlab:
    match: [gitlab.com, gitlab., code.mycorp.com]
    blob: "/-/blob/{commit}"
    line: "#L{start}-{end}"
```

호스트 판정은 점 경계로 한다. 부분 문자열이 아니므로 `evilgitlab.com`은 걸리지 않는다.

원격이 없는 작업본도 분석된다. 그때 인용은 링크 없이 경로와 줄 번호 문자열로 남는다.

## 언어 지원

| 대상 | 줄 수 | 파일 역할 | 심볼 | 임포트 | 타입 관계 | 호출 그래프 |
|---|---|---|---|---|---|---|
| Java | 있음 | 있음 | 있음 | 있음 | 있음 | 있음 |
| Python | 있음 | 있음 | 있음 | 있음 | 있음 | 있음 (임포트로 증명된 것만) |
| Scala | 있음 | 있음 | 있음 | 있음 | 일부 | 일부 |
| TypeScript / TSX | 있음 | 있음 | **없음** | **없음** | **없음** | **없음** |
| Go, Kotlin, JavaScript | 있음 | 있음 | **없음** | **없음** | **없음** | **없음** |
| Terraform | **없음** | 있음 | **없음** | **없음** | **없음** | **없음** |
| Helm, Ansible, k8s | **없음** | config | **없음** | **없음** | **없음** | **없음** |

정본은 `languages.yml`의 `analyzed`이고 오늘은 `[java, python, scala]`다. 확장자 표에는 있으나
`analyzed`에 없는 언어는 줄 수만 세고 심볼을 내지 않는다. `.tf`는 확장자 표에도 없어 `other`로
센다. Helm과 Ansible의 YAML은 설정 키 색인에만 잡히는데, 그 색인은 한 줄의 `키: 값`만 보므로
중첩 경로도 템플릿 관계도 태스크 정체도 담지 않는다.

조용히 다른 것으로 대체하지 않고, 무엇을 못 보았는지를 `analyze`의 출력에 적는다.

## 결정성

같은 작업본에서 같은 `facts.json`이 나온다. `PYTHONHASHSEED`를 바꿔도 바이트 단위로 같다.
ast-grep의 방출 순서에 기대지 않도록 매치를 정본 순서로 정렬하고, 커뮤니티 검출의 입력도
정렬된 순서로 넣는다.

## 규모

측정한 값이다(맥북, 2026-09-09).

| 저장소 | 파일 | 심볼 | 호출 엣지 | 시간 | 최대 메모리 |
|---|---|---|---|---|---|
| commons-cli | 143 | 1,482 | 579 | 3초 | 0.3GB |
| dubbo | 6,900 | 30,397 | 21,977 | 24초 | 2.1GB |
| airflow | 8,600 | 72,953 | 19,618 | 51초 | 3.8GB |
| kafka | 7,300 | 69,008 | 51,546 | 101초 | 7.7GB |

## 반입 환경

인터넷이 없는 환경에서는 두 가지를 미리 실어야 한다.

1. Python 의존: `uv sync`로 만든 `.venv` 또는 wheel 묶음
2. Node 의존: `src/repowiki/data/site-template/node_modules`

`repowiki site`는 `node_modules`가 이미 있으면 `npm ci`를 건너뛴다.

## 개발

```sh
uv run pytest tests -q                       # 단위와 회귀
uv run ruff check --config ruff.toml src     # 생성 규약
bash scripts/gate_chain.sh                   # 게이트 전부
```

코드 규약의 정본은 이 저장소가 아니라 `altera-rules`이고, 여기에는 그 표면만 심겨 있다.

**다른 기계에서 게이트를 돌리려면 그 저장소가 필요하다.** `ruff.toml`과 `pyproject.toml`의
`extend`, 그리고 `.pre-commit-config.yaml`의 `repo:`가 로컬 체크아웃의 절대 경로를 가리킨다.
세 자리를 자기 경로로 바꾸면 게이트가 돈다.

```sh
git clone <altera-rules> ~/workspace/altera-rules
sed -i '' "s#/Users/angyojun/workspace/altera-rules#$HOME/workspace/altera-rules#g" \
  ruff.toml pyproject.toml .pre-commit-config.yaml
```

`repowiki` 명령 자체는 `altera-rules`가 없어도 돈다. 필요한 것은 개발 게이트뿐이다.
게이트 체인은 없는 도구를 조용히 건너뛰지 않고 무엇을 건너뛰었는지 출력한다.

- 목표와 성공 기준: `SPEC.md`
- 설계 판단: `PLAN.md`
- 깊이 단계의 근거와 계획: `docs/plans/depth.md`
- 무엇을 언제 어떻게 쟀는지: `scripts/RUNLOG.md`

## 한계

정직하게 적어 둔다.

- 한 메서드 안의 형제 블록이 스코프를 공유한다. 블록 범위를 사실로 들어야 고칠 수 있다
- 체인 표현식(`a.b().c()`)의 수신자는 풀지 않는다. 중간 반환 타입을 모른다
- 상속받은 멤버를 통한 호출은 상위 타입까지 올라가지 않는다
- 저장소 밖의 부모 POM이 정하는 버전은 `${...}` 그대로 남는다. 지어내지 않는다
- 문서 색인은 Markdown 제목만 본다. 제목 없는 산문은 파일 전체가 한 자리다
- 인용이 그 문장을 실제로 지지하는지는 게이트가 보지 못한다. 존재와 범위만 본다

이 수들은 `analyze`가 매번 출력한다. 무엇을 못 보았는지가 산출물에 남는다.
