# 작업 결과 보고서: 판정·설정 버그 수정 및 검토 보완 (2026-10-22)

## 1. 6개 항목별 조치 내역 및 보완 사항

1. **사용자 FOV 설정 유지**: [완료]
   - **원인**: 설정 메뉴는 `camLens`에만 직접 값을 반영하고 있었으나, 전투 루프(`CombatSystem.update`)에서 기본 96도와 ADS 80도를 매 프레임 하드코딩으로 덮어씀.
   - **수정**: `base.base_fov`(기본 96도, 범위 70~115도)를 단일 권위 속성으로 두고, `UIManager` 설정 UI 및 `CombatSystem` 조준(ADS 비율 `base_fov * (80/96)` + 불릿타임 `+6.5도`) 계산이 이를 참조하도록 일원화함.

2. **보스 충격파 사망 처리 및 무적 판정**: [완료 / 보완]
   - **원인**: `MonsterDirector.update_monsters`의 보스 Ground Shockwave 분기에서 `player.take_damage(20)` 반환값을 확인하지 않아 사망 시 즉시 게임 오버로 전환되지 않고 슬로우 및 추가 패턴이 계속 진행됨.
   - **수정**: `is_dead` 반환값을 확인하여 치명 피해 시 `trigger_game_over(killer=m, reason="killed")`를 호출하고 즉시 `(True, closest_dist)`로 종료하여 추가 피격 및 후속 공격을 차단함.
   - **보완**: 실제 `PlayerController.take_damage`의 `invincible_timer` 무적 처리 로직을 연동하여, 무적 상태(0.55초)에서는 충격파 피해가 무효화되고 무적 해제 시 체력 감소 및 치명타 즉시 사망 처리가 정상 동작함을 검증함.

3. **정예 외형과 판정 배율 일치 및 헤드샷 검증**: [완료 / 보완]
   - **원인**: `spawner.apply_elite_mutation`에서 `node.setScale(1.25)`로 외형만 확대하고, 수동 사격 판정(`is_hit_by_ray`) 및 이동 충돌 반경(`col_radius`)은 고정값을 사용함.
   - **수정**: `apply_elite_mutation` 시 `col_radius`를 1.25배 확대하고, 정예 적용 가능한 5종 몬스터의 `is_hit_by_ray`에서 모델 원점 기준 상대 오프셋과 구체 반지름을 `node.getScale()[0]`(1.25배)로 동적 스케일링함.
   - **보완**: 회전(Heading 45도) 상태인 5종 정예 몬스터 전체의 실제 확대 머리 좌표를 정밀 조준한 레이캐스트 사격을 수행하여 `is_hit_by_ray == True` 및 `last_hit_was_head == True` 판정이 일치함을 검증함.

4. **정지 상태에서 불릿타임 보존**: [완료]
   - **원인**: `LiminalInfiniteLoop.update`에서 `bullet_time_timer` 및 오디오 업데이트를 `SHOP`, `INVENTORY`, `PAUSED`, `AAR` 조기 반환보다 먼저 실행하여 일시정지 중에도 시간이 감소함.
   - **수정**: 불릿타임 시간 감소 및 오디오 업데이트 로직을 메뉴 조기 반환 이후(`PLAYING` 진행 단계)로 이동하여 정지 상태에서 잔여시간이 보존되도록 수정함.

5. **탈출 방어전 증원 타이머 초기화**: [완료 / 보완]
   - **원인**: 실제 증원 누적은 `EscapePortalManager.door_defense_spawn_timer`를 사용하나, `game.restart_game`과 `advance_to_next_stage`는 `game.door_defense_spawn_timer`만 초기화하고 영역 이탈 시 누적시간이 보존됨.
   - **수정**: `EscapePortalManager`를 단일 소유자로 정립하고 `game.door_defense_spawn_timer`를 property로 연결하였으며, 영역 이탈 시와 새 관문 생성 시 `0.0`으로 초기화하여 온전한 2초 사수 시에만 증원이 발생하도록 수정함.
   - **보완**: 무거운 외부 작업(맵/청크/3D 엔티티 스폰)만 mock 처리하고 실제 `restart_game()` 및 `advance_to_next_stage()`를 직접 호출하여 `portal_mgr.door_defense_spawn_timer`가 0.0으로 정확히 초기화되는 것을 검증함.

6. **개발 단축키와 일반 기록 분리 및 F8 특성 연동**: [완료 / 보완]
   - **원인**: `_on_f7_grant_exp`가 일반 `PLAYING` 모드에서도 작동하고 있었으며, F5~F8 핸들러 가드 및 테스트 모드 플레이 결과의 랭킹 기록 차단 장치가 부족함. 또한 F8 핫키가 실제 사격 시스템이 참조하는 `has_perk` / `add_perk` 경로와 불일치하고 중복 누적 위험이 있었음.
   - **수정**: F5~F8 핸들러에 `is_test_mode` 가드를 적용하고, `trigger_victory`, `trigger_game_over`, `save_rank_record`에 테스트 모드 차단 가드를 추가함.
   - **보완**: F8 핸들러를 실제 `player.add_perk` 경로로 연결하고 `has_perk` 검사를 통해 이미 보유한 퍽은 중복 지급되지 않도록 방어함. F8을 반복 입력해도 퍽 레벨이 1로 유지되며 `player.has_perk("dragons_breath")`, `player.has_perk("tesla_arc")`가 정상 활성화됨을 검증함.

---

## 2. 변경 파일 및 핵심 함수 목록

- `game.py`:
  - `__init__`: `base_fov` 기본값 설정
  - `update`: 메뉴 정지 상태 시 불릿타임 시간 및 사운드 업데이트 보존
  - `door_defense_spawn_timer`: property getter/setter를 통해 `portal_mgr` 단일 상태 포워딩
  - `restart_game`: `is_test_mode = False` 복구 및 `door_defense_spawn_timer = 0.0` 초기화
  - `advance_to_next_stage`: `door_defense_spawn_timer = 0.0` 초기화
  - `_on_f5_pressed` / `_on_f6_spawn_boss` / `_on_f7_grant_exp`: `is_test_mode` 가드 적용
  - `_on_f8_test_elemental`: `is_test_mode` 가드, `player.has_perk` 검사 후 `player.add_perk` 연동 (반복 입력 시 레벨 증가 차단)
  - `trigger_victory` / `trigger_game_over`: 테스트 모드 시 랭킹 저장 차단
- `combat_system.py`: `update` (사용자 `base_fov` 기반 ADS/불릿타임 동적 FOV 계산)
- `ui_manager.py`: `show_pause_menu` / `_adjust_setting` (`base_fov` 70~115도 클램프), `save_rank_record` (테스트모드 파일 쓰기 가드)
- `monster_director.py`: `update_monsters` (보스 Ground Shockwave 치명타 시 `trigger_game_over` 및 즉시 반환)
- `spawner.py`: `apply_elite_mutation` (`col_radius` 1.25배 반영)
- `monster.py`: 5종 몬스터의 `is_hit_by_ray` (상대 오프셋 및 반지름 1.25배 동적 스케일링)
- `escape_portal.py`: `setup_escape_portal`, `update_door_defense` (영역 이탈 및 관문 생성 시 `door_defense_spawn_timer = 0.0` 초기화)
- `tests/test_bugfixes_20261022.py`: 14개 단위 테스트 케이스

---

## 3. 회귀 테스트 상세 목록 (`tests/test_bugfixes_20261022.py`)

1. `TestBug1FovPersistence.test_fov_adjust_and_combat_update_cycle`: 105도 설정 후 전투 업데이트, ADS, 불릿타임 적용/해제 시 정상 복귀 및 70~115도 범위 클램프 검증
2. `TestBug2BossShockwave.test_boss_shockwave_fatal_damage_triggers_game_over`: 충격파 치명타 시 게임오버 1회 호출, 즉시 반환, 슬로우/추가공격 미실행 검증
3. `TestBug2BossShockwave.test_boss_shockwave_non_fatal_damage_does_not_trigger_game_over`: 충격파 비치명 피해 시 슬로우 적용 및 게임오버 미호출 검증
4. `TestBug2BossShockwave.test_boss_shockwave_with_real_player_take_damage_invincibility`: 실제 `PlayerController.take_damage` 무적 타이머(0.55초)에 따른 피해 무효화 및 무적 해제 시 사망/생존 분기 검증
5. `TestBug3EliteHitboxScaling.test_tall_skeleton_hitbox_scaling`: 일반 vs 정예 판정 배율 및 상단 헤드샷/외곽 miss 검증
6. `TestBug3EliteHitboxScaling.test_all_five_monster_types_elite_col_radius_and_headshots`: 5종 정예 전체의 `col_radius` 배율 및 회전 상태 머리 조준 시 `last_hit_was_head == True` 일치 검증
7. `TestBug4BulletTimePausePreservation.test_bullet_time_preservation_across_menu_states`: PAUSED/SHOP/INVENTORY/AAR 상태 동안 불릿타임 보존 및 PLAYING 복귀 후 정상 소모/종료 검증
8. `TestBug5PortalDefenseTimer.test_defense_timer_reset_on_zone_exit_and_lifecycle`: 1.9초 방어 후 영역 이탈 시 0초 리셋, 재진입 후 즉시 증원 없음, 2초 연속 사수 시 1회 증원 검증
9. `TestBug5PortalDefenseTimer.test_real_restart_and_advance_stage_timer_reset`: 실제 `restart_game` 및 `advance_to_next_stage` 호출 시 `portal_mgr` 누적시간 0.0 초기화 검증
10. `TestBug6DevHotkeysAndRankingIsolation.test_dev_hotkeys_blocked_in_normal_playing`: 일반 플레이 모드에서 F5~F8 무반응 및 퍽 미지급 검증
11. `TestBug6DevHotkeysAndRankingIsolation.test_dev_hotkeys_functional_in_test_mode`: 테스트 모드에서 F5~F8 정상 작동 및 `add_perk`를 통한 퍽 정상 획득 검증
12. `TestBug6DevHotkeysAndRankingIsolation.test_f8_repeated_press_does_not_increment_perk_levels`: 반복 F8 입력 시 `add_perk` 경로를 통해 레벨 1이 유지되고 특성 레벨이 계속 증가하지 않음 검증
13. `TestBug6DevHotkeysAndRankingIsolation.test_ranking_record_isolation_in_test_mode`: 테스트 모드 종료 시 `save_rank_record` 미작성 및 차단 검증
14. `TestBug6DevHotkeysAndRankingIsolation.test_test_mode_resets_on_normal_restart`: `restart_game` 호출 시 `is_test_mode` 초기화 검증

---

## 4. 테스트 실행 결과

- **실행 명령**: `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`
- **실행 결과**: **Ran 104 tests in 0.259s / OK** (기존 90개 + 신규/보강 14개 전체 통과)
- **코드 스타일/포맷 검증**: `git diff --check` 통과 (0 errors)

---

## 5. 직접 검증하지 않은 항목 및 GUI 미확인 명시

- **GUI 미확인**: 본 작업은 비대화형 CLI 환경에서 수행되었으므로 실제 창(Window)을 화면에 띄우고 사용자가 직접 키보드/마우스를 조작하여 눈으로 시각적 요소를 확인하는 수동 GUI 검증은 진행하지 않았습니다.
- **직접 검증하지 않은 항목**:
  - 실제 GPU 렌더링 파이프라인 상의 셰이더 출력 결과 및 3D 화면 품질
  - 모니터 화면상에서 체감되는 실제 조준경(ADS) 줌 인/아웃 및 FOV 전환의 시각적 느낌
  - 장시간 플레이 시의 실제 프레임레이트(FPS) 및 스터터링 체감
  - 오디오 출력 장치를 통한 실제 3D 사운드 재생 체감
  - 위 항목들은 수동 GUI 조작 환경에서 직접 확인하지 않았으며, 헤드리스 단위 테스트, 가상 노드패스 및 상태 머신 시뮬레이션을 통해 로직 및 데이터 일관성을 검증하였습니다.
- **기존 사용자 수정 보존 확인**:
  - AR 조준사격 반동 증가 및 마우스 수동 반동 제어/흡수 로직 보존
  - AR 장전 속도 및 장전 상태 HUD 텍스트 보존
  - 플로팅 데미지 텍스트 투명 배경 및 헤드샷 적색 텍스트(headshot 문구 제외) 서식 보존
  - `rankings.json` 파일에 테스트 기록 미반영 보존
