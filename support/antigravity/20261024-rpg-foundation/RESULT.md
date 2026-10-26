# Antigravity 협업 결과 — 1단계: 아이템 데이터와 저장 기반

- 모델: Gemini 3.8 Flash (High)
- 일시: 2026-10-24
- 프로젝트: `panda-game`

---

## 1. 생성 및 변경 파일 목록

허용된 범위 내에서만 파일을 생성하였으며, 기존 게임 및 렌더링/전투 코드는 일절 수정하지 않았습니다.

1. `assets/data/items.json`
   - 카탈로그 버전 1 (`catalog_version: 1`).
   - 기본 무기 4종 (`weapon_pistol`, `weapon_dual_pistol`, `weapon_ar`, `weapon_shotgun`) 및 재료 2종 (`scrap_metal`, `bone_fragment`).
   - 런타임 전투 밸런스 수치(damage, cooldown 등)를 중복 정의하지 않고 `weapon_key` 식별자만 보관.
2. `rpg/__init__.py`
   - 공개 API 및 주요 예외 클래스 노출.
3. `rpg/items.py`
   - 아이템 데이터 계약 모델 (`ItemDefinition`, `ItemInstance`, `ItemAffix`).
   - 카탈로그 로더 (`load_catalog`, `get_default_catalog_path`) — `__file__` 기반 절대 경로 계산으로 작업 디렉터리 독립성 확보.
   - 아이템 생성 팩토리 (`create_item`) 및 직렬화/역직렬화 (`to_dict`, `from_dict`).
   - 예외 계층 (`RPGError`, `ValidationError`, `ItemNotFoundError`, `UnsupportedSaveVersion`, `SaveCorruptedError`).
4. `rpg/profile.py`
   - 영구 플레이어 프로필 모델 (`PlayerProfile`, `new_profile`).
   - 장착 슬롯 제약 (실제 소유 무기만 허용, 동일 UID 양 슬롯 장착 거부, 재료 장착 거부).
   - 통화(음수/bool 거절), 해금 목록(중복 거절), 아이템 매핑 검증.
5. `rpg/save_store.py`
   - 원자적 저장 및 자동 백업 관리자 (`SaveStore`, `LoadResult`, `get_default_save_path`).
   - `tempfile` 작성 후 flush/fsync 후 `os.replace`로 교체.
   - 기존 세이브가 유효할 때만 `.bak`으로 복사(손상된 원본으로 정상 백업을 덮지 않음).
   - 미지원 버전(`schema_version > 1`) 세이브 위로 저장하거나 백업으로 무단 폴백하는 것 차단.
   - 손상 시 백업 자동 복구 및 warnings 기록.
   - 스키마 마이그레이션 확장 지점 (`_MIGRATIONS`) 선언.
6. `tests/test_rpg_items.py`
   - 카탈로그 로드, cwd 독립성, `WEAPON_CONFIGS` 키 일치, UID 독립성, 옵션(affix) 유효성/중복 거절, 무기/재료 수량 제약 단위 테스트 16건.
7. `tests/test_rpg_save.py`
   - 프로필 생성, 슬롯 제약, 통화 검증, 격리성, 원자적 저장 실패 복원력, 백업 복구, 버전 불일치 차단 등 단위 테스트 17건.
8. `support/antigravity/20261024-rpg-foundation/verify_foundation.py`
   - 임시 디렉터리에서 프로필 생성 → 아이템 2개·재료 추가 → 두 무기 슬롯 지정 → 저장 → 복원 → 손상 시 백업 복구 E2E 검증 스크립트.
9. `support/antigravity/20261024-rpg-foundation/RESULT.md`
   - 본 결과 보고서.

---

## 2. 공개 API 사용 예시 (요약)

```python
from rpg import (
    load_catalog,
    create_item,
    new_profile,
    SaveStore,
    get_default_save_path,
)

# 1. 카탈로그 로드 (cwd 독립)
catalog = load_catalog()

# 2. 새 프로필 생성 (테스트용 무기 자동 지급 없음)
profile = new_profile()

# 3. 아이템 생성 (독립 UID 및 옵션 검증)
pistol = create_item(
    catalog,
    "weapon_pistol",
    rarity="rare",
    item_level=3,
    affixes=[("damage_mult", 1.15)],
)
scrap = create_item(catalog, "scrap_metal", quantity=50)

# 4. 인벤토리 등록 및 장비 장착
profile.add_item(pistol)
profile.add_item(scrap)
profile.equip("primary", pistol.uid, catalog)

# 5. 저장 및 복원
store = SaveStore("path/to/profile.json", catalog)
store.save(profile)

result = store.load()
# result.source: "primary" | "backup" | "new"
# result.warnings: 복구/경고 메시지 목록
# result.profile: 복원된 PlayerProfile 객체
```

---

## 3. 실행한 검사와 실제 결과

### A. 유닛 테스트 전체 실행
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe -m unittest discover -s tests
  ```
- 결과:
  ```text
  Ran 199 tests in 0.746s
  OK
  ```
  - 기존 166개 테스트 + 신규 RPG 테스트 33개(items 16개, save 17개) 전체 정상 통과.

### B. 독립 실행 검증 스크립트 실행
- 실행 명령어:
  ```powershell
  .venv\Scripts\python.exe support\antigravity\20261024-rpg-foundation\verify_foundation.py
  ```
- 결과:
  ```text
  === RPG Foundation E2E Verification ===
  [OK] Catalog loaded successfully with 6 item definitions.
  [OK] Isolated sandbox created at: C:\Users\nowco\AppData\Local\Temp\...
  [OK] New profile initialized with ID: hero-operative-42
  [OK] Added 3 items to inventory: ['pistol-v01', 'ar-v01', 'scrap-v01']
  [OK] Equipped primary=pistol-v01, secondary=ar-v01
  [OK] First save succeeded.
  [OK] Second save succeeded with backup rotation.
  [OK] Verified roundtrip save and load data integrity from primary.
  [OK] Simulated corruption of primary save file.
  [OK] Successfully recovered profile from backup. Warning: Primary save ... is corrupted (...); recovered from backup ...
  [OK] Confirmed load did not overwrite corrupted primary file on disk.
  === All RPG Foundation verifications passed successfully! ===
  ```

---

## 4. 미완료 사항 및 주의점

- **2단계 이후 연동 대상 (이번 단계 범위 제외)**:
  - 인벤토리 및 장비 슬롯 UI (그리드/슬롯 뷰).
  - 인게임 전투 시 무기 능력치(`damage_mult`, `reload_time_mult`, `weakpoint_mult`) 실제 적용 로직.
  - 게임 플레이 중 던전 드롭 확률 테이블, 몬스터 처치 시 파밍/루팅 이벤트 연동.
  - 사망 또는 던전 탈출 시점의 자동 저장 트리거 연결.
- **주의점**:
  - `PlayerProfile.items`는 캐릭터가 보유한 전체 아이템 딕셔너리(`uid -> ItemInstance`)이며, 장착 슬롯에 등록되지 않은 것은 보관함/인벤토리에 있는 것으로 간주합니다.
  - 무기 정의는 `combat/weapon_config.py`의 `WEAPON_CONFIGS` 키(`PISTOL`, `DUAL_PISTOL`, `AR`, `SHOTGUN`)와 매핑되며, 기본 공격력 및 탄창 수는 `items.json`에 복제하지 않고 기존 밸런스 모듈을 참조하도록 설계되었습니다.

