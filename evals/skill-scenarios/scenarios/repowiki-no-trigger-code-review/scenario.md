# repowiki-no-trigger-code-review

## Background

사용자가 파이썬 파일 하나의 코드 리뷰를 부탁한다. 위키와 무관하다.

## Expected Outcome

에이전트는 repowiki 스킬을 발동하지 않고 파일을 읽어 리뷰한다. search-wiki.sh 나 llms.txt 를 건드리지 않는다.

## Grading Criteria

- [ ] skill_not_triggered: repowiki 스킬을 발동하지 않았다
- [ ] no_wiki_reads: llms.txt 나 search-wiki.sh 를 건드리지 않았다
- [ ] answered: calc.py 를 읽고 리뷰를 냈다(빈 답이나 실행 실패는 통과가 아니다)
