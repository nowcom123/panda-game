import math
from panda3d.core import Fog, AmbientLight, Mat4

from constants import CHUNK_SIZE, FOG_COLOR


class LightingManager:
    """안개(Fog), 앰비언트 기본 조명, 청크 가시거리 컬링 및 동적 광원 8-Light 버짓 관리자"""

    def __init__(self, game):
        self.game = game
        self.light_cull_timer = 0.0
        self.last_light_cull_pos = None
        self.last_cull_pos = None

    def setup_fog(self):
        """지수 안개(Exponential Fog) 설정: 매끄럽고 몽환적인 자연스러운 거리 감쇠 안개 형성"""
        liminal_fog = Fog("LiminalDepthFog")
        liminal_fog.setColor(FOG_COLOR)
        liminal_fog.setExpDensity(0.038)
        self.game.render.setFog(liminal_fog)
        self.game.setBackgroundColor(FOG_COLOR)
        if hasattr(self.game, 'win') and self.game.win:
            self.game.win.setClearColor(FOG_COLOR)
        self.game.liminal_fog = liminal_fog
        return liminal_fog

    def setup_lighting(self):
        """기본 주변광(AmbientLight) 설정"""
        amb = AmbientLight('ambient_dim')
        amb.setColor((0.005, 0.005, 0.006, 1.0))
        amb_np = self.game.render.attachNewNode(amb)
        self.game.render.setLight(amb_np)
        self.game.amb_np = amb_np
        return amb_np

    def reset_cull_cache(self):
        """맵 재생성/초기화 시 컬링 캐시 초기화"""
        self.last_cull_pos = None
        self._cull_signature = None
        self.last_light_cull_pos = None
        self.light_cull_timer = 0.0
        self.game.last_cull_pos = None
        self.game.last_light_cull_pos = None
        self.game.light_cull_timer = 0.0

    def cull_chunks_to_view(self, force=False):
        """시야·렌즈·청크 변경 때만 청크 가시성을 다시 계산한다."""
        if getattr(self.game, 'is_test_mode', False):
            return
        px, py = self.game.camera.getX(), self.game.camera.getY()
        camera_matrix = self.game.cam.getMat(self.game.world_root)
        projection = self.game.camLens.getProjectionMat()
        signature = (Mat4(camera_matrix), Mat4(projection), px, py,
                     tuple((key, id(chunk)) for key, chunk in self.game.chunks.items()))
        if not force and signature == getattr(self, '_cull_signature', None):
            return
        # Camera frustum in the same parent space as the chunk bounds.
        # Recheck each frame: rotation, ADS/FOV and window resize all change it.
        frustum = self.game.camLens.makeBounds()
        frustum.xform(camera_matrix)

        self.last_cull_pos = (px, py)
        self.game.last_cull_pos = (px, py)
        chunk_rad = (CHUNK_SIZE / 2.0) * math.sqrt(2)
        max_visual_dist = 48.0
        max_dist_sq = (max_visual_dist + chunk_rad) ** 2

        visible_count = 0
        for (cx, cy), chunk in self.game.chunks.items():
            ccx = (cx + 0.5) * CHUNK_SIZE
            ccy = (cy + 0.5) * CHUNK_SIZE
            d_sq = (ccx - px) ** 2 + (ccy - py) ** 2
            is_visible = (d_sq <= max_dist_sq and
                          bool(frustum.contains(chunk.node.getBounds())))
            chunk.set_visible(is_visible)
            if is_visible:
                visible_count += 1

        self.game.rendered_chunk_count = visible_count
        self.game.total_chunk_count = len(self.game.chunks)
        self._cull_signature = signature

    def update_dynamic_lights(self, px, py, dt):
        """
        동적 광원 가시거리 컬링 및 조명 슬롯 버짓 관리 (SimplePBR 8-Light 최적화)
        - 탈출구 비콘, 보급 상자, 탄약 상자, 몬스터 오라 중 플레이어 반경 내 최근접 4개 조명만 엄선 활성화
        - 시야 밖/원거리 조명은 render.clearLight()로 즉시 차단하여 GPU 픽셀 셰이더 루프 부하 0%화
        """
        if getattr(self.game, 'is_test_mode', False):
            return
        self.light_cull_timer -= dt
        if self.light_cull_timer > 0.0:
            if self.last_light_cull_pos is not None:
                dx = px - self.last_light_cull_pos[0]
                dy = py - self.last_light_cull_pos[1]
                if (dx * dx + dy * dy) < 1.0:
                    return
        self.light_cull_timer = 0.08
        self.last_light_cull_pos = (px, py)
        self.game.last_light_cull_pos = (px, py)

        candidates = []

        # 1. 탈출 관문 비콘등 (최대 유효 반경 42m)
        if hasattr(self.game, 'beacon_light_np') and self.game.beacon_light_np and not self.game.beacon_light_np.isEmpty():
            ex, ey = getattr(self.game, 'escape_pos', (0, 0))
            d_sq = (px - ex) ** 2 + (py - ey) ** 2
            if d_sq <= 42.0 * 42.0:
                candidates.append((d_sq, self.game.beacon_light_np, self.game.render, self.game, 'beacon_is_lit'))
            elif getattr(self.game, 'beacon_is_lit', False):
                self.game.render.clearLight(self.game.beacon_light_np)
                self.game.beacon_is_lit = False

        # 2. 전술 보급 상자 네온등 (최대 유효 반경 25m)
        for cr in self.game.supply_crates:
            if not getattr(cr, 'is_opened', False) and hasattr(cr, 'beacon_np') and not cr.beacon_np.isEmpty():
                d_sq = (px - cr.pos.x) ** 2 + (py - cr.pos.y) ** 2
                if d_sq <= 25.0 * 25.0:
                    candidates.append((d_sq, cr.beacon_np, self.game.render, cr, 'beacon_is_lit'))
                elif getattr(cr, 'beacon_is_lit', False):
                    self.game.render.clearLight(cr.beacon_np)
                    cr.beacon_is_lit = False

        # 3. 필드 탄약 드롭 발광 (최대 유효 반경 18m)
        if hasattr(self.game, 'combat') and hasattr(self.game.combat, 'ammo_drops'):
            for drop in self.game.combat.ammo_drops:
                l_np = drop.get("light_np")
                if l_np and not l_np.isEmpty():
                    dx = px - drop["pos"][0]
                    dy = py - drop["pos"][1]
                    d_sq = dx * dx + dy * dy
                    if d_sq <= 18.0 * 18.0:
                        candidates.append((d_sq, l_np, self.game.render, drop, 'is_lit'))
                    elif drop.get("is_lit", False):
                        self.game.render.clearLight(l_np)
                        drop["is_lit"] = False

        # 3-2. 필드 전술 전리품 드랍 아이템 발광 (최대 유효 반경 20m)
        for drop in getattr(self.game, 'item_drops', []):
            if not getattr(drop, 'is_collected', False) and hasattr(drop, 'beacon_np') and not drop.beacon_np.isEmpty():
                d_sq = (px - drop.pos.x) ** 2 + (py - drop.pos.y) ** 2
                if d_sq <= 20.0 * 20.0:
                    candidates.append((d_sq, drop.beacon_np, self.game.render, drop, 'is_lit'))
                elif getattr(drop, 'is_lit', False):
                    self.game.render.clearLight(drop.beacon_np)
                    drop.is_lit = False

        # 4. 활성 몬스터 고유 오라 조명 (최대 유효 반경 22m)
        for m in self.game.monsters:
            if not getattr(m, 'is_corpse', False) and hasattr(m, 'aura_np') and not m.aura_np.isEmpty():
                d_sq = (px - m.pos.x) ** 2 + (py - m.pos.y) ** 2
                if d_sq <= 22.0 * 22.0:
                    candidates.append((d_sq, m.aura_np, self.game.render, m, 'aura_is_lit'))
                elif getattr(m, 'aura_is_lit', False):
                    self.game.render.clearLight(m.aura_np)
                    m.aura_is_lit = False

        # 거리순 정렬 후 최상위 4개 조명만 엄선
        candidates.sort(key=lambda item: item[0])
        for idx, (d_sq, l_np, parent_node, obj, lit_attr) in enumerate(candidates):
            if idx < 4:
                if not (obj[lit_attr] if isinstance(obj, dict) else getattr(obj, lit_attr, False)):
                    parent_node.setLight(l_np)
                    if isinstance(obj, dict):
                        obj[lit_attr] = True
                    else:
                        setattr(obj, lit_attr, True)
            else:
                if (obj[lit_attr] if isinstance(obj, dict) else getattr(obj, lit_attr, False)):
                    parent_node.clearLight(l_np)
                    if isinstance(obj, dict):
                        obj[lit_attr] = False
                    else:
                        setattr(obj, lit_attr, False)
