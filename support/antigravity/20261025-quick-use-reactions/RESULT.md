# 빠른 소모품 선택창 · 몬스터별 회피/방어 및 반격 · 대응 퍽 구현 결과 보고서 (Antigravity)

**작업 일시:** 2026-10-26  
**작업자:** Antigravity  
**협업자:** Codex  

---

## 1. 완료 범위 요약

Codex가 사전 구현한 계산 모듈(`combat/reactions.py`: `REACTION_PROFILES`, `counter_stats`, `reaction_chance`, `guarded_damage`)과 기본 단위 테스트(`tests/test_reaction_rules.py`)를 재사용하여, 백틱(`` ` ``) 빠른 소모품 선택창, 5종 몬스터 전용 회피/방어 및 반격 전투 연결, 신규 대응 퍽 2종 및 상태 카드 UI, 맹독 상태이상 HUD를 모두 완성했습니다.

### A. 백틱(`` ` ``) 빠른 소모품 선택창 (`rpg/quick_use.py`, `player_controller.py`, `game.py`)
- **전용 `QUICK_USE` 상태**:
  - PLAYING 상태에서 백틱 키를 누르고 있는 동안 즉시 `QUICK_USE` 상태로 전환.
  - 적 이동, 공격, 투사체, 탐험 시간, 불릿타임 잔여시간을 일시정지하고 UI만 갱신.
  - 마우스 잠금 해제 및 종료 시 중앙 재정렬로 델타 튐 방지.
  - 조준/사격 자동 중단.
- **실효 단축키 필터링 (`get_quick_use_items`)**:
  - RPG 모드 기준 1/2(주/보조 무기)에 의해 단축키에서 밀려난 `medkit`(응급키트), `adrenaline`(아드레날린) 포함.
  - 3/4 단축키로 즉시 사용 가능한 `ammo_pack`(탄약팩), `frag_grenade`(수류탄) 제외.
  - `quick_slot=None`인 `combat_stim`(공격강화제) 포함.
  - 수량 0인 소모품 및 장비/재료/미확보 전리품 완전 제외.
- **UI 및 입력 제어**:
  - 중앙 취소 영역(반경 0.22, pos=(0, 0))과 원형/카드 배치.
  - 마우스 호버 및 휠 순환 선택 지원 (`handle_weapon_next/prev` 연동, 이 상태에서 무기 교체 차단).
  - 키 릴리즈 시 선택된 소모품 1회 소비 (`PlayerController.use_item` 재사용).
  - 중앙 취소 영역에 있거나 ESC 입력 시 소모 없이 닫기.
  - 키 반복(repeat), 동일 프레임 release 중복에도 1회만 소비 보장.
  - 이름 입력 창(타이틀/삭제창), 일시정지, 사격장, 탈출 대기, 사망/승리/다음 층/앱 종료 시 안전한 취소 및 정리.

### B. 반응 공통 전투 연결 (`combat_system.py`, `monster_director.py`, `monster.py`)
- **샷건/연사 판정 캐싱**:
  - `shoot()` 시 discharge 단위로 `_discharge_reactions` 딕셔너리를 관리.
  - 동일한 발사(shot_id)에서 대상 몬스터(`id(monster)`)당 반응 판정을 1회만 수행하고 결과를 캐시.
  - 샷건 8펠릿이 적중해도 8번의 반격이나 중복 회피가 발생하지 않음.
  - 최초 적중 펠릿이 0번이 아니어도 정상 동작.
- **파수견 중복 RNG 차단**:
  - `take_damage(dmg, ..., skip_dodge=True)` 플래그를 추가하여 내부 35% RNG와 외부 반응 판정이 이중으로 돌지 않도록 보장.
- **전방 120도 가드 판정**:
  - 몬스터 전방 벡터와 피격 벡터 내적 `cos(60°) = 0.5` 이상일 때만 방어 적용.
  - 후방 및 측면 타격은 정상 피해 적용 및 반격 발동 차단.
  - 방어 성공 시 뱀은 60% 피해 감소, 골렘(오크)은 65% 피해 감소. 방어 시간 동안 지속되는 전방 총격 피해 감소.
  - 방어 성공 시 전방 펠릿은 샷건 3발 스턴 카운트에서 제외 (측후방 피격은 정상 적용).
- **0-피해 회피 무효화 처리**:
  - 회피 성공 시 `dmg = 0` 처리.
  - 흡혈(`hp_drain_accum`), 연계 타격, 헤드샷 보상, 스태거, 혈흔/피격 이펙트 일체 차단.
- **DOT / 환경 피해 분리**:
  - 직접 발사한 총탄에만 반응 판정 적용. 독(DOT), 폭발, 환경 피해에는 새 반응 발동 차단.

### C. 몬스터 5종 고유 연출 및 반격 (`monster.py`, `monster_director.py`)
1. **파수견 (`SkeletalDobermanHellhound`)**: 도약 회피 (0.35초), 기본 35% 확률, 단일 판정.
2. **마녀 (`AlluringAshWitch`)**: 
   - 2.5~4m 측면 순간이동 회피 (0.25초), 쿨다운 4.5초.
   - 플레이어 최소 2m 거리 유지, 벽 충돌/LOS/바닥높이 검증. 유효 후보 없으면 회피 취소 + 정상 피해.
3. **해골 (`TallSkeletonMonster`)**: 
   - 몸통/팔/다리 뼈 흩어짐 및 0.45초 내 원래 위치 재결합 회피, 쿨다운 5.0초.
   - 원래 관절 및 히트박스 참조 보존, 사망/파괴 시 부품 원복 보장.
4. **뱀 (`LongBlackSerpent`)**: 
   - 전방 방어 (0.40초, 60% 감소) + 0.85초 녹색 부채꼴 예고 (7m, ±25°).
   - 예고 방향 고정 발사: 10 즉발 피해 + 3초간 초당 4 피해 맹독 브레스.
   - 독 지속시간 갱신 (중첩 차단).
5. **골렘 역할의 진흙 오크 (`AbominableMudOrc`)**: 
   - 전방 방어 (0.60초, 65% 감소) + 1.0초 바닥 원형 예고 (8m).
   - 24 지진 피해 + 카메라 진동. 플레이어 발높이 0.75m 이상 점프 또는 범위 이탈로 회피 가능.
   - 기존 slam 쿨다운 최소 1.0초 보장으로 중첩 차단.
- **LOD 분리**:
  - `monster_director.py`에서 LOD 프레임 스킵 이전 매 틱마다 `update_reactions(dt)`를 호출하여 원거리나 저사양에서도 정확한 world_dt 시간 처리 보장.

### D. 플레이어 대응 능력치 및 신규 퍽 (`perks.py`, `ui_manager.py`)
- **새 능력치**:
  - `회피 억제 (evasion_suppression)`: 적 회피 확률에서 %p 차감.
  - `방어 관통 (guard_penetration)`: 적 방어 피해 감소율 무시.
- **신규 퍽 2종**:
  - `precision_training` (정밀 조준): 희귀도 RARE, max_level 3, 레벨당 회피 억제 +5/10/15%p.
  - `guard_breaker` (방어 파쇄): 희귀도 RARE, max_level 3, 레벨당 방어 관통 +10/20/30%.
  - 3레벨 도달 시 퍽 드로우 풀(`draw_random_perks`)에서 자동 제외.
- **인벤토리 UI 상태 카드 표시**:
  - 인벤토리 좌측 상태 카드 하단에 `• 회피 억제: {ev_supp}%p · 방어 관통: {gd_pen}%` 표시 추가.
  - 기존 레이아웃/유물/장비 슬롯 겹침 없음.

### E. 플레이어 맹독 상태이상 및 HUD (`player_controller.py`, `game.py`, `ui_manager.py`)
- `PlayerController.apply_poison(duration=3.0, dps=4.0)`: 중첩 대신 지속시간 3초로 갱신.
- `game.py`: PLAYING 상태에서 `world_dt` 기반 독 피해(초당 4) 및 사망 처리.
- `UIManager`: HUD 상단 체력/스태미나 바 아래에 `[ ☣ 맹독 감염 : 2.8s (-4 HP/s) ]` 상태 텍스트 실시간 표시.
- 층 전환, 게임 재시작, 타이틀 복귀 시 플레이어 독 상태 자동 제거.

---

## 2. 변경 파일 목록

| 파일 | 변경 요약 |
|---|---|
| `rpg/quick_use.py` | (신규) 실효 단축키 필터링, 원형/카드 UI 패널, QuickUseManager 수명주기/일시정지/입력 제어 |
| `combat_system.py` | shot_id 캐시 1회 판정(`_resolve_monster_reaction`), 전방 120도 판정(`_is_frontal_hit`), 0-피해 회피 차단, 샷건 스턴 제외 |
| `monster.py` | 5종 reaction_role 클래스/인스턴스 할당, 회피/방어/반격 연출(부채꼴/원형 예고, 마녀 텔포, 해골 분해/원복, 뱀 브레스, 오크 지진) |
| `monster_director.py` | LOD 프레임 스킵 전 논리 틱마다 `update_reactions` 호출, 회피/방어/반격 중 일반 공격/스킬 중첩 차단 |
| `perks.py` | `precision_training`, `guard_breaker` 등록, 퍽 레벨별 설명 및 수치 계산, max_level 도달 시 드로우 제외 |
| `player_controller.py` | 맹독 타이머/dps 및 `apply_poison`, 백틱 입력 이벤트 등록, 리셋 시 독 초기화 |
| `ui_manager.py` | 맹독 HUD 노드 및 갱신 메서드, 인벤토리 상태 카드에 회피 억제 / 방어 관통 표시 |
| `game.py` | QuickUseManager 연동, 백틱 입력 바인딩, 휠 선택 순환, QUICK_USE 일시정지, 독 데미지 및 사망/정리 처리 |
| `tests/test_quick_use.py` | (신규) 백틱 단축키 필터링, 1회 소비, ESC/취소, 휠 순환 등 7개 단위 테스트 |
| `tests/test_monster_reactions.py` | (신규) 샷건 8펠릿 단일 판정, 파수견 중복 RNG 차단, 마녀/해골/뱀/오크 반응, 퍽 드로우 등 9개 단위 테스트 |
| `support/antigravity/20261025-quick-use-reactions/verify_reactions_ui.py` | (신규) 오프스크린 다중 해상도(1280×720, 2294×1201) 통합 검증 및 시각 캡처 스크립트 |

---

## 3. 검증 결과

### 1) 단위 테스트 전체 스위트 (320개 전원 통과)
```bash
.venv\Scripts\python.exe -m unittest discover tests
```
- **결과:** `Ran 320 tests in 2.432s - OK`
- 기존 304개 테스트 + 신규 16개 테스트(Quick-Use 7개, Monster Reactions 9개) 100% 통과.

### 2) 독립 모듈 단위 테스트
- `tests/test_reaction_rules.py`: 4개 테스트 통과 (Codex 계산 모듈).
- `tests/test_quick_use.py`: 7개 테스트 통과.
- `tests/test_monster_reactions.py`: 9개 테스트 통과.

### 3) 오프스크린 다중 해상도 캡처 (`verify_reactions_ui.py`)
```bash
.venv\Scripts\python.exe support\antigravity\20261025-quick-use-reactions\verify_reactions_ui.py
```
- **1280×720 & 2294×1201 두 해상도 실제 크기 검증 완료**:
  - `inventory_stats_1280x720.png` (1280×720, 168,869 bytes)
  - `inventory_stats_2294x1201.png` (2294×1201, 522,046 bytes)
  - `quick_use_1280x720.png` (1280×720, 306,227 bytes)
  - `quick_use_2294x1201.png` (2294×1201, 937,081 bytes)
  - `monster_reaction_1280x720.png` (1280×720, 759,369 bytes)
  - `monster_reaction_2294x1201.png` (2294×1201, 2,329,885 bytes)

### 4) Windows CRCRLF (`\r\r\n`) 검사
- 검사 대상: 수정 및 신규 생성된 파이썬 파일 11개 전체.
- **결과: CRCRLF 0건** (CRLF 및 pure LF 규격 준수).

---

## 4. 보존 내역
- 기존 사용자 세이브 파일 및 `rankings.json` 일체 무변경 보존.
- `consumables_root` 부모 단위 숨김 보존.
- git commit / reset / clean 일체 미수행.

---

## 5. 인계 사항
- 모든 구현 및 검증이 완료되었습니다.
- 사용자께서는 Codex에 **"안티 작업 끝"**을 전달하여 최종 통합 검토를 진행하시면 됩니다.

