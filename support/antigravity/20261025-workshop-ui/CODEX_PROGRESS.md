# Codex 완료 범위 — 2026-10-25

- rpg/workshop.py: 고철/뼈 파편 강화 조리법, 미리보기, 상한, 영구 재료 차감 사본 생성.
- rpg/session.py: 미리보기 API 및 재료+무기 수치 원자적 저장. 성공 이후 캐시 반영.
- rpg/characters.py: 이름 확인 기반 캐릭터 목록 삭제. 저장 실패 시 복원, 프로필 파일 보존.
- game.py: 강화는 일반 게임 INVENTORY에서만 허용. 삭제는 INTRO에서만 허용.
  현재 캐릭터 삭제 시 게임/전투/장비 UI의 세션 참조 해제.
- tests/test_rpg_workshop.py 6개, tests/test_rpg_character_delete.py 4개 추가.

전체 테스트: 282개 통과. 로그 codex_tests.log.
저장 실패, 잠금, 상한, 여러 스택 차감, 중복 quote, 타 캐릭터 quote,
삭제 실패/마지막 삭제/등록 해제 후 파일 보존, 런/테스트 모드 제한을 검사했다.
모든 신규 테스트 저장은 TemporaryDirectory에서 실행했다.

아직 사용자용 강화 탭/삭제 버튼/확인창/구분 도형은 구현하지 않았다.
해당 UI와 실제 게임 통합·캡처는 TASK.md에 따라 Antigravity가 담당한다.
