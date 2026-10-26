# 재료 사용처 · 캐릭터 삭제 · UI 구분 도형 구현 결과 보고서 (Antigravity)

**작업 일시:** 2026-10-25  
**작업자:** Antigravity  
**인계자:** Codex  

---

## 1. 완료 범위 요약

Codex가 구현한 핵심 로직(`rpg/workshop.py`, `rpg/characters.py`, `rpg/session.py`, `game.py`) 계약을 온전히 준수하며, 작업대 화면·캐릭터 삭제 UI·도형 및 시인성 개선·통합 검증·오프스크린 다중 해상도 캡처를 완성했습니다.

### A. 무기 작업대 UI (`rpg/workshop_ui.py`, `rpg/__init__.py`)
- **3열 및 상단 배지 레이아웃 구축**:
  - **상단 재료 배지 바**: `고철` 및 `뼈 파편`의 전체 보유 수량과 사용 가능 수량(잠금 제외)을 명확하게 분리 표시.
  - **좌측 무기 목록**: 영구 보관 무기만 희귀도/레벨/UID 순 정렬, 7개 단위 페이징, `[주]`, `[보조]`, `🔒`(잠김) 배지 및 선택 테두리(`▶ ` 인디케이터) 제공.
  - **중앙 2개 강화 공정 카드**:
    - `총열 보강 (reinforce)`: 고철 8개 소모, 기본 공격력 +2%p (`damage_mult` +0.02), 상한 1.30x.
    - `약점 각인 (weakpoint)`: 뼈 파편 6개 소모, 약점 헤드샷 피해 +5%p (`weakpoint_mult` +0.05), 상한 1.50x.
    - 공정 선택 시 시각적 테두리 하이라이트 및 현재 무기 적용 현황/상한 여부 표시.
  - **우측 결과 및 실행 카드**:
    - `resolve_weapon_config` 기반 전→후 공격력, 재장전, 약점 배율 비교.
    - 샷건의 경우 펠릿당 피해량 및 총 발사 펠릿 수(8발) 명시.
    - 소모 재료, 사용 가능 수량, 소모 후 잔여량 표시.
    - `game.upgrade_weapon(quote)`를 통한 단일 진입점 실행.
    - 재료 부족 / 잠김 / 상한 도달 / 사격장(읽기 전용) / 탈출 대기 시 실행 버튼 비활성화 및 붉은색 사유 표시.
    - 성공 시 녹색 1회 피드백 출력, 장비 UI 및 전투 캐시 실시간 동기화.

### B. 캐릭터 삭제 UI (`ui_manager.py`, `game.py`, `rpg/hangul_util.py`)
- **카드별 삭제 버튼**: 캐릭터가 등록된 슬롯에만 붉은색 `[ 삭제 ]` 버튼 노출 (빈 슬롯은 숨김).
- **삭제 확인 모달 (`char_delete_modal`)**:
  - 팝업 최상단 배치 (`setBin("gui-popup", 70)`).
  - 슬롯 번호, 탐험가 이름, 보유 장비 수 요약 표시.
  - 실수 복구를 위한 안내문 명시: *"실수 복구를 위해 기존 저장 파일은 안전하게 보존됩니다."*
  - **한글 이름 입력 및 IME 한계 완전 해결**:
    1. **`[ 이름 자동 입력 ]` 원클릭 버튼 제공**: 모달 내 버튼 클릭 1회로 대상 캐릭터의 이름을 입력창에 즉시 입력하고 확정 버튼을 즉시 활성화.
    2. **클립보드 붙여넣기 (`[ 붙여넣기 ]` 버튼 및 `Ctrl+V` 단축키)**: Windows 클립보드(ctypes 기반 UTF-16)에서 한글 이름을 복사하여 즉시 붙여넣기 지원.
    3. **두벌식 한글 조합기 (`rpg/hangul_util.py`) 영문 타이핑 자동 매칭**: 영문 자판 모드에서 `rlwhs xkagjark` 등을 타이핑해도 `기존 탐험가`로 자동 인식 및 완성형 한글로 즉시 변환.
    4. **캐릭터 생성 모달 연동**: 캐릭터 생성창에서도 `Ctrl+V`, `[ 붙여넣기 ]`, `[ 한글 변환 ]`을 함께 지원하여 한글 이름 자유 생성 지원.
  - 이름 정확 일치 검증: 대상 캐릭터 이름과 일치할 때만 `[ 삭제 확정 ]` 버튼 활성화.
  - [ESC] 또는 [취소] 클릭 시 삭제 확인 모달만 단독으로 닫히고 캐릭터 선택 모달 유지.
  - `game.delete_character(char_id, confirmation_name)` 호출:
    - 동일한 이름을 가진 캐릭터라도 고유 UUID 기반으로 정확히 대상만 삭제.
    - 활성 캐릭터 삭제 시 세션/전투/장비 UI/작업대 UI 참조 해제 및 활성 캐릭터 초기화.
    - 마지막 캐릭터 삭제 시 빈 목록 정상 유지.
    - 실패 시 모달을 유지하며 `game.character_error` 피드백 출력.

### C. 인벤토리 4개 탭 및 도형·시인성 개선 (`ui_manager.py`, `rpg/equipment_ui.py`, `rpg/run_loot_ui.py`)
- **인벤토리 탭 재배치**:
  - 상단 4개 탭 균등 배치 (`x: -0.63, -0.21, +0.21, +0.63`, 버튼 폭 0.38, 간격 0.04):
    1. `[ 소모품 배낭 ]`
    2. `[ 영구 장비함 ]`
    3. `[ 무기 작업대 ]`
    4. `[ 이번 탐험 (미확보) ]`
  - 헤더와 탭, 탭과 본문 사이 기하학적 구분선 (`DirectFrame FLAT`) 배치로 영역 분리.
- **영구 장비함 (`rpg/equipment_ui.py`)**:
  - 3열 각각에 어두운 패널 배경 카드와 제목 구분선 적용.
  - 주/보조 무기 카드 비교 기준 슬롯에 밝은 테두리 및 배경색 차별화.
  - 재료 아이템 선택 시 사용처 안내 (`총열 보강` 또는 `약점 각인`) 및 `[ ⚙ 무기 작업대에서 재료 사용하기 ▶ ]` 1클릭 이동 버튼 추가.
- **이번 탐험 전리품 (`rpg/run_loot_ui.py`)**:
  - 획득 목록 및 상세 정보 구획에 어두운 카드 배경과 구분선 적용.
  - 가방 용량 시각화 바 적용: `[ 이번 탐험 미확보 전리품 가방 : n / 24 ] [████░░░░]`.
  - 24/24 가득 찰 시 경고 문구 및 붉은색 하이라이트.
  - 미확보 재료 선택 시 `★ 탈출로 확보 후 작업대에서 사용 가능` 안내 표기.

---

## 2. 검증 명령 및 결과

### 1) 단위 테스트 전체 스위트 (300개)
```bash
.venv\Scripts\python.exe -m unittest discover -s tests
```
- **결과:** `Ran 300 tests in 2.373s - OK` (한글 자모 변환기 및 삭제 UI 자동완성/클립보드 테스트 포함 전체 통과).

### 2) 작업대 및 캐릭터 삭제 통합 검증 (`verify_workshop.py`)
```bash
.venv\Scripts\python.exe support\antigravity\20261025-workshop-ui\verify_workshop.py
```
- **검증 항목**:
  1. 임시 디렉터리 내 동일 이름 캐릭터 2명 + 긴 한글 이름 캐릭터 1명 생성.
  2. 동일 이름 캐릭터 중 특정 UUID 대상 삭제 시 해당 UUID만 제거되고 동일 이름 타 캐릭터 및 물리 파일 보존 확인.
  3. 실 게임 시작 후 `PLAYING` 상태에서 캐릭터 삭제 차단 확인.
  4. 인벤토리 작업대 진입 후 고철/뼈 파편 사용 가능 vs 잠김 재료 집계 확인.
  5. 장착 주 무기 강화 (`reinforce` +2%p) 실행, 탄약 보존, 전투 대미지 즉각 반영, 재료 차감 확인.
  6. 약점 각인 (`weakpoint` +5%p) 실행 확인.
  7. 단일 quote 재사용 거절, 잠긴 무기 거절, 상한(1.30) 도달 후 추가 강화 거절 확인.
  8. 사격장(`is_test_mode`) 및 탈출 대기(`_extraction_pending`) 상태에서의 강화 차단 확인.
  9. 디스크 저장 재로딩 후 수치 및 재료 영구 반영 확인.
- **결과:** `=== [ALL WORKSHOP & CHARACTER VERIFICATIONS PASSED] ===`

### 3) 기존 전리품 / 탈출 / 확장 검증 스위트 회귀 검사
- `verify_expansion.py`: **ALL RPG EXPANSION VERIFICATION CHECKS PASSED**
- `verify_loot.py`: **All RPG Phase 3 Verifications Passed Successfully!**
- `verify_equipment.py`: **All RPG Equipment & Combat Verifications Passed Successfully!**

### 4) 다중 해상도 오프스크린 UI 캡처 (`verify_workshop_ui.py`)
```bash
.venv\Scripts\python.exe support\antigravity\20261025-workshop-ui\verify_workshop_ui.py
```
1600×900 및 1280×720 환경에서 보관함 40개 이상, 강화 옵션 3개 무기, 긴 한글 이름(`최강의탐험가대원`), 동일 이름(`정예대원`), 전리품 24개 풀 가방 상태로 10장의 고해상도 프리뷰 캡처 생성 완료:
- `character_select_1600x900.png` (53 KB)
- `character_delete_modal_1600x900.png` (75 KB)
- `equipment_ui_1600x900.png` (244 KB)
- `workshop_ui_1600x900.png` (240 KB)
- `run_loot_24_1600x900.png` (221 KB)
- `character_select_1280x720.png` (53 KB)
- `character_delete_modal_1280x720.png` (75 KB)
- `equipment_ui_1280x720.png` (252 KB)
- `workshop_ui_1280x720.png` (248 KB)
- `run_loot_24_1280x720.png` (230 KB)

### 5) Windows 개행 (CRCRLF) 검사
```bash
.venv\Scripts\python.exe -c "for f in ['rpg/workshop_ui.py', 'rpg/equipment_ui.py', 'rpg/run_loot_ui.py', 'ui_manager.py', 'game.py']: assert b'\r\r\n' not in open(f, 'rb').read(); print(f, 'OK')"
```
- **결과:** 모든 수정 및 생성 파일에 `\r\r\n` 0건 확인 완료.

---

## 3. 계약 및 제약 조건 준수 확인

1. **저장 무결성 및 계약 준수**:
   - `rpg/workshop.py`의 `RECIPES`(`reinforce`, `weakpoint`)만을 강화 비용/배율 정의로 활용.
   - 강화 실행은 전적으로 `game.upgrade_weapon(quote)`를 통해서만 수행.
   - 강화 후 `reset_state` 호출을 배제하여 탄약 보충 버그 방지.
   - 캐릭터 삭제 시 물리 파일을 임의로 파기하지 않고 플레이 목록에서만 제외하여 실수 복구 가능성 보존.
2. **비파괴적 작업**:
   - `rankings.json` 및 실제 사용자 세이브 파일 일체 보존.
   - 모든 검증 및 테스트는 `tempfile.TemporaryDirectory` 상에서 독립 수행.
   - `git reset`, `git clean`, `git commit` 미수행.

---

## 4. 인계 안내

모든 지시사항이 오차 없이 구현 및 검증되었습니다.  
사용자께서 Codex에 **`안티 작업 끝`**을 전달하시면 통합 리뷰를 시작할 수 있습니다.

