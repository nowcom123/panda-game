"""Weapon balance values shared by runtime and tools."""

WEAPON_CONFIGS = {
    "PISTOL": {
        "id": "PISTOL",
        "name": ".50 매그넘 데저트 이글",
        "max_ammo": 7,
        "initial_reserve": 28,
        "damage": 120.0,
        "headshot_mult": 4.2,
        "cooldown": 0.44,
        "combo_cooldown": 0.32,
        "pellets": 1,
        "base_spread": 0.012,
        "ads_spread": 0.0,
        "recoil_time": 0.18,
        "recoil_deg": 22.0,
        "reload_time": 1.45,
        "description": "7발 탄창. .50 Action Express 매그넘탄. 뼈를 부수는 파괴적인 단발 저지력과 관통력."
    },
    "DUAL_PISTOL": {
        "id": "DUAL_PISTOL",
        "name": "9mm 듀얼 글록 (아킴보)",
        "max_ammo": 34,
        "initial_reserve": 68,
        "damage": 26.0,
        "headshot_mult": 2.0,
        "cooldown": 0.065,
        "combo_cooldown": 0.048,
        "pellets": 1,
        "base_spread": 0.050,
        "ads_spread": 0.020,
        "recoil_time": 0.060,
        "recoil_deg": 7.5,
        "reload_time": 2.50,
        "description": "34발 대용량(양손 17발x2). 9mm 파라블럼 탄을 사용하는 듀얼 글록. 빠른 단발 클릭으로 뿜어져 나오는 양손 속사 화력."
    },
    "AR": {
        "id": "AR",
        "name": "5.56mm HK416 돌격소총 (AR)",
        "max_ammo": 30,
        "initial_reserve": 90,
        "damage": 38.0,
        "headshot_mult": 2.4,
        "cooldown": 0.082,
        "combo_cooldown": 0.065,
        "pellets": 1,
        "base_spread": 0.030,
        "ads_spread": 0.008,
        "recoil_time": 0.075,
        "recoil_deg": 14.0,
        "reload_time": 3.20,
        "description": "30발 탄창. 5.56x45mm NATO. 단행정 가스 피스톤 방식을 채용한 독일 H&K사의 하이엔드 돌격소총 HK416. 분당 730발 초고속 연사 화력(재장전 지연 3.2s)."
    },
    "SHOTGUN": {
        "id": "SHOTGUN",
        "name": "12게이지 펌프 샷건",
        "max_ammo": 8,
        "initial_reserve": 24,
        "damage": 25.0,
        "headshot_mult": 1.6,
        "cooldown": 0.72,
        "combo_cooldown": 0.58,
        "pellets": 8,
        "base_spread": 0.175,
        "ads_spread": 0.110,
        "recoil_time": 0.20,
        "recoil_deg": 26.0,
        "reload_time": 1.75,
        "pump_time": 0.44,
        "description": "8발 튜브 탄창. 1격발당 8발 대구경 벅샷 산탄과 펌프 액션 (초근접 광역 섬멸, 원거리 산탄 분산 및 위력 감쇄)."
    }
}
WEAPON_ORDER = ["PISTOL", "DUAL_PISTOL", "AR", "SHOTGUN"]
