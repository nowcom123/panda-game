# 작업 2: 관문 증원 흐름 개선 및 검토 지적 보완 결과 보고서

## 1. 최종 파라미터 및 실제 상태 전이

### 1.1 시스템 설정 파라미터 (`gate_wave.py: GateWaveConfig`)
- **작동 반경**: 플레이어-관문 거리 45.0m 이하 (`activation_radius = 45.0`)
- **스테이지당 최대 웨이브**: 3회 (`max_waves_per_stage = 3`)
- **웨이브당 출현 목표**: `2 + min(max(stage - 1, 0), 2)`마리 (1스테이지: 2마리, 2스테이지: 3마리, 3스테이지 이상: 4마리)
- **출현 전 경고 시간**: 2.0초 (`warning_duration = 2.0`)
- **웨이브 내 출현/재시도 간격**: 0.75초 (`spawn_interval = 0.75`, 스폰 실패/좌표 부재 시에도 동일 재시도 간격 적용)
- **웨이브 종료 후 재정비**: 8.0초 (`rest_duration = 8.0`)
- **다음 경고 허용 조건**: 관문 45m 이내 생존 적 6마리 이하 (`max_nearby_enemies_for_warning = 6`)
- **전체 생존 적 상한**: 16마리 (`global_alive_enemies_cap = 16`, 시체 제외, 보스 포함)
- **출현 단계 타임아웃**: 6.0초 (`spawning_phase_timeout = 6.0`)

### 1.2 상태 머신 전이 흐름
```
[WAITING] ──(45m 진입 & 주변 적 <= 6)──> [WARNING (2.0초)]
    │                                          │
    │                                (2.0초 경고 완료)
    │                                          ▼
[EXHAUSTED] <──(3회 소진 시)── [REST (8.0초)] <──(목표 달성 or 6초 타임아웃)── [SPAWNING (0.75초 간격)]
```

### 1.3 기존 분산 증원 5개 경로 일원화 내역
1. `MonsterDirector`: 45m 진입 시 2마리 즉시 스폰 코드 제거.
2. `MonsterDirector`: 25m 진입 시 3마리 즉시 스폰 코드 제거.
3. `MonsterDirector`: 32m 이내 4초 주기 무제한 증원 코드 제거.
4. `MonsterDirector`: 관문 근처 적 처치 시 65% 즉시 재증원 코드 제거.
5. `EscapePortalManager`: 5초 사수 중 2초 주기 증원 코드 제거.
-> 모든 관문 증원이 `GateWaveManager` 단일 상태 머신으로 통일되었습니다.

---

## 2. 검토 지적 5개 보완 내역 및 변경 파일

### 2.1 검토 지적 5개 반영 상세
1. **[지적 1] 생성 전 검사 반경과 실제 몬스터 반경 일치**:
   - `monster.py`: `TallSkeletonMonster`(0.40), `AbominableMudOrc`(0.45), `AlluringAshWitch`(0.38), `SkeletalDobermanHellhound`(0.35), `LongBlackSerpent`(0.38), `CableOverlordBoss`(0.55)에 클래스 수준 속성 `col_radius`를 선언하여 인스턴스 미생성 상태에서도 정확한 기본 반경을 조회할 수 있도록 개선.
   - `spawner.py`: `MONSTER_BASE_COLLISION_RADII` 딕셔너리 및 `get_monster_collision_radius(cls, is_elite=False)`를 구현하고, `apply_elite_mutation`의 반경 계산에 `round(..., 4)`를 적용하여 사전 검사값과 사후 실제 모델 반경이 오차 없이 일치하도록 동기화(정예 오크: 0.5625m).
   - 실제 `spawn_reinforcement_monster` 경로에서 일반 오크(0.45m), 정예 오크(0.5625m)를 선정하고 0.53m 벽 거리에 대해 정예 오크 거절 및 일반 오크 허용을 검증하는 `test_11` 추가.
2. **[지적 2] 빈 청크 목록 안전 검사 우회 방지 및 test_colliders 전용 코드 제거**:
   - `spawner.py:is_spawn_position_safe`: `chunks is None or not isinstance(chunks, dict) or len(chunks) == 0` 및 `chunk_coord not in chunks` 검사를 상단에 엄격히 배치하여 청크 미로드 시 반드시 `False`를 반환하도록 수정.
   - 생산 코드에 임시로 삽입되었던 `game.test_colliders` 분기를 완전히 제거하고, `collision.py`의 공식 API인 `register_custom_collider`와 `clear_custom_colliders` 및 실제 청크 자료구조(`cell_colliders`)를 사용하도록 정리.
3. **[지적 3] HUD 숨김·생명주기 메인 루프 연동**:
   - `gate_wave.py`: `get_status_hud_text()`, `refresh_hud()`, `hide_hud()` 메서드 추가.
   - `ui_manager.py`: `_set_hud_cluster_visible(visible)`에서 비가시화 시 `gate_wave_status_text`도 함께 숨기도록 연동.
   - `game.py`: `PAUSED`, `SHOP`, `INVENTORY`, `AAR`, `GAME_OVER`, `VICTORY` 조기 반환 시 및 `pause_game`, `open_inventory` 등에서 `gate_wave_mgr.hide_hud()` 호출; `resume_game`, `close_inventory`, `close_level_up_modal` 시 `gate_wave_mgr.refresh_hud()` 호출; `show_intro_scene` 및 `start_test_mode` 시 `gate_wave_mgr.reset()` 호출.
   - `test_06`에서 `LiminalInfiniteLoop.update` 조기 반환과 HUD 은닉/복원 경로를 직접 검증.
4. **[지적 4] 출현 실패 시 0.75초 재시도 간격 및 타임아웃 검사 순서 정돈**:
   - `gate_wave.py`: `SPAWNING` 틱 시작 시 타임아웃(`spawning_time_left <= 0.0`) 검사를 최우선 실행하여 시간이 소진된 틱의 신규 생성을 차단.
   - 안전 위치 부재로 `spawn_reinforcement_monster`가 `None`을 반환하더라도 `self.spawn_cooldown = self.config.spawn_interval` (0.75초)을 설정하여 매 프레임 후보 전체를 재검사하는 CPU 낭비 방지.
   - `test_04`에서 실패 시 0.75초 간격 유지(호출 횟수 제한), 부분 성공, 타임아웃 후 추가 호출 차단 검증.
5. **[지적 5] 보스 출현 프레임 순서 및 보스 고유 소환 패턴 보존**:
   - `monster_director.py:update_monsters`: 3스테이지 관문 38m 보스 출현 검사를 `gate_wave_mgr.update` 호출 **앞**으로 재배치하여, 보스가 출현하는 당일 프레임에 일반 웨이브가 먼저 스폰되지 않고 즉시 REST로 중단되도록 보완.
   - 기존 보스 고유 패턴(2페이즈 체력 50% 진입 시 2마리 스폰, 주기적 소환)은 온전히 보존.
   - `test_07`에서 관문 35m 접근 당일 프레임 보스 생성 -> 일반 웨이브 0회 즉시 중단 -> 보스 생존 중 8초 정비 동결 -> 보스 격파 후 8초 카운트다운 -> 2페이즈 고유 소환 2마리 유지의 통합 사례 검증.

### 2.2 변경 파일 및 실제 구현 함수
- [`gate_wave.py`](file:///c:/Users/user/Desktop/park/MyGame/gate_wave.py):
  - `GateWaveConfig`: 파라미터 정의 데이터 클래스.
  - `GateWaveManager`: `update`, `refresh_hud`, `hide_hud`, `get_status_hud_text`, `on_gate_changed`, `reset`, `get_cached_candidates`, `count_nearby_alive_enemies`, `count_global_alive_enemies`.
- [`monster.py`](file:///c:/Users/user/Desktop/park/MyGame/monster.py):
  - 몬스터 클래스별 클래스 속성 `col_radius` 선언.
- [`spawner.py`](file:///c:/Users/user/Desktop/park/MyGame/spawner.py):
  - `MONSTER_BASE_COLLISION_RADII`, `get_monster_collision_radius`.
  - `is_spawn_position_safe`: 청크 유효성, 벽/관문 충돌, 시야/차폐, 몬스터 중첩 판정.
  - `get_gate_corridor_candidates`: 10~30m 관문 복도 후보 좌표 추출.
  - `spawn_reinforcement_monster`: 0.75초 간격 준수, 모델 생성 없이 사전 반경 계산 및 fallback 없는 스폰.
- [`monster_director.py`](file:///c:/Users/user/Desktop/park/MyGame/monster_director.py):
  - 38m 보스 생성 로직을 `gate_wave_mgr.update` 이전으로 재배치.
  - 보스 2페이즈 고유 소환 패턴 유지.
- [`escape_portal.py`](file:///c:/Users/user/Desktop/park/MyGame/escape_portal.py):
  - 관문 확정 시 `monster_director.gate_wave_mgr.on_gate_changed` 호출 연동.
- [`game.py`](file:///c:/Users/user/Desktop/park/MyGame/game.py):
  - 메뉴/종료/테스트모드 조기 반환 시 `gate_wave_mgr.hide_hud()` 연동, 복귀 시 `refresh_hud()` 연동, `show_intro_scene` 및 `start_test_mode` 시 `reset()` 연동.
- [`ui_manager.py`](file:///c:/Users/user/Desktop/park/MyGame/ui_manager.py):
  - `gate_wave_status_text` 추가, `update_gate_wave_status` 구현, `_set_hud_cluster_visible` 은닉 연동.
- [`tests/test_bugfixes_20261022.py`](file:///c:/Users/user/Desktop/park/MyGame/tests/test_bugfixes_20261022.py):
  - `pass`만 있던 빈 `test_08` 제거 (실제 재시작/스테이지 전환 리셋은 `TestBug5PortalDefenseTimer.test_real_restart_and_advance_stage_timer_reset`에서 철저히 검증).
  - 지적 1~5 검증용 테스트 갱신 및 `test_11` 추가.

---

## 3. 테스트 검증 내용 및 실행 결과

### 3.1 실행 명령 및 결과
- **단위/통합 테스트**: `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`
  - 결과: **119개 테스트 전체 통과 (Ran 119 tests in 0.312s, OK)**
- **코드 검사**: `git diff --check`
  - 결과: **정상 (오류 및 공백 충돌 없음, Exit code 0)**
- **`rankings.json` 무단 변경 검증**: `git diff rankings.json`
  - 결과: 사용자 플레이 기록(2026-10-22 15:23:48)이 온전히 보존되었으며, 테스트 실행에 의한 신규 레코드 삽입이나 데이터 변경이 전혀 없음(정상 격리 확인).

### 3.2 검증 테스트 상세
1. `test_01_warning_duration_and_no_multi_spawns_on_large_dt`: 2초 경고 중 스폰 0회, 경고 완료 후 0.75초 간격 준수, 큰 dt(5.0초) 단일 프레임 주입 시에도 한 프레임에 1마리만 스폰됨을 검증.
2. `test_02_rest_duration_no_spawns_on_kill_and_max_waves_exhaustion`: REST 8초간 신규 출현 0회, 관문 근처 적 처치 시 65% 즉시 재스폰 차단, 3웨이브 소진 시 EXHAUSTED 전환 검증.
3. `test_03_nearby_enemies_threshold_and_global_alive_cap`: 관문 45m 내 살아있는 적이 6마리 초과 시 WARNING 진입 보류, 전체 생존 적이 16마리일 때 추가 스폰 차단, 시체(corpse)는 카운트에서 정상 제외됨을 검증.
4. `test_04_spawning_phase_timeout_and_no_budget_accumulation`: 안전 후보 없음으로 스폰 실패 시 0.75초 재시도 간격 유지, 6초 타임아웃으로 웨이브 강제 종료 및 REST 진입, 타임아웃 이후 스폰 시도 차단 검증.
5. `test_05_radius_exit_and_reentry_policies`: 45m 이탈 시 타이머 동결; WARNING 중 재진입 시 온전한 2초 경고 재제공; SPAWNING 중 재진입 시 남은 수량 앞에 2초 경고 재제공하되 6초 예산/웨이브 횟수 미추가; REST 잔여시간 정상 보존 검증.
6. `test_06_real_raw_dt_and_menus_test_mode_isolation`: `LiminalInfiniteLoop.update` 실행을 통해 PAUSED/SHOP/INVENTORY/AAR 조기 반환 및 HUD 은닉 검증, `resume_game` 시 안내 복원, 불릿타임 중 dilated world_dt가 아닌 실제 `raw_dt` 진행 검증.
7. `test_07_boss_presence_halts_waves_and_post_boss_rest`: 38m 보스 출현 프레임에 보스 우선 생성 및 일반 웨이브 즉시 중단(스폰 0회), 보스 생존 중 REST 타이머 동결, 보스 처치 후 8초 재정비 보장, 보스 고유 2페이즈 소환(2마리) 보존 검증.
8. (참조) `TestBug5PortalDefenseTimer.test_real_restart_and_advance_stage_timer_reset`: `restart_game` 및 `advance_to_next_stage` 호출 시 웨이브 수, 상태, 타이머, 후보 캐시 리셋 검증.
9. `test_09_safety_position_checks_comprehensive`: 빈 청크/None/미로드 청크 시 무조건 거절, `collision.register_custom_collider`를 활용한 실제 충돌체 검사, 관문 거리 10~30m, 플레이어 최소 12m, 정면 열린 시야 급습 배제, 선분 상 벽 차폐 시 허용, 후방 허용, 테스트 후 충돌체 정리 검증.
10. `test_10_door_defense_hold_isolated_from_wave_system`: 사수 구역(3.8m) 진입 및 5초 사수 진행이 웨이브 매니저를 중복 발동시키지 않고 온전히 독립 동작함을 검증.
11. `test_11_pre_spawn_collision_radius_matches_actual_monster_and_wall_rejection`: 실제 `spawn_reinforcement_monster` 경로에서 오크(0.45m)와 정예 오크(0.5625m) 사전 반경 일치, 0.53m 벽 거리에 대해 정예 오크 거절 및 일반 오크 허용, 0.65m 거리에서 정예 오크 생성 및 `col_radius` 일치 검증.

---

## 4. 플레이 감각 및 체감 한계 명시

- **검증 범위**: 119개의 단위 및 통합 자동화 테스트, 헤드리스 모듈 로딩 및 정적 검사를 통해 모든 수치 규칙과 기하학적 안전 조건, 충돌체 판정의 정확성을 확인하였습니다.
- **플레이 감각 미검증 명시**: 본 구현에 적용된 수치(경고 2초, 출현 간격 0.75초, 재정비 8초, 최대 3웨이브 등)는 1차 플레이테스트용 가설 파라미터입니다. 실제 GUI 수동 플레이를 통한 체감 난이도, 긴장감, 조작 피로도 및 재미는 검증된 것으로 주장하지 않으며, 추후 플레이어 피드백에 따라 미세 조정이 필요할 수 있습니다.

---

## 5. 기존 작업 및 사용자 수정 보존 확인

- **작업 1 버그 수정 보존**:
  - FOV 유지 (ADS / 불릿타임 / 메뉴 / 스테이지 전환 복원) 보존
  - 보스 그라운드 충격파 즉시 게임오버 처리 보존
  - 정예 몬스터 5종 비주얼 스케일 vs 레이캐스트 피격 판정 및 충돌체 일치 보존
  - 불릿타임 메뉴 상태 잔여 시간 보존
  - 개발 단축키(F5~F8) 및 테스트 모드 랭킹 기록 격리 보존
- **보스 고유 전투 패턴 보존**:
  - 케이블 채찍, 전방위 고전압 지진 충격파, 고압 와이어 다트 패턴 보존
  - 체력 50% 진입 시 2페이즈 폭주 및 미니언 소환(2마리) 패턴 보존
- **사용자 수정 내역 보존**:
  - 사용자 탄피 이펙트 및 HUD 무기/반동 시스템 보존
  - 퍽 선택창 레벨업 디커플링 및 UI 개선 보존
  - `rankings.json` 무단 수정 방지 및 보존 완료
