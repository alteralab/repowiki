# 조회 스킬 eval 원장

실행 기록의 정본이다. `runs/` 는 커밋하지 않고(트레이스가 크다) 여기에 결론을 남긴다.
형식은 altera-skills 의 evals 원장을 따른다. 시나리오는 `scenarios/<스킬>-<이름>/` 이고
러너는 `bin/run.sh`, 채점은 `bin/grade.py`, 사람 판정은 실행 디렉터리의 `judgments.json` 이다.

| 날짜 | 실행 | 모델 | 시나리오 | 측정 기준 | 판정 기준 | 결과 | 비고 |
|---|---|---|---|---|---|---|---|
| 2026-09-10 | 2026-09-10-043057 | claude-fable-5-1 | 4 | 전부 통과 | absent-fact 의 no_fabrication 실패(기억으로 3600초를 덧붙임) | 3/4 | 픽스처 인덱스가 없는 쪽을 가리킴. Codex 리뷰 9건 반영 뒤 재실행 |
| 2026-09-10 | 2026-09-10-043918 | claude-fable-5-1 | 4 | 전부 통과 | no_fabrication 2건 통과(사람 판정) | 4/4 | 비용 $3.11. search-fallback 은 인용 링크의 원문을 GitHub 에서 받아 읽었다고 밝힘 |
| 2026-09-10 | 2026-09-10-050559 (+2026-09-10-050559-b) | claude-fable-5-1 | 6 | 전부 통과 | no_fabrication 3건 통과, asks_which 첫 판 실패 뒤 재실행 통과(사람 판정) | 5/6 + 재실행 1/1 | 비용 $9.04. 시스템 라우팅 추가 뒤 실행. route-two-wikis 는 system/llms.txt 를 먼저 읽고 commons-cli 로 갔고 위키 각주의 줄 번호가 어긋난 것을 찾아냈다. ambiguous-asks 첫 판(Options)은 정확한 타입명이 한쪽에만 있어 에이전트가 근거로 가렸고, 진짜 모호한 낱말(예외 계층)로 바꾼 뒤 두 위키를 따로 답하고 되물었다. 이전 판 실행 하나에서 absent-fact 가 스킬 없이 Grep 으로 답한 일이 있어 description 에 발동 단서를 더했다 |
