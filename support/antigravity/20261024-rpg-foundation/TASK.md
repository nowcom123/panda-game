# Antigravity 협업 — 1단계: 아이템 데이터와 저장 기반

프로젝트: `C:\Users\nowco\Desktop\Dream\panda-game`

사용자가 이 파일을 Antigravity에 직접 전달하는 방식이다. 현재 선택된 모델로 구현하고
실제 모델명은 알 수 있을 때만 결과에 기록한다. 다른 에이전트까지 추가로 호출하지 않는다.

## 목표와 담당

게임을 던전 크롤러 파밍 RPG로 확장하는 첫 단계다. 이번 결과물은 실제 사용 가능한
아이템 모델, 데이터 검증, 프로필 저장/복원 API와 독립 실행 예제다.

- Codex: 기존 코드 조사와 아래 인터페이스·검증 기준 확정 완료. 반환 후 변경 리뷰,
  회귀 검사, 다음 단계의 실제 게임 연결을 담당한다.
- Antigravity: 아래 허용 파일에 구현과 테스트를 작성하고 RESULT.md에 결과를 남긴다.
- 효율: 전체 저장소를 다시 분석하거나 두 가지 구현안을 만들지 않는다. 필요한 참조만
  읽고 하나의 작은 구현으로 완료한다. 라이브러리 설치, 엔진 변경, UI 시안은 필요 없다.

## 확인된 기존 구조

- `combat/weapon_config.py`: 현재 수치의 원본. 무기 키 `PISTOL`, `DUAL_PISTOL`, `AR`, `SHOTGUN`.
  PISTOL은 .50 데저트 이글이다. 기본 공격력 등의 값을 새 JSON으로 복제하지 않는다.
- `player_controller.py`: `inventory`는 응급키트·탄약 등 소모품 dict 목록이다.
  `reset_inventory()`는 매 새 게임에 초기화한다. 새 영구 장비 데이터와 혼합하면 안 된다.
- `game.py`: start_game/restart_game, 사망/탈출 상태 연결은 후속 단계다.
- `ui_manager.py`: rankings.json은 순위 기록이며 프로필 세이브가 아니다.
- `item_editor.py`: 검·도끼 등 구형 템플릿 에디터. 이번 런타임 데이터의 의존성으로 쓰지 않는다.
- 작업 트리에 사용자 변경과 Codex 최적화가 많다. 기존 파일 롤백, git reset/clean/commit 금지.
  Weapon_Templates.json, sky.jpg 삭제 상태도 복구하거나 변경하지 않는다.

## 수정 허용 범위

- 신규 `rpg/__init__.py`, `rpg/items.py`, `rpg/profile.py`, `rpg/save_store.py`
- 신규 `assets/data/items.json`
- 신규 `tests/test_rpg_items.py`, `tests/test_rpg_save.py`
- 이 폴더의 `verify_foundation.py`, `RESULT.md`

기존 게임·전투·UI·적·렌더링·성능 관련 파일과 rankings.json은 수정하지 않는다.
별도 인벤토리 UI, 실제 장비 능력치 적용, 무기 2슬롯 제한, 드롭 확률, 자동 저장 이벤트는
2단계 이후다. 이번에는 해당 기능을 위한 저장 필드만 마련한다.

## 데이터 계약 — schema_version 1

표준 라이브러리만 사용한다. rpg 패키지는 Panda3D/ShowBase/game을 import하지 않는다.
dataclass 등 간단한 구조로 작성하며 전역 가변 공유 상태와 pickle은 사용하지 않는다.

### 아이템 정의와 인스턴스

`assets/data/items.json`에는 catalog_version=1과 definitions 목록을 둔다.
각 정의: `definition_id`, 한국어 `name`, `kind`(weapon/material), `weapon_key`(무기에만),
`max_stack`(무기 1, 재료 양의 정수). 최소 무기 4종과 scrap_metal/bone_fragment 재료 2종.
기본 전투 수치는 넣지 않는다. definition_id는 UI 표시명과 독립적인 영구 식별자다.

`ItemInstance` 필드:
- `uid`: 개별 물건의 비어 있지 않은 고유 문자열. 기본 생성은 uuid4, 테스트에서는 주입 가능.
- `definition_id`: 정의 참조.
- `rarity`: common/uncommon/rare/epic/legendary 중 하나.
- `item_level`: 양의 정수.
- `quantity`: 1..max_stack. 무기는 항상 1.
- `affixes`: 옵션 ID와 확정된 수치의 목록. 저장할 때 재추첨하지 않는다.
- `locked`: bool. 후속 잠금/일괄 분해 UI를 위한 데이터.

옵션 ID는 이번에 damage_mult/reload_time_mult/weakpoint_mult 세 개만 허용하고,
양의 유한 숫자만 수용한다. 재료에는 옵션을 허용하지 않는다. 옵션 효과 계산/랜덤 생성은
구현하지 않는다. 같은 옵션 ID의 중복과 알 수 없는 옵션을 명확히 거절한다.

필수 공개 API(세부 타입은 문서화):
- `load_catalog(path=None)` → 검증된 정의 매핑. 기본 경로는 __file__ 기준, cwd 독립.
- `create_item(catalog, definition_id, *, rarity='common', item_level=1,
  quantity=1, affixes=None, locked=False, uid=None)` → ItemInstance.
- 인스턴스의 JSON 호환 `to_dict()` / `from_dict(data, catalog)`.

### 영구 프로필

`PlayerProfile`: `schema_version=1`, `profile_id`, `items`(uid → ItemInstance),
`equipment`({primary: uid 또는 null, secondary: uid 또는 null}), `currencies`({credits: 0}),
`unlocks`(중복 없는 문자열 목록).

items는 소유 물건 전체다. 장착하지 않은 물건이 창고에 있는 것으로 해석하여 별도의
중복 stash 목록은 만들지 않는다. equipment의 UID는 실제 소유한 무기여야 하며 두 슬롯에
동일 UID를 넣을 수 없다. 딕셔너리 키와 인스턴스 uid 불일치도 거절한다.

- `new_profile(profile_id=None)` → 빈 프로필. 테스트용 장비를 실제 사용자에게 자동 지급하지 않는다.
- `profile.to_dict()` / `PlayerProfile.from_dict(data, catalog)` → 검증된 직렬화/복원.
- 음수 수량·통화, bool을 정수로 오인하는 값, NaN/Infinity, 잘못된 참조, 중복 UID를 거절한다.
- 로드 후 수정한 목록이 원본 dict나 다른 프로필에 영향을 주지 않게 한다.

### 저장소

`SaveStore(path, catalog)`; 기본 경로 계산은 별도 함수로 제공한다.
기본 경로: Windows LOCALAPPDATA 아래 `LiminalBackrooms/profile.json`.
환경 변수가 없으면 사용자 홈 아래 `.liminal_backrooms/profile.json`.
테스트·예제는 반드시 명시적으로 TemporaryDirectory 내부 경로를 전달한다.

- `save(profile)` → 검증 후 UTF-8 JSON 기록. 같은 디렉터리에 임시 파일을 만들고
  flush/fsync 후 os.replace로 교체한다. 성공 전 원본을 지우지 않는다.
- 기존 정상 세이브는 `.bak`에 보존한다. 이미 손상된 원본으로 정상 백업을 덮지 않는다.
- `load()` → `LoadResult(profile, source, warnings)`. source는 primary/backup/new 중 하나.
- 파일이 없으면 빈 프로필을 메모리에 반환하고 디스크에 자동 기록하지 않는다.
- 본 파일 손상 시 유효한 백업을 읽고 warnings에 복구 사실을 남긴다. 로드가 파일을 수정하지 않는다.
- 둘 다 손상되면 명시적 예외. 빈 프로필로 조용히 덮어쓰지 않는다.
- 지원 버전보다 높은 세이브는 백업으로 몰래 되돌리지 말고 UnsupportedSaveVersion 예외.
  알 수 없는 버전의 파일 위로 save하는 것도 차단한다.
- 정의가 없어진 아이템은 이번 v1에서 검증 오류로 처리하고 원본을 보존한다.
  버전별 migration 함수의 확장 지점만 마련한다. 실제 구형 RPG 세이브는 없으므로 가짜 migration 금지.
- 오류 메시지는 실패 이유/파일을 파악할 수 있어야 한다. 예외를 광범위하게 삼키지 않는다.
- 여러 게임 프로세스 동시 실행 충돌 해결이나 클라우드 동기화는 이번 범위가 아니다.

## 완료 검사

1. 4종 무기 키가 현재 WEAPON_CONFIGS와 일치하며 런타임 수치를 중복 저장하지 않는다.
2. 같은 총기 정의로 만든 두 개체의 UID/옵션은 독립적이다.
3. UID, 옵션, 장착 관계, 재료 수량, 잠금, 통화가 왕복 저장에서 정확히 보존된다.
4. 누락/중복/범위 오류, 잘못된 장착 참조, 미지원 버전은 명확히 실패한다.
5. save 도중 os.replace 실패를 주입해도 직전 정상 세이브가 읽힌다.
6. 손상된 primary + 정상 backup은 복구 가능하고, 둘 다 손상 시 원본을 보존한 채 실패한다.
7. 작업 디렉터리를 바꿔도 기본 카탈로그 로드가 된다.
8. verify_foundation.py는 임시 디렉터리에서 프로필 생성 → 아이템 2개·재료 추가 →
   두 무기 슬롯 지정 → 저장 → 복원 → 손상 시 백업 복구를 보여주고 정리한다.
9. `.venv/Scripts/python.exe -m unittest discover -s tests` 및 위 예제 실행.
   테스트가 실제 LOCALAPPDATA/사용자 저장/순위 파일을 쓰면 안 된다.

## 반환

RESULT.md에 변경 파일, 공개 API 사용 예(짧게), 실행한 검사와 실제 결과, 미완료/주의점을 기록한다.
과장된 완료 선언이나 향후 UI 기능을 이미 구현한 것처럼 설명하지 않는다.
완료 후 사용자가 Codex에게 '안티 작업 끝'이라고 전달하면 Codex가 리뷰한다.
