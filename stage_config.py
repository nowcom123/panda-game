"""층별 몬스터 편성과 안내. 렌더링·전투 상태와 독립적인 설정입니다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StageProfile:
    name: str
    summary: str
    tip: str
    reinforcements: tuple[str, str]


INTRO_PROFILES = (
    StageProfile("첫 번째 악몽", "룬 제단 3개를 각인하고 관문으로 탈출하세요.",
                 "제단 근처에서 E를 유지하세요. 공격 예고가 보이면 피하세요.",
                 ("orc", "witch")),
    StageProfile("미로의 심연", "몬스터가 늘어납니다. 보급품을 확보하세요.",
                 "스토커의 도약 화살표를 보고 옆으로 피하세요.",
                 ("orc", "witch")),
)

DEEP_PROFILES = (
    StageProfile("진흙의 파수대", "오크·해골 증원 — 근접 압박에 대비하세요.",
                 "오크의 지진 예고를 확인하고 해골과 거리를 유지하세요.",
                 ("orc", "skeleton")),
    StageProfile("잿불의 회랑", "마녀·뱀 증원 — 사선을 확인하며 이동하세요.",
                 "마녀가 지팡이를 밝히면 엄폐물을 이용하세요.",
                 ("witch", "serpent")),
    StageProfile("그림자 사냥터", "스토커·뱀 증원 — 도약 방향을 주시하세요.",
                 "스토커의 도약을 옆으로 피하고 노출된 심장을 노리세요.",
                 ("stalker", "serpent")),
)

BASE_ROSTER = ("stalker", "orc", "orc", "witch", "witch", "serpent", "skeleton")


def get_stage_profile(stage):
    if stage < 1:
        raise ValueError("stage must be at least 1")
    if stage <= 2:
        return INTRO_PROFILES[stage - 1]
    return DEEP_PROFILES[(stage - 3) % len(DEEP_PROFILES)]


def build_monster_roster(stage):
    """기존 총수와 첫 두 층을 유지하고, 심층 증원 중 최대 3쌍을 교체합니다."""
    profile = get_stage_profile(stage)
    roster = list(BASE_ROSTER)
    if stage >= 2:
        roster.append("stalker")
    themed_pairs = min(3, max(0, stage - 2))
    for _ in range(stage - 1 - themed_pairs):
        roster.extend(("orc", "witch"))
    for _ in range(themed_pairs):
        roster.extend(profile.reinforcements)
    return tuple(roster)
