# repowiki-ambiguous-asks

## Background

뿌리 아래에 위키가 둘이다(kafka 발췌, commons-cli 발췌). 사용자가 "예외 계층"을 묻는데 어느 저장소인지 말하지 않는다. 두 위키 모두 자기 예외 계층을 다룬다(kafka 는 areas/1-clients.md 의 "오류를 어떻게 다루는가", commons-cli 는 concepts/2-defaultparser-unrecognizedoptionexception.md). 첫 판은 "Options" 였는데, 에이전트가 정확히 그 이름의 타입은 commons-cli 에만 있다고 근거로 가려 답했다. 그것은 짐작이 아니라 실측이라 시나리오를 진짜 모호한 낱말로 바꿨다(2026-09-10).

## Expected Outcome

에이전트는 system/llms.txt 를 읽고, 뿌리에 검색을 돌려 두 위키에 다 있음을 확인한 뒤, 짐작해서 하나를 고르지 않고 사람에게 어느 저장소를 말하는지 묻는다. 물을 때 두 저장소의 이름과 무엇이 있는지를 보인다.

## Grading Criteria

- [ ] skill_triggered: repowiki 스킬을 발동했다
- [ ] system_first: system/llms.txt 나 system/index.md 를 어느 위키 파일보다 먼저 읽었다
- [ ] used_search_script: scripts/search-wiki.sh 를 실행했다
- [ ] asks_which: 답이 두 저장소 이름을 모두 들고 어느 것인지 사람에게 묻는다
- [ ] no_full_dump: llms-full.txt 를 통째로 열지 않았다(Read 도 cat 류도)
