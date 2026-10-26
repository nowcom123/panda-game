# Antigravity 협업 결과 — 2단계: 장비 인벤토리와 실제 전투 적용

- 모델: Gemini 3.8 Flash (High)
- 일시: 2026-10-24
- 프로젝트: `panda-game`

---

## 1. 생성 및 변경 파일 목록

허용된 범위 내에서만 구현 및 연동을 진행했으며, 기존 밸런스 및 워킹 트리 변경 사항을 완전히 보존했습니다.

1. **`rpg/session.py` (신규)**
   - `RPGSession`: 영구 프로필 로드, 기본 무기 지급(starter_loadout_v1 정책), 장착/해제/잠금 원자적 저장 및 롤백 관리.
   - `resolve_weapon_config`를 통한 effective config 캐싱.
   - 마지막 장착 무기 해제 방지(무장 해제 방지) 및 재료 장착 거부, 동일 UID 중복 장착 거부.
2. **`rpg/equipment_ui.py` (신규)**
   - `EquipmentUIPanel`: 인벤토리 모달 내부 장비 관리 패널.
   - 상단 주/보조 무기 슬롯 카드 (클릭으로 비교 대상 슬롯 선택).
   - 좌측 스크롤/페이지네이션 보유 아이템 목록 (이름, 등급, 레벨, 장착 상태, 잠금 🔒).
   - 우측 상세 정보: 부여된 옵션, 실제 공격력/장전시간/약점배율 및 대상 슬롯 대비 변화량 (장전 시간 단축은 가속(좋음)으로 표시).
   - 하단 4대 액션 버튼: `주 무기 장착`, `보조 무기 장착`, `장착 해제`, `잠금/해제`.
3. **`combat_system.py` (변경)**
   - `rpg_session` 주입 및 연동 (`set_rpg_session`, `sync_with_rpg_session`, `get_current_weapon_config`).
   - `active_slot`("primary"/"secondary"), `active_item_uid` 별도 분리.
   - 같은 무기 종류라도 UID별로 독립적인 탄창 잔탄/슬라이드 잠금 관리 (`item_states`).
   - 예비탄은 무기 종류별(`reserve_ammo_pools`)로 공유하여 슬롯 스왑 시 탄약 복제 차단.
   - 장전/ADS 도중 슬롯 교체 시 안전 취소 (탄약 복제 방지).
   - 사격 레이캐스트, 펠릿, 도탄 기본 피해, 장전 속도/애니메이션에서 effective config 일관 적용.
   - 미장착 무기 직접 선택 차단 (장착된 슬롯 무기만 선택 가능).
   - `rpg_session`이 없는 환경(기존 테스트 모드/사격장)에서는 기존 로직으로 안전하게 fallback.
4. **`ui_manager.py` (변경)**
   - 인벤토리 모달 상단에 `[ 소모품 배낭 ]` / `[ 무기 / 장비함 ]` 탭 추가.
   - 탭 전환 시 기존 소모품 위젯과 `EquipmentUIPanel` 간 가시성 제어.
   - 기존 소모품 사용, 퀵슬롯 안내, ESC/TAB 닫기 기능 보존.
5. **`game.py` (변경)**
   - `save_store` 및 `save_path` 주입 지원 (ShowBase 생성자에 넘기지 않고 사전 추출).
   - 저장소 무결성 검증: 손상/미지원 버전 세이브 감지 시 일반 게임 시작 차단 및 알림.
   - 인게임 숫자키 `1`, `2` 입력을 주/보조 무기 슬롯 전환으로 라우팅 (소모품 퀵슬롯 3, 4 보존).
   - 테스트 모드 진입 시 프로필에 영향을 주지 않도록 격리.
6. **`rpg/__init__.py` (변경)**
   - `RPGSession`, `STARTER_UNLOCK_KEY`, `resolve_weapon_config` re-export.
7. **`tests/test_rpg_equipment.py` (신규)**
   - 기본품 지급 정책, 재시작 시 중복 방지, 장착/해제/잠금 영구 저장, 마지막 무기 해제 거부, 손상 파일 보존 등 단위 테스트 7건.
8. **`tests/test_rpg_equipment_combat.py` (신규)**
   - 같은 AR 2자루 피해 분리, 약점/장전시간 옵션 반영, 퍽과 옵션 누적 방지, 탄약 복제 방지, 예비탄 공유, 미장착 무기 차단 등 전투 통합 테스트 6건.
9. **`support/antigravity/20261024-rpg-equipment/verify_equipment.py` (신규)**
   - 샌드박스 E2E 기능 검증 스크립트.
10. **`support/antigravity/20261024-rpg-equipment/verify_equipment_ui.py` (신규)**
    - 1600x900 오프스크린 렌더링 및 UI 캡처 스크립트.
11. **`support/antigravity/20261024-rpg-equipment/equipment_ui_1600x900.png` (신규 캡처)**
    - 1600x900 해상도 장비 UI 패널 오프스크린 캡처 이미지.

---

## 2. 사용법 요약

```python
from rpg import load_catalog, SaveStore, RPGSession
from combat_system import CombatSystem

# 1. 세션 초기화 (starter loadout 정책 자동 적용)
catalog = load_catalog()
store = SaveStore("profile.json", catalog)
session = RPGSession(store, catalog)
session.initialize()

# 2. CombatSystem 연동
combat = CombatSystem(...)
combat.set_rpg_session(session)

# 3. 주/보조 슬롯 전환 및 사격
combat.switch_to_slot("primary")    # 주 무기 활성화 (1번 키)
combat.switch_to_slot("secondary")  # 보조 무기 활성화 (2번 키)
combat.next_weapon()                # 채워진 슬롯 간 토글 (Q / 휠)

# 4. 장비 UI 모달
# [I] 또는 [TAB] 키로 인벤토리 열기 -> 상단 [무기 / 장비함] 탭 클릭
# 주/보조 슬롯 선택 후 원하는 무기 [주 무기 장착] / [보조 무기 장착] 클릭
```

---

## 3. 실제 테스트 및 검증 결과

### A. 유닛 테스트 전체 실행
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe -m unittest discover -s tests
  ```
- 결과:
  ```text
  Ran 224 tests in 0.951s
  OK
  ```
  - 기존 211개 테스트 + 신규 장비/전투 통합 테스트 13건 = **224건 전체 정상 통과 (0건 실패)**.

### B. 독립 E2E 검증 스크립트
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe support\antigravity\20261024-rpg-equipment\verify_equipment.py
  ```
- 결과:
  ```text
  === RPG Phase 2: Equipment & Combat Integration Verification ===
  [OK] Catalog loaded with 6 item definitions.
  [OK] Isolated sandbox store at: ...\profile.json
  [OK] Starter loadout verified: 4 starter weapons granted; PISTOL / SHOTGUN equipped.
  [OK] Session restart verified: No duplicate weapons granted.
  [OK] Protection verified: Unequipping the last weapon rejected.
  [OK] Combat damage separation verified: Modded AR (53.2) vs Plain AR (38.0).
  [OK] Ammo isolation and reload cancellation verified (no ammo duplicated).
  [OK] Direct switch to unequipped weapons properly blocked.
  [OK] Equipment UI model verified: 5 items sorted and formatted.
  === All RPG Equipment & Combat Verifications Passed Successfully! ===
  ```

### C. 1600x900 오프스크린 UI 렌더링 및 캡처 검증
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe support\antigravity\20261024-rpg-equipment\verify_equipment_ui.py
  ```
- 결과:
  ```text
  === Running Offscreen Equipment UI & Resolution Verification (1600x900) ===
  [OK] Switched to equipment tab.
  [OK] Captured 1600x900 Equipment UI preview: ...\equipment_ui_1600x900.png (266782 bytes)
  [OK] ESC / TAB closing verified.
  === Offscreen Equipment UI Verification Passed! ===
  ```
  - 1600×900 해상도에서 텍스트 잘림, 버튼 겹침 없이 장비 슬롯 카드, 보유 목록, 상세 제원 비교 패널 정상 렌더링 확인.
  - ESC 및 TAB 키 입력 시 즉시 인벤토리가 닫히고 `PLAYING` 상태로 정상 복귀.

---

## 4. UI 캡처 파일

- 파일 경로: `support/antigravity/20261024-rpg-equipment/equipment_ui_1600x900.png`
- 해상도: 1600 × 900
- 내용: `[소모품 배낭]` / `[무기 / 장비함]` 상단 탭, 주/보조 슬롯 선택 카드, 보유 무기 리스트(등급/레벨/장착태그), 확정 옵션 효과 및 슬롯 대비 스탯 변화량(녹색/적색), 4대 조작 버튼 정상 표시.

---

## 5. 미완료 사항 및 주의점

- 이번 2단계 범위에 포함되지 않은 내용 (향후 3단계 이후):
  - 던전 루팅 드롭 확률 테이블에 따른 몬스터 처치 시 실시간 아이템 획득.
  - 상점 골드 거래, 장비 분해 및 재료를 통한 무기 제작 시스템.
  - 랜덤 옵션 추첨(RNG 롤링) 생성기.
- 주의사항:
  - 일반 게임에서 1번과 2번 키는 주/보조 무기 슬롯 전환으로 동작하며, 3번과 4번 키는 기존 소모품 퀵슬롯으로 유지됩니다.
  - 테스트 모드(사격장) 진입 시에는 사용자의 프로필에 영향을 주지 않도록 기존 4종 무기 전체를 자유롭게 시험할 수 있는 모드로 자동 격리됩니다.

