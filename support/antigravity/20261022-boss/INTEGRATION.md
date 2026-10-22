# Codex 통합 가이드 (INTEGRATION.md)

- **작업 주체**: Antigravity -> Codex 후속 연동 작업 가이드
- **대상 엔티티**: `CableOverlordBoss` (골해의 지배자)

---

## 1. 보스 명칭 및 기본 정보
- **클래스명**: `CableOverlordBoss` (기존 코드 및 모듈 호환성 유지)
- **보스 이름 (`self.name`)**: `골해의 지배자`
- **충돌 반경 (`col_radius`)**: `0.55` (기존 맵과 좁은 통로 네비게이션 100% 호환)
- **최대 체력 (`max_hp`)**: `3500`

---

## 2. HUD 및 UI 매니저 (`ui_manager.py`) 연동 상태
- `update_boss_hp(hp, max_hp, phase)` API가 온전히 유지됩니다.
- Codex가 구현한 0.12초 시간상수 지수 보간 연속 체력바와 완벽히 호환됩니다.
- 보스가 피해를 입거나 회복, 스턴 중일 때도 `m.hp`를 실시간으로 직접 읽어 부드러운 애니메이션이 작동합니다.
- 보스 사망 시 `turn_into_corpse()` 또는 `destroy()`가 호출되면 모든 바닥 위험 인디케이터(`GroundDangerIndicator`)와 3D 뼈 침(`GroundBoneSpike`)이 즉시 화면에서 정리되므로 UI 상의 잔여물 문제가 발생하지 않습니다.

---

## 3. `game.py` 후속 연결 권장 사항
1. **보스 출현 배너 및 알림 문구**:
   - `game.py` 내의 보스 스폰 지점에서 `self.boss.name`을 참조하여 배너를 띄우면 `골해의 지배자`로 자동 표시됩니다.
   - 혹시 하드코딩된 옛 텍스트(`심연의 지배자`, `케이블 엔티티`)가 남아있다면 아래와 같이 통일을 권장합니다:
     ```python
     boss_title = getattr(self.boss, 'name', '골해의 지배자')
     self.ui_mgr.show_stage_banner(f"[ ! 최종 보스 출현: {boss_title} ! ]\n...", color=(1.0, 0.2, 0.2, 1.0))
     ```
2. **사망 및 격파 메시지**:
   - `killer.name`이 `"골해의 지배자"`로 전달되므로 게임오버 화면에서 자연스럽게 출력됩니다.

---

## 4. 패턴 컨트롤러 (`boss_patterns.py`) 상태 연동 요약
- `boss.pattern_controller.state`: `IDLE`, `TELEGRAPH`, `ACTIVE`, `RECOVERY`
- `boss.pattern_controller.is_acting()`: 보스가 특수 공격(휩쓸기, 가시 분출, 도약, 사격, 회복) 중일 때 `True`를 반환합니다.
- `boss.pattern_controller.is_skull_exposed`: 보스가 공격 후 회복 모션일 때 `True`가 되며, 해골 머리가 전면으로 낮아져 헤드샷 적중 판정 범위가 넓어집니다.
