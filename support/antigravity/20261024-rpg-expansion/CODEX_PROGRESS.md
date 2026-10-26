# Codex 작업 현황 — 2026-10-25

## 완료: A1 스테이지 성장

- boss_scaling.py: 스테이지 3 기준 체력/부위/피해/이동 배율. 생성 시 1회만 적용.
- game.py: 실제 보스 생성 시 적용, HUD에 증가한 최대 HP 전달.
- boss_patterns.py: 휩쓸기/가시/착지/일제사격 피해 배율, 2페이즈 이동 배율 보존.
- monster_director.py: 레거시 보스 공격도 배율 적용. 스케일 적용 보스는 일반 적 이동 가속 제외.
- projectiles.py/game.py: damage_scale 인자를 전달하고 풀 재사용 때 기본 피해로 재설정.
- GroundShockwave는 시각 효과이므로 별도 피해를 부여하지 않았다.

검증: `.venv/Scripts/python.exe -m unittest discover -s tests` — 247개 통과.
새 5개 검사에서는 실제 보스 노드와 패턴, 실제 spawn_boss 함수와 HUD 인자,
부위 파괴 후 재적용 방지, 2페이즈, 풀 소진/비활성 재사용을 검사했다.
테스트에서 게임을 시작하거나 사용자 저장/순위 파일을 쓰지 않았다.
실제 플레이 체감 밸런스와 신규 UI의 화면 검증은 아직 하지 않았다.

## Antigravity 후속 작업

TASK.md의 A2 신규 기믹 → B 캐릭터 생성/저장 → C 인벤토리를 구현한다.
A1의 HUD 레벨/부위 상태 표시도 포함한다. 완료 결과는 RESULT.md에 작성한다.
Codex는 반환된 실제 코드와 결과를 검토하고 저장 격리·이관·패턴·UI 회귀를 확인한다.

전달 프롬프트:

```text
support/antigravity/20261024-rpg-expansion/TASK.md와 CODEX_PROGRESS.md를 읽고 작업해줘.
Codex가 구현한 A1 스테이지 성장 로직은 유지하고 A2 → B → C 순서로 구현해줘.
기존 사용자 저장과 다른 변경을 보존하고, 임시 저장소 테스트 및 UI 캡처를 수행해줘.
완료한 범위와 검증 결과, 남은 문제를 같은 폴더 RESULT.md에 기록해줘.
```
