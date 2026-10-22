# 불릿타임 연출 비교 검토 및 추천 결과 보고서 (RESULT.md)

- **작업 일시**: 2026-10-23
- **실제 사용 모델**: Gemini 3.8 Flash (High) (사용자 설정 모델)
- **작업 원칙**: 지시서 사양에 따라 본 단계에서는 게임 코드에 신규 효과를 기본 적용하지 않고, 코드 분석과 독립 프리뷰 렌더링 스크립트를 통해 비교 검토를 진행함.

---

## 1. 기존 구현 상태 및 재사용 자산 분석

1. **후처리 파이프라인 (`post_processing.py`)**:
   - Codex가 `GamePostProcessing`을 통해 SimplePBR 톤매핑 패스 내에 일반 화면 선명도(Sharpening) 옵션을 추가 완료함.
   - 별도의 렌더 타깃(FBO)이나 추가 전체화면 패스를 생성하지 않고, 기존 톤매핑 쿼드의 프래그먼트 셰이더 내에서 단일 패스로 처리됨.
   - HUD(render2d)는 후처리 쿼드 이후에 렌더링되므로, 후처리 효과가 UI와 조준선을 절대 흐리거나 왜곡하지 않음.
2. **탄피 및 파편 시스템 (`casing_effects.py`, `combat_system.py`)**:
   - 24개 고정 크기 풀(`CasingEffects`)과 64개 피격 파티클 풀(`hit_particle_pool`)이 사전 할당되어 GC 스파이크 없이 작동 중임.
   - 현재 `game.py`에서 `combat.update(dt)`에 실시간 `raw_dt`를 그대로 넘기고 있어, 불릿타임(0.35x) 중에도 탄피와 혈흔 파편만 1.0x 실시간 속도로 빠르게 떨어지는 몰입감 저해 요소가 존재함.
3. **오디오 및 전환 이징 (`audio_system.py`)**:
   - 불릿타임 시작 시 0.12초 볼륨 페이드인, 종료 시 0.30초 볼륨 페이드아웃, 0.95초에 걸친 피치 감속(`setPlayRate(1.0 - 0.58 * ease)`)이 이미 정교하게 구현되어 있음.
4. **FOV 및 UI 연출 (`combat_system.py`, `ui_manager.py`)**:
   - 현재 `combat_system.py`에서 불릿타임 시 `cur_fov += 6.5`가 1프레임 만에 계단식으로 즉시 전환되어 시각적 튀임(Snap) 현상이 있음.
   - `ui_manager.py`의 청록색 외곽 비네트 펄스와 카운트다운 타이머 패널은 독립적으로 깔끔하게 기능하고 있음.

---

## 2. 연출 제안 비교 검토 및 추천 조합

### [최우선 추천 조합] (성능 무부하 + 높은 시각적 완성도)

| 제안 연출 | 기술 구현 방식 | 장점 및 시인성 | 예상 비용 및 리스크 |
|---|---|---|---|
| **1. 탄피 및 파편의 슬로우모션 (0.35x)** | `combat_system.py`에서 시각 효과용 `fx_dt`를 분리하여 `casing_effects.update(fx_dt)`, `hit_particle_pool`, `smoke_pool`에만 0.35x 적용. 무기 발사·장전·마우스 시점 속도는 1.0x 유지. | 1인칭 화면 바로 옆에서 황동 탄피가 천천히 텀블링하며 튀어나가고, 피격 파편이 공중에 머물러 영화 같은 슬로모션 체감 극대화. | • 추가 메모리: 0<br>• 추가 드로우콜: 0<br>• 성능 부하: 0 |
| **2. 약한 채도 감소 (20~22%) + 차가운 청회색 틴트** | `post_processing.py`의 톤매핑 셰이더 내에서 3~4줄의 경량 수식으로 휘도 기반 채도 22% 감소 및 차가운 틴트(`vec3(0.92, 0.96, 1.06)`) 합성. | 영화 <매트릭스> 스타일의 차분하고 냉철한 몰입감 제공. 배경이 차분해짐에 따라 **적의 붉은 안광, 바닥의 주황색 위험 경고 링, 총구 화염이 훨씬 선명하게 부각**되어 피아 식별 및 회피 시인성 개선. HUD는 100% 원본 선명도 유지. | • 신규 패스 없음<br>• GPU 부하: 0.01ms 이하 (ALU 연산 4개)<br>• 과도한 흑백화 방지 (20% 수준 유지) |
| **3. 전환감 부드러운 보간 (Ease-in 0.20s / Ease-out 0.28s)** | 불릿타임 강도 계수 `bt_intensity (0.0~1.0)`를 도입하여 색조 틴트와 FOV 워프(+5.5도)를 부드럽게 보간. | 기존 계단식 FOV 팝핑(+6.5도)을 완전히 없애고, 오디오 피치 감속(0.12s/0.30s)과 시각 효과가 완벽하게 일치하여 "집중 상태로 진입하는 감각"을 자연스럽게 전달. | • 연산 부하: float lerp 1개 (측정 불가 수준) |
| **4. 총알 궤적(Tracer) 비행 속도 감속 (선택 적용)** | 히트스캔 즉시 판정은 유지하되, 시각용 `active_tracers`의 비행 진행 속도만 `fx_dt`로 업데이트. | 총알이 공기를 가르며 목표물로 날아가는 궤적 선이 0.25~0.30초 동안 시야에 선명히 남아 전술적 궤적 인지 가능. | • 기존 트레이서 풀 재사용<br>• 탄피 잔상(Trail)은 시야를 가릴 위험이 있어 제외 권장 |

---

### [우선안에서 제외한 효과 및 사유]

1. **전체 화면 강한 모션블러 (Full-screen Motion Blur)**:
   - 빠른 마우스 에임 조준 시 화면이 심하게 뭉개져 1인칭 정밀 사격에 치명적인 방해가 됨.
   - Panda3D 환경에서 벨로시티 버퍼 또는 다중 프레임 버퍼 블렌딩 필요 시 상당한 GPU 대역폭 및 VRAM 오버헤드 유발.
2. **과도한 색수차 (Chromatic Aberration - RGB 색분리)**:
   - 화면 가장자리의 몬스터 윤곽선을 흐릿하게 만들어 장시간 플레이 시 눈의 피로도를 급격히 증가시킴.
3. **급격한 화이트 플래시 / 섬광**:
   - 백룸 특유의 어둡고 밀폐된 공간에서 시각적 불쾌감을 주며 야간 플레이 시 눈부심 유발.
4. **추가적인 과도한 FOV 왜곡 (>12도)**:
   - 마우스 감각 왜곡 및 어안렌즈 왜곡으로 원근 거리 측정을 방해함.

---

## 3. 구체적인 변경 후보 위치 (추후 본 적용 시 참고용)

- [post_processing.py](file:///c:/Users/nowco/Desktop/Dream/panda-game/post_processing.py):
  - 톤매핑 프래그먼트 셰이더에 `bt_intensity` 유니폼 및 `apply_bullet_time_grade` 수식 삽입.
  - `GamePostProcessing.set_bullet_time_intensity(intensity)` 메서드 추가.
- [combat_system.py](file:///c:/Users/nowco/Desktop/Dream/panda-game/combat_system.py):
  - 2394행: `self.casing_effects.update(fx_dt)` 및 `hit_particle_pool`에 `fx_dt` 전달.
  - 2693행: 계단식 `cur_fov += 6.5` 대신 `cur_fov += 5.5 * self.bt_intensity` 보간 적용.
- [game.py](file:///c:/Users/nowco/Desktop/Dream/panda-game/game.py):
  - 불릿타임 루프(1282행)에서 `fx_dt = world_dt` 산출 및 파이프라인의 `bt_intensity`를 0.20s/0.28s 속도로 갱신.

---

## 4. 검증 결과 및 프리뷰 산출물

### 검증 실행 결과
1. **단위 테스트 전체 실행**:
   ```powershell
   python -m unittest discover -s tests
   ```
   - **결과**: `Ran 141 tests in 0.397s, OK` (모든 기존 및 신규 테스트 100% 통과)
2. **GPU 선명도 및 불릿타임 독립성 검증 스크립트 실행**:
   ```powershell
   python support/graphics/verify_bullet_time.py
   ```
   - **결과**: `PASS: GPU shaders, 261209 changed scene pixels, settings toggle, bullet-time independence, exact restoration, pipeline rebuild.`

### 생성된 비교 프리뷰 이미지 ([support/antigravity/20261023-bullet-time/](file:///c:/Users/nowco/Desktop/Dream/panda-game/support/antigravity/20261023-bullet-time/))
- [preview_normal.png](file:///c:/Users/nowco/Desktop/Dream/panda-game/support/antigravity/20261023-bullet-time/preview_normal.png): 일반 상태 화면 (표준 톤매핑, 샤프닝 OFF).
- [preview_bullet_time_proposed.png](file:///c:/Users/nowco/Desktop/Dream/panda-game/support/antigravity/20261023-bullet-time/preview_bullet_time_proposed.png): 제안된 불릿타임 연출 (22% 채도 감소 + 차가운 청회색 틴트 + 슬로우 탄피). 적 안광과 바닥 위험 링이 차분한 배경 위에서 더욱 선명하게 대비됨.
- [preview_bullet_time_with_sharpening.png](file:///c:/Users/nowco/Desktop/Dream/panda-game/support/antigravity/20261023-bullet-time/preview_bullet_time_with_sharpening.png): 제안 불릿타임 상태에서 사용자가 ESC 설정의 선명도(Sharpening)를 ON으로 켰을 때의 화면 (선명도 옵션과 완벽한 독립 공존 확인).
- [preview_casing_tracer_slowmo.png](file:///c:/Users/nowco/Desktop/Dream/panda-game/support/antigravity/20261023-bullet-time/preview_casing_tracer_slowmo.png): 슬로우모션으로 천천히 회전하며 방출되는 탄피 비행 클로즈업 뷰.
- 프리뷰 렌더링 스크립트: [preview_bullet_time.py](file:///c:/Users/nowco/Desktop/Dream/panda-game/support/antigravity/20261023-bullet-time/preview_bullet_time.py)

---

## 5. 구현하지 않은 부분 (현 단계의 경계)
- 사용자 지시서의 **"이번 단계에서 새 효과를 실제 게임에 기본 적용하지 않는다"** 사양을 준수하여, 본 게임 코드([game.py](file:///c:/Users/nowco/Desktop/Dream/panda-game/game.py), [combat_system.py](file:///c:/Users/nowco/Desktop/Dream/panda-game/combat_system.py), [post_processing.py](file:///c:/Users/nowco/Desktop/Dream/panda-game/post_processing.py))는 일체 임의 수정하지 않고 기존 상태를 유지했습니다.
- 본 보고서와 독립 프리뷰 산출물을 바탕으로 사용자가 최종 채택을 결정하면 즉시 무결점 연동이 가능하도록 구조화되어 있습니다.
