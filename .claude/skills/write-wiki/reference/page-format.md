# 제출물의 형식

`page.json`의 필드와 게이트가 그것을 어떻게 보는지.

## 필드

```json
{
  "job_id": "concept-option-optiongroup",
  "title": "Option와 OptionGroup",
  "description": "한 문장. 사이드바 아래와 llms.txt에 실린다",
  "tags": ["concept", "java"],
  "body_markdown": "본문",
  "citations": ["E1", "E5"]
}
```

- `job_id`는 그 작업의 id와 같아야 한다. 다르면 없는 작업이라고 거부한다.
- `title`과 `description`은 사람이 정한다. 계획 층이 준 제목은 기계가 지은 이름이라
  더 나은 이름이 있으면 바꾼다.
- `citations`는 본문이 실제로 인용한 id다. 머리말의 `sources`가 이 목록이 아니라 본문에서
  찾은 것으로 채워지므로, 여기 적고 본문에 안 쓰면 그 근거는 실리지 않는다.

## 자리표시자

도식과 표는 본문에 이렇게 둔다.

```
{{diagram:TYPE-Option}}
{{table:members-Option}}
```

제출할 때 사실의 소스로 펴진다. 쓸 수 있는 이름은 `next`가 낸 "자리표시자" 절에 있고,
없는 이름을 쓰면 제출이 거부된다. 손으로 옮겨 적지 않는다 — 옮기다 틀리면 게이트는
그것을 규칙 위반과 구별하지 못한다.

작성자가 쓴 `page.json`은 제출 뒤에도 자리표시자를 그대로 들고 있다. 사실 층이 바뀌어
도식이 달라져도 같은 글을 다시 낼 수 있다.

## 게이트가 거부하는 것

| 규칙 | 무엇을 본다 |
|---|---|
| `citation-out-of-range` | 그 작업이 주지 않은 근거 id를 인용했다 |
| `too-few-citations` | 산문의 인용 밀도가 모자란다 |
| `too-short` | 그 쪽 종류의 분량 하한에 못 미친다 |
| `diagram-missing` / `diagram-not-from-facts` | 준 도식을 빼거나 없는 도식을 그렸다 |
| `table-missing` / `table-not-from-facts` | 준 표를 빼거나 없는 표를 만들었다 |
| `html-table` | 표를 HTML로 썼다 |
| `em-dash` / `interpunct` / `emoji` / `double-passive` | 산문 규범 |
| `empty-description` | 설명이 비었다 |

밀도와 분량의 실제 숫자는 `scripts/wiki_loop.py thresholds`가 낸다. 여기 적지 않는 것은
그 값의 정본이 `gate/page.py`와 `data/diagram-limits.yml`이기 때문이다.

거부 사유는 무엇이 빠졌는지를 자리표시자 이름으로 말한다. 그 이름을 본문에 넣으면 된다.

## 인용의 형식

본문에서 `[^E3]`으로 인용한다. 각주 정의는 도구가 만든다 — 본문에 `[^E3]: ...`를 쓰지
않는다. 각주는 분석 커밋에 고정된 소스 링크가 된다.
