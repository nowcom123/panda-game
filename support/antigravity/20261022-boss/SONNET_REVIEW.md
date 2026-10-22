# Antigravity Sonnet 4.6 최종 검토 지시서

프로젝트: `C:\Users\nowco\Desktop\Dream\panda-game`

사용자가 지정한 모델은 **Sonnet 4.6**이다. Antigravity에서 해당 모델을 선택한 뒤 이 작업을 진행한다. 이전 RESULT.md에는 Gemini 3.8 Flash 사용으로 기재되어 있어 Sonnet 협업 완료로 간주하지 않았다. 실제 모델 확인이 불가능하면 확인 불가로 보고하고 모델명을 추측하지 않는다.

## 현재 상태

Codex가 반환된 구현을 통합하고 오류를 수정했다. `CODEX_REVIEW.md`를 먼저 읽는다. 코드를 처음부터 재구현하지 않는다. 테스트와 실제 실행으로 확인할 수 있는 결함만 최소 수정한다.

## 검토할 내용

1. `monster.py`의 CableOverlordBoss: 큰 살색 해골, 원통형 척추·갈비뼈, 긴 회전 팔, 관절로 연결된 8개 뼈 다리. 회전 중 어깨뼈 연결, 공격 종료 후 자세 복원, 애니메이션을 따라가는 헤드샷 판정을 확인한다.
2. `boss_patterns.py`: 네 패턴이 예고→공격→회복→유휴로 반복되는지 확인한다. 예고 최소 0.8초, 벽 차단, 실제 플레이어 점프 높이로 휩쓸기/착지 회피, 고정된 예고 위치·사격 방향, 중복 피해 방지, 사망 즉시 정리를 검사한다.
3. `monster_director.py`: 실제 보스 인스턴스로 상태이상·패턴·이동 갱신이 중복되지 않는지 검사한다. 기존 테스트용 레거시 경로를 실제 게임 경로 검증으로 오인하지 않는다.
4. `ui_manager.py`: 실제 HP 변화가 즉시 숫자로 반영되고 막대는 왼쪽을 고정한 채 부드럽게 목표까지 감소하는지 확인한다.
5. 실제 게임 플레이에서 성능과 시인성을 확인한다. 근거 없는 FPS 수치를 보고하지 않는다. 현재 원거리 일제사격은 기존 Fireball 투사체를 재사용한다.

## 검증 명령

```powershell
python -m unittest discover -s tests
python support/antigravity/20261022-boss/verify_integration.py
python support/antigravity/20261022-boss/verify_hud.py
python support/antigravity/20261022-boss/render_boss_previews.py
```

`SONNET_RESULT.md`에 실제 사용 모델, 발견 사항, 수정 파일, 실행한 검증과 결과, 남은 한계를 기록한다. 기존 RESULT.md의 사용 모델 기록을 덮어쓰지 않는다.

사용자 변경인 `audio_system.py`, `rankings.json`과 이번 요청 밖 총기·퍽 코드는 수정하지 않는다. 커밋, 푸시, 패키지 업그레이드는 하지 않는다.
