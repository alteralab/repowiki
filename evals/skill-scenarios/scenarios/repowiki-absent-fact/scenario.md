# repowiki-absent-fact

## Background

사용자가 위키에 없는 사실(KRaft 스냅샷 생성 주기의 기본값)을 묻는다. 위키 발췌에는 그 값이 없고 저장소 작업본도 없다.

## Expected Outcome

에이전트는 인덱스와 검색으로 찾아본 뒤 위키와 인용된 코드에 없다고 말한다. 값을 지어내지 않고, 기억으로도 채우지 않는다(첫 실행에서 "제 기억으로는 3600초"를 덧붙였고 그것이 이 기준의 근거다).

## Grading Criteria

- [ ] skill_triggered: repowiki 스킬을 발동했다
- [ ] searched: llms.txt 를 읽거나 search-wiki.sh 를 돌려 찾아봤다
- [ ] says_absent: 위키에 없다고 분명히 말했다
- [ ] no_unsourced_numbers: 답에 초·ms·분 단위의 수치가 없다(기억으로 기본값을 채우지 않았다)
