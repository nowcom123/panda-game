# Antigravity 협업 결과 — 3단계: 드롭·랜덤 옵션·탈출 확보

- 모델: Gemini 3.8 Flash (High)
- 일시: 2026-10-24
- 프로젝트: `panda-game`

---

## 1. 작업 개요 및 완성된 흐름

RPG 3단계(적 처치 시 드롭, 등급별 랜덤 옵션 롤링, 미확보 탐험 가방, 바닥 상호작용, 안전한 영구 확보 및 사망 시 소실 트랜잭션, 3분할 인벤토리 탭 및 HUD UI)를 성공적으로 구현하고 전체 검증을 완료했습니다.

```
[ 일반 적 / 정예 / 보스 처치 ]
          │
          ▼ (일반 20%, 정예 100%, 보스 무기1+재료1 100% 드롭)
[ 3D 월드 바닥에 표시 (단순 형상 + 등급색, 최대 40개 제한 관리) ]
          │
          ▼ [E] 키 획득 (2.5m 거리, 1.5m 층고, 벽 너머 LOS 검사 통과 시)
[ 이번 탐험의 미확보 가방 보관 (최대 24칸 제한, 중복 UID 원천 차단) ]
          │
          ├────────────────────────────────┬───────────────────────────────┐
          ▼                                ▼                               ▼
   [ 계속 탐험 진행 ]             [ 비상 관문 탈출 선택 ]           [ 사망 / 포기 / 시간초과 ]
 (바닥만 정리, 가방 유지)        (원자적 프로필 병합 & 저장)       (미확보 전리품만 전액 소실)
                                           │                       (기존 영구 장비/통화 보존)
                                           ▼
                                 [ 영구 보관함으로 이관 ]
```

---

## 2. 생성 및 변경 파일 목록

허용된 파일 범위 내에서만 구현 및 연동을 진행했으며, 기존 게임 시스템 및 이전 단계의 변경 사항을 완벽히 보존했습니다.

1. **`rpg/loot.py` (신규)**
   - 엔진 독립 드롭 생성기: `roll_loot(catalog, rng=None, *, enemy_tier="normal", stage=1) -> list[ItemInstance]`.
   - 주입 가능한 RNG 지원 (테스트 재현성 보장, 전역 random 상태 의존 없음).
   - 드롭 확률 및 가중치:
     - 일반 적: 20% 확률로 1개 드롭.
     - 정예 적: 1개 확정 드롭.
     - 보스 적: 무기 1개 + 재료 1묶음 확정 드롭.
     - 전리품 종류: 무기 60%, 재료 40%.
     - 무기 4종 균등 분배. 등급 가중치: 일반(common 50, uncommon 40, rare 10), 정예(uncommon 35, rare 55, epic 10), 보스(rare 70, epic 30). 전설은 제외.
     - 옵션 개수: common 0개, uncommon 1개, rare 2개, epic 3개.
     - 옵션 확정 수치 범위 및 3자리 반올림: `damage_mult`(1.050~1.200), `reload_time_mult`(0.850~0.950), `weakpoint_mult`(1.050~1.250). 단일 아이템 내 중복 affix 배제.
     - 아이템 레벨: `max(1, stage)`.
     - 재료: `scrap_metal`, `bone_fragment` 중 1종, 일반/정예 수량 1~3, 보스 수량 3~6.
     - 각 아이템 UID는 독립적인 `uuid4`로 고유 생성.

2. **`rpg/run_loot.py` (신규)**
   - `RunLootBag`: 이번 탐험의 인메모리 미확보 전리품 컨테이너 (영구 프로필 필드가 아닌 탐험 런 인메모리 상태로 분리).
   - 최대 용량 24칸 제한 (`MAX_RUN_LOOT_CAPACITY = 24`), 가득 찬 경우 바닥 물건 보존 및 획득 거부.
   - 가방 내 중복 UID 및 영구 프로필 보유 아이템 UID 획득 차단.
   - `extract(session)` 원자적 트랜잭션:
     1) 영구 프로필 복제 (`copy.deepcopy`)
     2) 미확보 전리품 병합
     3) 카탈로그 스키마 무결성 검증 (`candidate.validate`)
     4) 디스크 원자적 저장 (`store.save`)
     5) 성공 시에만 세션 프로필/캐시 갱신 및 pending 비우기
   - 저장 실패 시 pending 아이템을 보존하여 `last_save_error` 기록 및 재시도 허용.
   - 중복 탈출 콜백 호출 시 안전한 무해화 (이미 확보된 런에 재보상 지급 차단).
   - `clear_on_death()`: 사망 시 pending만 버리고 기존 영구 장비/통화는 안전하게 보존.
   - `abandon()`: 명시적 탐험 포기 처리.

3. **`rpg/loot_world.py` (신규)**
   - `LootWorldItem`: 3D 바닥 드롭 인스턴스 (무기: 발광 다이아몬드 크리스탈, 재료: 금속 잉곳/캐니스터 단순 형상 + 등급별 색상, 동적 광원 0%, per-frame 메시 재생성 0%).
   - `LootWorldManager`:
     - 전체 바닥 RPG 드롭 표시 최대 40개 상한 관리 (초과 시 가장 오래된 미획득 드롭을 FIFO 방식으로 정리하여 렌더 부하 방지).
     - 상호작용 검사: 플레이어 거리 2.5m 이내, 수직 층고 1.5m 이내, `check_line_of_sight` 및 `get_nearby_colliders`를 통한 벽 너머 획득 차단.
     - `try_pickup`: 가방 수용 가능 시에만 월드 노드 정리 및 가방 추가; 가방 가득 참 시 바닥에 보존.
     - `clear_world_drops()`: 스테이지 전환 시 바닥 표시만 일괄 정리.

4. **`rpg/run_loot_ui.py` (신규)**
   - `RunLootUIPanel`: 인벤토리 모달 내 세 번째 탭 `[ 이번 탐험 (미확보) ]` 읽기 전용 검사 패널.
   - 상단 헤더: `[ 이번 탐험 미확보 전리품 가방 : n / 24 ]` 및 탈출 시 영구 확보/사망 시 소실 안내.
   - 좌측: 획득 전리품 목록 (등급별 색상, 이름, 수량, 옵션 개수, 7개 단위 페이지네이션).
   - 우측: 전리품 상세 제원 (등급, 분류, 아이템 레벨, 부여된 추가 무작위 옵션 수치 및 계수).
   - 하단 버튼: `[ 탈출 후 영구 소유 및 장착 가능 ]` (비활성화 상태로 고정하여 탐험 중 장착 불가 규칙 명시).

5. **`rpg/__init__.py` (변경)**
   - `roll_loot`, `roll_affixes`, `RunLootBag`, `MAX_RUN_LOOT_CAPACITY`, `LootWorldItem`, `LootWorldManager` export 추가.

6. **`monster_director.py` (변경)**
   - 몬스터 사망 시 RPG 전리품 드롭 훅 연결:
     - 일반 몬스터: `roll_loot(catalog, enemy_tier="normal", stage=stage)`
     - 정예 몬스터: `roll_loot(catalog, enemy_tier="elite", stage=stage)`
     - 보스 (`CableOverlordBoss`): `roll_loot(catalog, enemy_tier="boss", stage=stage)`
   - `_rpg_loot_dropped` 플래그로 몬스터당 1회만 드롭 보장 (시체 갱신, DoT 틱 등 중복 드롭 방지).
   - 보스의 기존 소모품 3회 생성 루프 외부에 배치하여 보스 전리품(무기 1 + 재료 1)이 정확히 1회만 드롭되도록 격리.
   - 사격장/테스트 모드(`g.is_test_mode`)에서는 드롭 완전 차단.

7. **`game.py` (변경)**
   - `run_loot_bag` 및 `loot_world` 초기화 및 연결.
   - [E] 키 상호작용 단일 타겟팅 로직:
     - 보급 상자, 전술 소모품 드랍, RPG 전리품 중 플레이어와 **가장 가까운 단 1개의 대상**만 타겟팅.
     - HUD 프롬프트 텍스트와 실제 [E] 키 획득 대상이 100% 일치하도록 보장.
   - `restart_game()`: 새 런 진입 시 새 가방 생성, 바닥 정리, HUD 0/24 리셋.
   - `advance_to_next_stage()`: 바닥 드롭만 정리하고 `run_loot_bag`은 유지.
   - `clear_projectiles()`: 바닥 드롭 노드 정리.
   - `trigger_victory()`:
     - 탈출 시 `run_loot_bag.extract(self.rpg_session)` 호출.
     - 저장 성공 시: 승리 화면 표시 및 랭킹 저장 (`★ 전리품 n개 영구 확보 완료! ★`).
     - 저장 실패 시: 승리/랭킹 기록을 차단하고 `show_extraction_error_dialog` 표시.
   - `trigger_game_over()`:
     - `self.run_loot_bag.clear_on_death()` 호출로 미확보 전리품만 소실.
     - 게임 오버 화면에 잃은 전리품 개수 명시 및 영구 장비는 보존되었음을 명시.

8. **`ui_manager.py` (변경)**
   - 우측 하단 HUD에 `미확보 전리품  n / 24` 라벨 추가 및 실시간 동기화.
   - 인벤토리 모달 상단 탭을 3분할로 재배치: `[ 소모품 배낭 ]`, `[ 무기 / 장비함 ]`, `[ 이번 탐험 (미확보) ]`.
   - 탭 전환 시 소모품 위젯, 영구 장비 패널, 탐험 전리품 패널 간 상호 배타적 숨김/표시 (위젯 겹침 0%).
   - `show_stage_clear_shop`: 관문 도달 시 `심연 더 깊이 진입 (계속 탐험)`과 `★ 전리품 확보하고 탈출 ★` 버튼 및 미확보 전리품 개수·규칙 안내.
   - `show_extraction_error_dialog`: 탈출 저장 실패 시 `[ 저장 재시도 ]`와 `[ 보상 포기 후 복귀 ]` 분리 모달.

9. **`tests/test_rpg_loot.py` (신규)**
   - 드롭율, 적 등급별 가중치, 옵션 개수 및 3자리 반올림, 중복 affix 배제, 재료 수량, UID 고유성, 스테이지 레벨 스케일링 등 유닛 테스트 7건.

10. **`tests/test_rpg_loot_integration.py` (신규)**
    - 가방 24개 한도, 중복 UID 차단, 영구 아이템 중복 획득 차단, 원자적 추출 트랜잭션, 저장 실패 시 pending 보존 및 재시도, 사망 시 pending만 소실 및 영구 장비 보존, 탐험 포기, 바닥 40개 상한 FIFO 정리, 거리 및 층고 필터링 등 통합 테스트 7건.

11. **`support/antigravity/20261024-rpg-loot/verify_loot.py` (신규)**
    - 엔진 독립 E2E 기능 검증 스크립트.

12. **`support/antigravity/20261024-rpg-loot/verify_loot_ui.py` (신규)**
    - 1600×900 오프스크린 UI 렌더링 및 캡처 검증 스크립트.

13. **`support/antigravity/20261024-rpg-loot/loot_ui_1600x900.png` (신규 캡처)**
    - 1600×900 해상도 이번 탐험 전리품 UI 패널 오프스크린 캡처 이미지.

---

## 3. 실제 검사 및 테스트 결과

### A. 유닛 테스트 전체 실행
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe -m unittest discover -s tests
  ```
- 결과:
  ```text
  Ran 240 tests in 1.015s
  OK
  ```
  - 기존 226개 테스트 + 신규 전리품/월드/트랜잭션 테스트 14건 = **총 240건 전체 정상 통과 (0건 실패)**.

### B. 독립 E2E 검증 스크립트 실행
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe support/antigravity/20261024-rpg-loot/verify_loot.py
  ```
- 결과:
  ```text
  === RPG Phase 3: Loot, World Interaction & Extraction Verification ===
  [OK] Catalog loaded with 6 item definitions.
  [OK] Isolated sandbox session initialized at: ...\profile.json
  [OK] Normal enemy drop rate verified: 19.0%
  [OK] Elite enemy guaranteed drop verified.
  [OK] Boss enemy guaranteed weapon + material drops verified.
  [OK] Affix rules (counts, 3-decimal rounding, non-duplication) verified.
  [OK] Run bag 24-item capacity limit enforced.
  [OK] Duplicate and permanent item UID rejection verified.
  [OK] World loot 40-item ground cap and FIFO oldest pruning verified.
  [OK] World loot distance (2.5m) and height (1.5m) filtering verified.
  [OK] Stage transition: floor drops cleared while run bag preserved.
  [OK] Death mechanics: pending loot discarded, permanent profile intact.
  [OK] Extraction save failure resilience: pending items preserved for retry.
  [OK] Extraction success: items merged, validated, and persisted atomically.
  [OK] Extraction idempotency verified.
  === All RPG Phase 3 Verifications Passed Successfully! ===
  ```

### C. 1600×900 UI 오프스크린 캡처 검증
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe support/antigravity/20261024-rpg-loot/verify_loot_ui.py
  ```
- 결과:
  ```text
  === Running Offscreen Loot UI & Resolution Verification (1600x900) ===
  [OK] In-run bag populated and HUD text verified.
  [OK] 3-way inventory tab isolation verified (no widget overlap).
  [OK] Captured 1600x900 In-Run Loot UI preview: ...\loot_ui_1600x900.png (260361 bytes)
  [OK] Tab return transitions verified.
  [OK] Stage clear shop escape option and loot status verified.
  === Offscreen Loot UI Verification Passed! ===
  ```
  - 생성된 이미지: `support/antigravity/20261024-rpg-loot/loot_ui_1600x900.png` (260,361 바이트).
  - 3개 탭 전환 간 기존 소모품 패널, 영구 장비 패널, 탐험 전리품 패널 간 겹침 현상 없이 깔끔하게 분리 표시됨을 확인.

---

## 4. 검증 체크리스트 충족 현황

| 검증 항목 | 충족 여부 | 세부 내용 |
| :--- | :---: | :--- |
| **주입 RNG 기반 생성기** | **충족** | 난수 생성기를 주입받아 전역 random 상태 영향 없이 20% 확률, 확정 드롭, 등급별 옵션/수량 생성 |
| **등급별 옵션 규칙** | **충족** | common 0, uncommon 1, rare 2, epic 3개 옵션 및 3자리 확정 계수 반올림, 중복 배제, 전설 미생성 |
| **가방 한도 및 중복 방지** | **충족** | 24개 한도 초과 시 획득 거부 및 바닥 보존, 가방/영구 프로필 간 중복 UID 획득 차단 |
| **원자적 탈출 트랜잭션** | **충족** | 프로필 복제 → 전리품 병합 → 검증 → `store.save` 성공 시에만 세션 갱신 및 pending 비우기 |
| **저장 실패 복원력** | **충족** | 디스크 저장 실패 시 pending 아이템 보존, 재시도 지원, 승리/랭킹 중복 기록 차단 |
| **층 이동 vs 사망 규칙** | **충족** | 층 이동 시 바닥 표시만 정리하고 가방 유지, 사망 시 미확보만 소실하고 영구 장비는 100% 보존 |
| **몬스터 드롭 단일 호출** | **충족** | 일반/정예/보스 사망 시 `_rpg_loot_dropped` 플래그로 1회만 호출 (보스 소모품 3회 루프 외부 격리) |
| **사격장 드롭 차단** | **충족** | `is_test_mode` 환경에서 전리품 드롭 및 저장 일체 차단 |
| **E키 단일 타겟팅** | **충족** | 상자, 소모품, RPG 전리품 중 최단거리 대상 1개만 처리하며 안내 텍스트와 획득 대상 일치 |
| **벽 너머 획득 방지** | **충족** | 2.5m 거리, 1.5m 층고, `check_line_of_sight`를 통한 벽체 가림 판정 |
| **바닥 40개 상한 관리** | **충족** | 40개 초과 시 가장 오래된 바닥 드롭을 FIFO 방식으로 정리 (가방 아이템 영향 없음) |
| **임시 디렉터리 샌드박스** | **충족** | 모든 검증 및 테스트는 `tempfile.TemporaryDirectory` 내부 세이브만 사용 |
| **1600×900 UI 캡처** | **충족** | 오프스크린 렌더링으로 `loot_ui_1600x900.png` 캡처 완료 |

---

## 5. 남은 문제 및 후속 제언

1. **전설 장비 및 세트 효과 (다음 단계)**
   - 이번 단계에서는 지시서 규칙에 따라 전설 등급 생성을 제외했습니다. 추후 전설 고유 지속 효과(유니크 퍽 결합) 구현 시 전설 드롭 테이블을 활성화할 수 있습니다.
2. **자동 스택 합치기 (향후 편의성)**
   - 현재는 지시서 정책에 따라 재료 묶음 1개가 1칸을 차지하도록 단순화되어 있습니다. 향후 배낭 정리 기능(자동 스택 병합)이 추가되면 가방 공간 활용성이 더욱 개선될 것입니다.

---

> **안내**: Codex 검토를 위해 **"안티 작업 끝"**을 전달하시면 됩니다.

