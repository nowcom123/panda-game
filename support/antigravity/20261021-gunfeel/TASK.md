# 총기 개선 협업 지시서 — 2026-10-21

프로젝트: `C:\Users\nowco\Desktop\Dream\panda-game`
목표: 시야를 가리지 않는 탄피 크기·배출·수명 개선. Codex는 반동과 조준 복귀를 동시에 작업한다.

## 파일 소유권 (동시 편집 충돌 방지)
- Antigravity: 새 `casing_effects.py`, `tests/test_casing_effects.py`, 이 폴더의 `RESULT.md`와 `INTEGRATION.md`만 작성한다.
- Codex: `combat_system.py`, `player_controller.py`, 새 반동 모듈 및 테스트를 담당한다.
- **combat_system.py를 직접 수정하지 말 것.** 연결할 위치와 코드 조각을 INTEGRATION.md에 작성하면 Codex가 통합한다.
- 기존 수정 중인 ui_manager.py, geometry.py, rankings.json 및 다른 테스트를 건드리지 말 것.
- 커밋/push/pull, 설치, 실행 중인 게임 종료 금지. 사용자에게 프롬프트 입력을 받은 뒤 작업한다.

## 현재 코드 조사
combat_system.py의 `_init_pools`, `_eject_casing`, update의 탄피 루프, reset의 casing_pool 정리를 읽는다.
현재 24개 풀, 카메라 기준 고정 배출 위치, 1.4초 수명, 기본 원통에 색/배율 변경 방식이다.
샷건은 펌프 동작 때 배출하며 발사 직후에 추가로 배출하면 안 된다.
큰 구형 총구 섬광 제거와 AR 가늠쇠 수정은 보존한다.

## 새 모듈 계약
`CasingEffects(world_root, capacity=24)`
- `emit(weapon, position, velocity, is_left=False)`: position/velocity는 world_root 좌표계의 Vec3.
- `update(dt)`: 중력/회전/바닥 반동/짧은 페이드 및 수명 종료.
- `clear()`: 전부 비활성화/숨기기, 새 게임에서 잔여 탄피 없음.
- `destroy()`: 생성 노드 정리.
- 상한 고정 풀. 발사마다 노드 생성 금지. 전 무기 공유 풀에서 재사용 시 크기·색·투명도·회전이 초기화되어야 한다.

## 요구사항
1. PISTOL/DUAL_PISTOL/AR/SHOTGUN의 탄피 크기를 무기에 맞춰 작게 구분한다.
2. 샷건 셸은 짧은 붉은 몸체와 황동 바닥. 나머지는 원통형 금속 탄피. 과한 발광 setLightOff는 지양한다.
3. 약 0.7~1.0초 수명, 끝부분 페이드. 착지 후 떨림/끝없는 튀기 방지.
4. 기존 기하 helper의 setScale이 원래 치수를 덮어쓰지 않도록 별도 root와 실제 크기의 자식 메시를 사용한다.
5. INTEGRATION.md에 실제 총기 노드(권총 recoil_node, dual_left/right_recoil, ar_recoil_node, sg_recoil_node)의 배출구 기준 위치/방향을 world_root로 변환하는 구체적 연결 코드를 제안한다. 카메라 바로 앞/화면 중앙으로 날아오지 않게 옆으로 배출한다. 좌측 쌍권총은 좌측으로.
6. 피해량/발사 속도/소리/총구 화염/반동은 변경하지 않는다.

## 검증과 보고
작은 실제 Panda3D NodePath 기반 테스트로 풀 재사용(샷건→권총), 총량 제한, 수명 종료, clear, 큰 dt에서도 안정성을 확인한다.
가능하면 간단한 오프스크린 시각 확인을 하되 의존성 설치는 하지 않는다.
RESULT.md에 실제 변경 파일, 실행 명령과 결과, 남은 통합 작업을 기록한다.
