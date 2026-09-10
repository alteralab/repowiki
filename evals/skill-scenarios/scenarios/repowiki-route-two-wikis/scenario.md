# repowiki-route-two-wikis

## Background

뿌리 아래에 위키가 둘이다(kafka 발췌, commons-cli 발췌). system/llms.txt 가 둘을 가리킨다. 사용자는 어느 저장소인지 말하지 않고 commons-cli 의 타입(DefaultParser)이 옵션을 어떻게 가르는지 묻는다. 답은 commons-cli/wiki/concepts/2-defaultparser-unrecognizedoptionexception.md 에 있다.

## Expected Outcome

에이전트는 system/llms.txt(또는 system/index.md)를 먼저 읽어 commons-cli 를 고르고, 그 위키의 llms.txt 로 간 뒤 해당 쪽을 읽어 인용과 함께 답한다. kafka 위키를 헤매지 않는다.

## Grading Criteria

- [ ] skill_triggered: repowiki 스킬을 발동했다
- [ ] system_first: system/llms.txt 나 system/index.md 를 어느 위키의 llms.txt 보다 먼저 읽었다
- [ ] right_page: commons-cli/wiki/concepts/2-defaultparser-unrecognizedoptionexception.md 를 읽었다
- [ ] cited: 답에 그 쪽 링크나 path:Lx-Ly 인용이 있다
- [ ] no_full_dump: llms-full.txt 를 통째로 열지 않았다(Read 도 cat 류도)
- [ ] no_fabrication: 쪽에 없는 동작을 출처 없이 말하지 않았다
