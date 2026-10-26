# Antigravity RPG 확장 구현 결과 보고서

## 1. 개요 및 구현 범위

Codex가 구현 완료한 A1(스테이지별 보스 성장 로직)을 온전히 보존한 상태에서, 지시서(`TASK.md`)에 따라 **A2(신규 보스 기믹 2종) → B(캐릭터 생성/선택 및 독립 저장) → C(인벤토리 UI 재정비 및 다중 해상도 검증)**을 완수했습니다.

---

### Phase A: 보스 성장 및 신규 기믹 (A1 잔여 + A2)

1. **A1 잔여 HUD 연동**:
   - `ui_manager.py`: 보스 체력바 상단 텍스트에 스테이지 레벨 `[Lv.n]` 및 실시간 부위 파괴 수 `(다리 파괴: n/8)` 표시 반영.
   - 2페이즈 폭주 시 붉은색 게이지 및 `[Lv.n] 골해의 지배자 — 폭주 (다리 파괴: n/8)` 표시 연동.
   - AI 틱 분산과 무관하게 매 프레임 `_animate_boss_hp`에서 현재 체력과 파괴된 다리 수를 동기화.

2. **A2 신규 보스 기믹 1 — 뼈 부채꼴 파동 (3층부터)**:
   - 시전 개시 시 플레이어 방향을 조준각도로 고정하고 전방 14.0m, 각도 ±60도 범위의 부채꼴 파동 예고 (`FanWaveIndicator`).
   - 중앙 폭 24도(±12도)의 녹색 안전 통로 보장. 안전 통로가 벽으로 막혀 있는 경우 패턴 시전을 건너뛰고 다른 패턴 선택.
   - 예고 시간 1.1초(>= 1.0초 요구 충족), 활성 시간 0.5초.
   - 프레임 단위 연타 방지 플래그(`fan_wave_hit_done = True`) 적용 및 `clear_attack_path`로 벽 너머 피해 관통 차단.

3. **A2 신규 보스 기믹 2 — 뼈 심장 봉인 (5층부터)**:
   - 보스 좌우 3.8m 빈 공간에 최대 2개의 파괴 가능한 `BoneHeartSeal` 봉인체 생성 (`HP 120 * limb_health_scale`).
   - 봉인 활성 중 보스는 뼈 방어막 이펙트와 함께 받는 피해 60% 감소 (`dmg *= 0.40`).
   - 봉인체는 `is_hit_by_ray` 및 `take_damage`를 구현하여 레이캐스트 사격 적중 및 피격 시 붉은색 발광 반응 제공 (경험치/드롭 미지급).
   - 모든 봉인 파괴 성공 시: 보스 2초 스턴(`stun_timer = 2.0`), 두개골 약점 노출(`is_skull_exposed = True`), 리커버리 전환.
   - 8초 타임아웃 경과 시: 방어막 해제 및 봉인 소멸 (스턴 보상 없음).
   - 보스 사망, 다리 파괴 중단, 다음 층 진입, 메뉴 복귀 시 `pattern_controller.cleanup()`으로 봉인체 및 쉴드 완벽 소거.

4. **부위 파괴 연계**:
   - 거미 다리가 4개 이상 파괴된 경우 `_can_leap_to_target`이 `False`를 반환하여 도약 강타(Spider Leap Slam) 선택을 영구 차단.
   - 파괴 수는 `leg_hp`에서 실시간 집계하여 중복 카운터 변수 방지.

---

### Phase B: 캐릭터 생성·선택과 저장 분리

1. **저장 구조 및 목록 관리 (`rpg/characters.py`)**:
   - 저장 루트 레이아웃: `characters.json` 및 `characters/<uuid>/profile.json`.
   - `CharacterList`: `version=1`, `active_character_id`, `characters` 리스트(각 id, name, created_at).
   - `CharacterManager`: 원자적 파일 교체(`_atomic_write`), 백업 로테이션(`characters.json.bak`), 미지원 상위 버전(`UnsupportedSaveVersion`) 보호 적용.
   - 캐릭터 ID는 표준 UUID를 사용하며, 파일 경로에 사용자 지정 이름을 직접 사용하지 않아 경로 조작(Path Traversal) 공격 방지.
   - 이름 검증: 2~12자(한글/영문/숫자 허용, 양끝 공백 자동 제거, 유니코드 제어문자 거절).
   - 최대 3명 제한: 4번째 생성 시도시 `RPGError` 차단.

2. **기존 단일 `profile.json` 안전 이관 (Migration)**:
   - 기존 저장소에 `profile.json`이 존재할 경우 **원본과 .bak 파일을 절대 삭제하지 않고 보존**.
   - 프로필 ID 기반 결정적 UUID(`uuid.uuid5(uuid.NAMESPACE_OID, f"legacy_{profile_id}")`)로 이관하여 중복 실행 및 재개 시에도 멱등성 보장 및 캐릭터 복제 방지.
   - 기존 `SaveStore`로 복구/로드 검증 → 새 캐릭터 경로에 저장 → 대상 파일 재로드 검증 → 마지막으로 `characters.json`에 '기존 탐험가'로 커밋.

3. **게임 루프 및 권한 격리 연동 (`game.py`, `ui_manager.py`)**:
   - 타이틀 메뉴(`INTRO`)에서만 캐릭터 선택 및 생성 가능. 탐험 진행 중(`PLAYING`)에는 전환 차단.
   - 탈출 저장 실패(`_extraction_pending == True`) 상태에서는 캐릭터 전환 및 생성 원천 차단.
   - 새 캐릭터 전환 시 `combat.item_states`, 탄약 풀, 캐시를 초기화하여 이전 런의 잔여 상태 혼선 방지.
   - 레거시 테스트 스크립트의 `save_path` / `save_store` 명시적 주입 시 단일 캐릭터 검사 모드로 호환성 유지.

---

### Phase C: 인벤토리 UI 재정비 및 다중 해상도 검증

1. **상단 통합 헤더 및 입력 안내 일치**:
   - 상단 헤더: `[ TACTICAL INVENTORY // 탐험가: {name} ]`
   - 안내 문구: `[1] 주 무기  |  [2] 보조 무기  |  [3] 구급약  |  [4] 탄약팩  |  [G] 수류탄  |  [Tab/I] 가방 닫기`
   - 상단 탭: `[ 소모품 배낭 ]  |  [ 영구 장비함 ]  |  [ 이번 탐험 (미확보) ]` (상호 배타적 전환 보장).

2. **영구 장비함 3단 칼럼 배치 (`rpg/equipment_ui.py`)**:
   - **좌측 칼럼**: 주/보조 무기 장착 카드 (슬롯 클릭 시 비교 대상 지정), 보유 크레딧(`{credits} C`).
   - **중앙 칼럼**: 7개 단위 스크롤 보관함 + `[ 등급순 ]` / `[ 종류순 ]` / `[ 이름순 ]` 실시간 정렬 버튼 + 페이지 내비게이션. 긴 이름 말줄임표 처리.
   - **우측 칼럼**: 선택 아이템 제원 + 대상 슬롯 장비 대비 실시간 비교(`resolve_weapon_config` 기반 공격력/장전시간/약점배율 증감율 표기) + 부여 옵션 목록.
   - **버튼 상태 및 이유 명시**:
     - 재료 아이템 선택 시: `[재료 장착 불가]`
     - 이미 장착 중인 슬롯: `[이미 주 무기]` / `[이미 보조 무기]`
     - 마지막 남은 무기 해제 시도 시: `[마지막 무기 해제 불가]`
   - **선택 및 스크롤 유지**: 장착, 해제, 잠금 토글 후에도 현재 선택된 아이템(`selected_uid`)과 페이지 번호(`current_page`) 보존.

3. **이번 탐험 탭 (`rpg/run_loot_ui.py`)**:
   - 용량 `n / 24` 및 사망/포기 시 전리품 소실 경고 배너 유지.
   - 미확보 아이템 읽기 전용 열람 및 `[ 탈출 후 장착 및 관리 가능 ]` 상태 명확화.

4. **다중 해상도 오프스크린 캡처 검증**:
   - 1600×900: `character_select_1600x900.png`, `inventory_ui_1600x900.png`
   - 1280×720: `inventory_ui_1280x720.png`
   - 영구 보관함 40개 이상(44개), 미확보 전리품 24개 풀 상태에서 텍스트 잘림, UI 겹침, 버튼 클릭 영역 정상 작동 확인.

---

## 2. 변경 및 생성 파일 목록

| 구분 | 파일 경로 | 변경 요약 |
|---|---|---|
| **신규** | `rpg/characters.py` | 캐릭터 목록/요약, 유효성 검증, 독립 SaveStore 관리, 레거시 profile.json 결정적 이관 |
| **신규** | `tests/test_boss_gimmicks.py` | 부채꼴 파동, 뼈 심장 봉인, 다리 4개 파괴 시 leap 금지, 보스 HUD 표시 단위 테스트 (7개) |
| **신규** | `tests/test_rpg_characters.py` | 캐릭터 생성/최대 3명, 격리, 레거시 이관 원본 보존, 미지원 버전 차단 단위 테스트 (8개) |
| **신규** | `tests/test_rpg_expansion_integration.py` | 40개 장비 정렬/페이징/선택유지, 24개 전리품, 게임 내 캐릭터 전환 규칙 통합 테스트 (3개) |
| **신규** | `support/antigravity/20261024-rpg-expansion/verify_expansion.py` | A~C 전 범위 엔드투엔드 무인 검증 스크립트 |
| **신규** | `support/antigravity/20261024-rpg-expansion/verify_expansion_ui.py` | 1600×900 및 1280×720 다중 해상도 오프스크린 캡처 생성 스크립트 |
| **신규** | `support/antigravity/20261024-rpg-expansion/character_select_1600x900.png` | 1600×900 탐험가 선택/관리 모달 캡처 이미지 |
| **신규** | `support/antigravity/20261024-rpg-expansion/inventory_ui_1600x900.png` | 1600×900 3단 인벤토리 UI 캡처 이미지 |
| **신규** | `support/antigravity/20261024-rpg-expansion/inventory_ui_1280x720.png` | 1280×720 3단 인벤토리 UI 캡처 이미지 |
| **수정** | `boss_scaling.py` | `apply_boss_scaling` 시 `limb_health_scale` 저장 추가 |
| **수정** | `boss_patterns.py` | `FanWaveIndicator`, `BoneHeartSeal` 구현, 패턴 컨트롤러 디스패치 및 4다리 파괴 도약 차단 |
| **수정** | `monster.py` | `CableOverlordBoss` 뼈 방어막 노드(`set_bone_shield`), 보호 시 60% 피해 감소(`dmg *= 0.40`), `destroy` 정리 |
| **수정** | `combat_system.py` | `_perform_raycast`에 `BoneHeartSeal` 사격 판정 및 타격 피드백, 파괴 처리 추가 |
| **수정** | `ui_manager.py` | 보스 HUD 레벨/파괴다리수 표시, 탐험가 선택 모달, 인벤토리 3단 헤더 및 탭 배타적 갱신 |
| **수정** | `game.py` | `CharacterManager` 연결, `switch_to_character`, `create_and_switch_character`, 타이틀 전환 검사 |
| **수정** | `rpg/equipment_ui.py` | 3단 칼럼 재배치, 등급/종류/이름 정렬, 옵션 비교(`resolve_weapon_config`), 버튼 비활성화 이유 명시 |
| **수정** | `rpg/__init__.py` | `CharacterManager`, `CharacterSummary`, `CharacterList` 모듈 내보내기 |

---

## 3. 검증 결과

### 1) 단위 테스트 스위트
```text
Ran 265 tests in 1.319s
OK
```
- 기존 247개 테스트 전체 통과 (회귀 0건).
- 신규 추가된 18개 테스트 (`test_boss_gimmicks.py` 7개, `test_rpg_characters.py` 8개, `test_rpg_expansion_integration.py` 3개) 전체 통과.

### 2) 독립 검증 스크립트 실행
- `python support/antigravity/20261024-rpg-expansion/verify_expansion.py`:
  - Phase A: 6층 스케일링, 부채꼴 파동(안전지대/피해영역/1회피격), 뼈 심장 봉인(2개생성/60%감소/스턴보상/정리), 다리 4개 파괴 시 leap 금지 검증 완료.
  - Phase B: 최대 3명 제한, 2명 캐릭터 간 아이템/통화/잠금 격리, 레거시 profile.json 바이트 일치 보존 및 멱등 이관 검증 완료.
  - Phase C: 44개 장비 7페이지 페이징, 등급/종류/이름 정렬, 마지막 무기 해제 불가 보호, 24개 가방 용량 검증 완료.
  - 결과: **ALL RPG EXPANSION VERIFICATION CHECKS PASSED SUCCESSFULLY!**

### 3) 다중 해상도 오프스크린 UI 캡처
- `python support/antigravity/20261024-rpg-expansion/verify_expansion_ui.py`:
  - `character_select_1600x900.png` (50,656 bytes): 3개 슬롯 카드, 현재 선택 상태, 탐험 레벨 초기화 안내, 등록 모달 렌더 확인.
  - `inventory_ui_1600x900.png` (230,313 bytes): 좌측 슬롯/크레딧 + 중앙 44개 보관함 정렬/페이징 + 우측 비교/부여옵션 3단 레이아웃 렌더 확인.
  - `inventory_ui_1280x720.png` (172,765 bytes): 720p 해상도에서 텍스트 잘림 및 UI 겹침 없는 안정적 렌더 확인.

---

## 4. 제약 사항 및 보존 현황 확인

1. **줄바꿈(CRCRLF) 검사**:
   - `combat_system.py`, `ui_manager.py`, `monster.py`, `boss_patterns.py`, `boss_scaling.py`, `game.py`, `rpg/equipment_ui.py`, `rpg/characters.py` 등 모든 대상 파일에서 `CRCRLF == 0` 확인 완료.
2. **이중 피해 방지**:
   - `GroundShockwave`는 순수 시각 효과로 유지하고 별도 피해를 추가하지 않음.
3. **가속 배율 중복 배제**:
   - 보스는 `boss_scaling`의 `bounded movement_scale`만 적용되고, 일반 몬스터의 `stage_mult` 가속은 중복 적용되지 않음.
4. **저장소 및 랭킹 보존**:
   - 실제 사용자 저장 경로 및 `rankings.json`을 수정하지 않았으며, 모든 테스트와 캡처는 `tempfile.TemporaryDirectory`에서 격리 실행됨.
5. **외부 패키지 추가 없음**:
   - 신규 라이브러리 설치 없이 기본 Python 3 및 기존 Panda3D / DirectGUI 환경만 활용.

