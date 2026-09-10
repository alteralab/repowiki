# repowiki-answer-dependency

## Background

사용자가 kafka 위키(./wiki, 쪽 셋과 인덱스 발췌)를 보다가 connect 모듈이 무엇에 기대는지 묻는다. 답은 areas/3-connect.md 에 있고 그 쪽은 클라이언트 모듈 링크와 각주 인용을 갖는다.

## Expected Outcome

에이전트는 repowiki 스킬을 발동하고, wiki/llms.txt 를 먼저 읽어 쪽을 고르고, areas/3-connect.md 를 읽어 답한다. 답의 문장에 쪽 링크나 path:Lx-Ly 인용이 붙는다. llms-full.txt 전체를 열지 않는다.

## Grading Criteria

- [ ] skill_triggered: repowiki 스킬을 발동했다
- [ ] index_first: wiki/llms.txt 를 쪽 원문보다 먼저 읽었다
- [ ] right_page: areas/3-connect.md 를 읽었다
- [ ] cited: 답에 쪽 링크(areas/3-connect.md)나 path:Lx-Ly 인용이 있다
- [ ] no_full_dump: llms-full.txt 를 통째로 열지 않았다(Read 도 cat 류도)
- [ ] no_fabrication: 쪽에 없는 관계나 수치를 출처 없이 말하지 않았다
