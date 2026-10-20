"""
perks.py - 백룸 서바이벌 로그라이크 퍽(Perk) 및 시너지 카드 시스템

플레이어가 레벨업하거나 스테이지를 클리어할 때 3장의 무작위 퍽 카드가 제시되며,
플레이어는 상황과 빌드에 맞는 카드를 선택하여 고유한 전투 스타일과 시너지를 구축합니다.
"""

import random

# 퍽 희귀도 (Rarity) 정의 및 테마 색상 (RGBA)
RARITY_COMMON = "COMMON"       # 일반 (청록/시안)
RARITY_RARE = "RARE"           # 희귀 (보라/자수정)
RARITY_EPIC = "EPIC"           # 영웅 (황금/앰버)
RARITY_LEGENDARY = "LEGEND"    # 전설 (타오르는 핏빛/네온 레드)

RARITY_COLORS = {
    RARITY_COMMON: (0.35, 0.85, 1.0, 1.0),
    RARITY_RARE: (0.75, 0.40, 1.0, 1.0),
    RARITY_EPIC: (1.0, 0.82, 0.20, 1.0),
    RARITY_LEGENDARY: (1.0, 0.30, 0.30, 1.0),
}

RARITY_NAMES = {
    RARITY_COMMON: "일반 퍽",
    RARITY_RARE: "희귀 퍽",
    RARITY_EPIC: "영웅 퍽",
    RARITY_LEGENDARY: "전설 퍽",
}

# 12종의 고유 전술 퍽 카탈로그
PERK_CATALOG = {
    "ricochet": {
        "id": "ricochet",
        "name": "도탄 사격",
        "icon": "◆",
        "rarity": RARITY_RARE,
        "category": "전술 사격",
        "desc": "벽면에 착탄한 탄환이 튕겨 반경 14m 이내의 가장 가까운 적을 자동 추적 타격합니다. (도탄 피해 70%)",
        "tags": ["도탄", "추적", "다중타격"],
        "max_level": None,
    },
    "shrapnel_burst": {
        "id": "shrapnel_burst",
        "name": "파편 폭발",
        "icon": "★",
        "rarity": RARITY_EPIC,
        "category": "폭발 살상",
        "desc": "적 처치 시 시체에서 고열 파편이 사방으로 비산하여 반경 3.8m 내 적들에게 75의 범위 폭발 피해를 입힙니다.",
        "tags": ["처치 발동", "광역 피해", "연쇄 폭발"],
        "max_level": None,
    },
    "adrenaline_slide": {
        "id": "adrenaline_slide",
        "name": "아드레날린 슬라이딩",
        "icon": "▶",
        "rarity": RARITY_RARE,
        "category": "기동 전술",
        "desc": "슬라이딩 중 사격 시 1.8초간 불릿타임(시간 감속)이 발동하며 탄환 피해가 1.5배로 증폭됩니다.",
        "tags": ["슬라이드", "불릿타임", "대미지 증폭"],
        "max_level": None,
    },
    "vampiric_leech": {
        "id": "vampiric_leech",
        "name": "흡혈 탄환",
        "icon": "♥",
        "rarity": RARITY_RARE,
        "category": "생존 흡혈",
        "desc": "적 처치 시 체력 +12 회복, 헤드샷 치명타 적중 시 체력 +5를 즉시 흡수합니다.",
        "tags": ["흡혈", "체력 회복", "헤드샷 시너지"],
        "max_level": None,
    },
    "armor_piercing": {
        "id": "armor_piercing",
        "name": "장갑 관통탄",
        "icon": "▲",
        "rarity": RARITY_COMMON,
        "category": "탄약 개조",
        "desc": "모든 탄환이 적 1체를 완전히 관통하여 후방에 위치한 적에게도 100% 온전한 피해를 전달합니다.",
        "tags": ["관통", "다중 타격", "일렬 소탕"],
        "max_level": None,
    },
    "bullet_storm": {
        "id": "bullet_storm",
        "name": "탄환 폭풍",
        "icon": "★",
        "rarity": RARITY_LEGENDARY,
        "category": "화력 폭주",
        "desc": "적 처치 시 3.5초간 '탄환 폭풍' 폭주가 발동하여 탄약 소모 없이 무한 연사 및 연사 속도 +35%가 적용됩니다.",
        "tags": ["무한 탄약", "연사 속도", "처치 폭주"],
        "max_level": None,
    },
    "tesla_arc": {
        "id": "tesla_arc",
        "name": "테슬라 아크",
        "icon": "◆",
        "rarity": RARITY_RARE,
        "category": "원소 감전",
        "desc": "헤드샷 또는 치명타 적중 시 주변 6m 내 최대 2마리의 몬스터에게 35의 연쇄 전기 방전 충격을 가합니다.",
        "tags": ["치명타", "연쇄 번개", "스턴 유발"],
        "max_level": None,
    },
    "dragons_breath": {
        "id": "dragons_breath",
        "name": "드래곤 브레스",
        "icon": "★",
        "rarity": RARITY_EPIC,
        "category": "화염 소이",
        "desc": "샷건 및 총기 탄환이 적을 발화시켜 3.0초간 초당 25의 지속 화염 피해를 입힙니다.",
        "tags": ["지속 피해", "소이탄", "샷건 극대화"],
        "max_level": None,
    },
    "cluster_grenade": {
        "id": "cluster_grenade",
        "name": "집속 수류탄",
        "icon": "●",
        "rarity": RARITY_EPIC,
        "category": "폭발 무기고",
        "desc": "전술 수류탄 폭발 시 4개의 미니 자탄이 사방으로 흩어져 0.35초 후 연쇄 2차 폭발(각 90 피해)을 일으킵니다.",
        "tags": ["수류탄 강화", "클러스터", "광범위 섬멸"],
        "max_level": None,
    },
    "titan_armor": {
        "id": "titan_armor",
        "name": "타이탄 방탄 외골격",
        "icon": "■",
        "rarity": RARITY_COMMON,
        "category": "방어 장갑",
        "desc": "받는 모든 피해가 상시 25% 감소하며, 몬스터의 넉백 및 땅울림 슬로우 효과를 50% 억제합니다.",
        "tags": ["피해 감소", "군중 제어 저항", "탱킹"],
        "max_level": None,
    },
    "speed_demon": {
        "id": "speed_demon",
        "name": "스피드 데몬",
        "icon": "▶▶",
        "rarity": RARITY_COMMON,
        "category": "전술 기동",
        "desc": "기본 이동 속도 +20%, 재장전 속도 +35% 가속 및 달리기 스테미나 소모량이 40% 감소합니다.",
        "tags": ["이동 속도", "재장전 가속", "스프린트"],
        "max_level": None,
    },
    "headhunter": {
        "id": "headhunter",
        "name": "헤드헌터 현상금",
        "icon": "★",
        "rarity": RARITY_RARE,
        "category": "정밀 저격",
        "desc": "헤드샷 치명타 피해 배율이 +1.5배 증가하며, 헤드샷으로 적 처치 시 2배의 경험치를 획득합니다.",
        "tags": ["헤드샷 배율", "경험치 2배", "정밀 저격"],
        "max_level": None,
    },
}


def draw_random_perks(player_perks, count=3):
    """신규 획득과 보유 퍽 강화를 함께 추첨하되 한 번의 제안에는 중복하지 않는다."""
    pool = list(PERK_CATALOG)

    # 희귀도별 가중치: COMMON=50, RARE=35, EPIC=12, LEGENDARY=3
    weights = []
    for pid in pool:
        rarity = PERK_CATALOG[pid]["rarity"]
        if rarity == RARITY_COMMON:
            weights.append(50)
        elif rarity == RARITY_RARE:
            weights.append(35)
        elif rarity == RARITY_EPIC:
            weights.append(12)
        else:
            weights.append(3)

    chosen_ids = []
    available_indices = list(range(len(pool)))

    for _ in range(min(count, len(pool))):
        sub_weights = [weights[i] for i in available_indices]
        pick_idx = random.choices(available_indices, weights=sub_weights, k=1)[0]
        chosen_ids.append(pool[pick_idx])
        available_indices.remove(pick_idx)

    return [PERK_CATALOG[pid] for pid in chosen_ids]


def get_perk_definition(perk_id):
    """지정된 ID의 특성 정보를 반환합니다."""
    return PERK_CATALOG.get(perk_id)


def get_perk_level(player, perk_id):
    """Legacy owned-only saves/fixtures count as level 1."""
    if player is None:
        return 0
    levels = getattr(player, 'perk_levels', {})
    if perk_id in levels:
        return max(0, int(levels[perk_id]))
    return int(perk_id in getattr(player, 'perks', set()))


def get_perk_stats(perk_id, level):
    """Single source of truth for combat effects and card descriptions."""
    n = max(0, int(level))
    d = max(0, n - 1)
    if perk_id == 'ricochet':
        return dict(damage_mult=.70 + .15*d, range=14 + 2*d)
    if perk_id == 'shrapnel_burst':
        return dict(damage=75 + 25*d, radius=3.8 + .4*d)
    if perk_id == 'adrenaline_slide':
        return dict(damage_mult=1 + .5*n, duration=1.8 + .4*d)
    if perk_id == 'vampiric_leech':
        return dict(kill_heal=12*n, headshot_heal=5*n)
    if perk_id == 'armor_piercing':
        return dict(targets=n)
    if perk_id == 'bullet_storm':
        return dict(duration=3.5 + d, cooldown_mult=1 / (1 + (1/.65 - 1)*n))
    if perk_id == 'tesla_arc':
        return dict(damage=35 + 15*d, radius=7.5 + .5*d, targets=min(8, n+1),
                    shock_duration=.85 + .1*d, primary_duration=.65 + .1*d,
                    stun_duration=.4 + .05*d)
    if perk_id == 'dragons_breath':
        return dict(dps=25 + 10*d, duration=3 + .5*d)
    if perk_id == 'cluster_grenade':
        return dict(count=min(12, n+3), damage=90 + 30*d, radius=3.5 + .2*d)
    if perk_id == 'titan_armor':
        return dict(damage_mult=.75**n, slow_duration_mult=.5**n,
                    slow_strength_mult=.5**n, bonus_hp=25*n)
    if perk_id == 'speed_demon':
        return dict(move_mult=1 + .2*n, reload_mult=max(.1, .65**n),
                    stamina_mult=.6**n)
    if perk_id == 'headhunter':
        return dict(damage_mult=1 + .45*n, xp_mult=1+n)
    raise KeyError(perk_id)


def get_player_perk_stats(player, perk_id):
    return get_perk_stats(perk_id, get_perk_level(player, perk_id))


def describe_perk(perk_id, level):
    s = get_perk_stats(perk_id, level)
    if perk_id == 'ricochet':
        return f"벽 착탄 시 {s['range']:g}m 내 적 추적. 도탄 피해 {s['damage_mult']*100:g}%."
    if perk_id == 'shrapnel_burst':
        return f"처치 시 반경 {s['radius']:g}m에 파편 피해 {s['damage']:g}."
    if perk_id == 'adrenaline_slide':
        return f"슬라이딩 사격 피해 {s['damage_mult']:g}배, 불릿타임 {s['duration']:g}초."
    if perk_id == 'vampiric_leech':
        return f"처치 시 체력 +{s['kill_heal']:g}, 헤드샷 적중 시 +{s['headshot_heal']:g} 회복."
    if perk_id == 'armor_piercing':
        return f"후방 적 최대 {s['targets']}체 추가 관통. 피해 100% 전달."
    if perk_id == 'bullet_storm':
        return f"처치 시 {s['duration']:g}초간 무한 탄약. 발사 간격 {(1-s['cooldown_mult'])*100:.1f}% 단축."
    if perk_id == 'tesla_arc':
        return f"치명타 시 {s['radius']:g}m 내 {s['targets']}체에 전기 피해 {s['damage']:g}. 감전 {s['shock_duration']:g}초."
    if perk_id == 'dragons_breath':
        return f"적중 시 {s['duration']:g}초간 초당 {s['dps']:g} 화염 피해."
    if perk_id == 'cluster_grenade':
        return f"수류탄 자탄 {s['count']}개. 각각 반경 {s['radius']:g}m에 {s['damage']:g} 피해."
    if perk_id == 'titan_armor':
        return f"받는 피해 {(1-s['damage_mult'])*100:.1f}% 감소, 최대 체력 +{s['bonus_hp']}. 감속 강도·시간 {(1-s['slow_duration_mult'])*100:.1f}% 감소."
    if perk_id == 'speed_demon':
        return f"이동 +{(s['move_mult']-1)*100:.0f}%, 장전 시간 {(1-s['reload_mult'])*100:.1f}% 단축, 달리기 소모 {(1-s['stamina_mult'])*100:.1f}% 감소."
    if perk_id == 'headhunter':
        return f"헤드샷 피해 {s['damage_mult']:g}배, 헤드샷 처치 경험치 {s['xp_mult']:g}배."
    raise KeyError(perk_id)


# Every perk can be upgraded. Bounded particle counts keep late-game effects cheap.
for _perk_id, _definition in PERK_CATALOG.items():
    _definition['desc'] = describe_perk(_perk_id, 1)
