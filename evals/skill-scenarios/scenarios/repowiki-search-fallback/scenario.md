# repowiki-search-fallback

## Background

사용자가 인덱스의 한 줄 설명에는 안 나오는 타입 이름(RemoteLogMetadataSerde)을 묻는다. 그 이름은 concepts/6-5-apimessageandversion-offsetandepoch.md 의 호출 표 한 줄(`deserialize` 가 지역 변수 `ApiMessageAndVersion` 의 `message()` 를 부른다, 자리 `RemoteLogMetadataSerde.java:L93-L93`)에만 있다. 질문은 그 한 줄이 답하는 범위로 좁혔다. llms.txt 로는 고를 수 없고 scripts/search-wiki.sh 가 그 절을 찾는다.

## Expected Outcome

에이전트는 인덱스로 못 고른 뒤 search-wiki.sh 를 돌려 해당 절을 찾고, 그 쪽을 읽어 인용과 함께 답한다. llms-full.txt 를 통째로 열지 않는다.

## Grading Criteria

- [ ] skill_triggered: repowiki 스킬을 발동했다
- [ ] used_search_script: scripts/search-wiki.sh 를 실행했다
- [ ] right_page: concepts/6-5-apimessageandversion-offsetandepoch.md 를 찾아 읽었다
- [ ] cited: 답에 그 쪽 링크나 path:Lx-Ly 인용이 있다
- [ ] no_full_dump: llms-full.txt 를 통째로 열지 않았다(Read 도 cat 류도)
- [ ] no_fabrication: 표의 한 줄(message() 호출, L93)을 넘는 역할 설명을 사실처럼 말하지 않았다
