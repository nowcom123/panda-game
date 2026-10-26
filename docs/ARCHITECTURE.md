# 코드 구조와 검증

## 실행 및 모듈 경계

프로젝트 루트에서 `.venv/Scripts/python.exe game.py`로 실행한다.
기존 실행 파일, 에셋 상대 경로, 저장 데이터 위치는 유지한다.

| 위치 | 담당 |
|---|---|
| `game.py` | 앱 초기화, 게임 상태, 프레임 갱신 연결 |
| `combat_system.py` | 사격 판정, 무기 조작, 재장전, 뷰모델 연결 |
| `combat/weapon_config.py` | 4종 무기 수치와 전환 순서 |
| `combat/tracer_effects.py` | 탄도 선 지오메트리 재사용, 비행·착탄·소멸 |
| `weapon_recoil.py`, `casing_effects.py` | 반동과 탄피 효과 |
| `monster.py`, `monster_director.py` | 적 모델·상태 및 AI 갱신 |
| `enemy_approach.py`, `boss_patterns.py` | 역할별 접근 목표 및 보스 패턴 |
| `chunk.py`, `world_gen.py` | 청크 지오메트리와 맵 생성 |
| `collision.py`, `navigation.py` | 충돌과 경로 탐색 |
| `lighting_manager.py`, `post_processing.py` | 가시성·조명과 화면 후처리 |
| `ui_manager.py`, `audio_system.py` | UI 및 오디오 |
| `tests/` | 자동 회귀 검사 |
| `support/` | 벤치마크, 렌더 검증, 협업 시안 |
| `assets/` | 게임 리소스 |

`combat_system.WEAPON_CONFIGS`와 `WEAPON_ORDER`는 호환성을 위해 계속 노출한다.
새 데이터 조회 코드는 `combat.weapon_config`에서 직접 가져올 수 있다.
탄도 갱신 모듈은 게임 앱 전체를 참조하지 않고 목록·렌더 부모·효과 dt만 받는다.

## 2026-10-24 정리 및 최적화

- 전투 데이터와 탄도 이펙트를 별도 패키지로 분리했다.
- 실내 청크에서 사용하지 않는 `sky.jpg`의 필수 로드를 제거했다. 생성자 호환 인자는 유지한다.
- 탄도 노드 재사용을 유지하면서 소멸 목록을 한 번의 순회로 정리한다.
  기존 목록 객체와 남은 궤적의 순서를 보존한다.
- 청크 컬링은 카메라 변환, 렌즈 투영, 청크 구성에 변화가 없으면 이전 결과를 재사용한다.
  회전·이동·FOV·화면비 변경, 청크 추가/삭제/교체, 명시적 `force=True`는 다시 계산한다.
- 청크 지오메트리를 같은 객체 안에서 바꾸는 기능을 추가할 경우 `reset_cull_cache()` 또는
  `cull_chunks_to_view(force=True)`로 가시성을 갱신해야 한다. 현재 청크는 생성 후 정적이다.
- 충돌·적 AI·무기 수치는 이 정리 작업에서 변경하지 않았다.

## 검증 명령

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests
.venv/Scripts/python.exe support/benchmark_culling.py
.venv/Scripts/python.exe support/antigravity/20261021-gunfeel/verify_integration.py
.venv/Scripts/python.exe support/antigravity/20261022-boss/verify_integration.py
```

벤치마크는 정지 상태와 회전 상태를 분리한 CPU 검사다. GPU 렌더링이나 전체 게임 FPS를
측정하지 않으며, 정지 상태의 결과를 이동 중 개선율로 해석하면 안 된다.
대형 UI·몬스터 모듈의 추가 분리는 관련 기능의 검증을 확보하면서 진행한다.
