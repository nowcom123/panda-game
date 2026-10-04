"""
Medieval Dark Fantasy Chunk Module (Optimized & Sealed)
- 3D 폐쇄형 석조 벽체 (Closed Solid Geometry)
- 맵 4면 외곽 경계벽 완전 밀폐 (0-A 남단, 0-B 서단, 북단 ht=1, 동단 vt=1)
- 매끄러운 무봉제 월드 정렬 바닥 (Seamless Continuous Floor with World-Aligned UV)
- 텍스처별 배칭 및 결합된 유기적 물웅덩이 데칼 (Batched Organic Puddle Decals with flattenStrong)
- 단조 철제 벽걸이 촛대 정적 메쉬 결합 (Batched Sconce Geometry with flattenStrong)
- 3D 발광 빌보드 불꽃 (Glowing Candle Flame Billboard)
"""

import os
import collections
import math
from panda3d.core import (
    CardMaker, TextureStage, NodePath, LColor, Point3, Material, TransparencyAttrib,
    TexturePool, Filename, SamplerState
)
from constants import (
    CELL_SIZE, CHUNK_CELLS, CHUNK_SIZE, TIER_HEIGHT, WALL_HEIGHT, DOOR_HEIGHT, WALL_THICKNESS,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import zone_hash, get_edge_types, cell_has_pillar

CANDLE_HEIGHT = 1.65

_PUDDLE_TEXTURES = None

def get_puddle_textures():
    """자연스러운 물웅덩이 데칼 텍스처 풀 (싱글톤 캐싱)"""
    global _PUDDLE_TEXTURES
    if _PUDDLE_TEXTURES is None:
        _PUDDLE_TEXTURES = []
        base_dir = os.path.dirname(__file__)
        for i in (1, 2, 3):
            p = os.path.join(base_dir, f'puddle_decal_{i}.png')
            if os.path.exists(p):
                tex = TexturePool.loadTexture(Filename.fromOsSpecific(p))
                if tex:
                    tex.setWrapU(SamplerState.WM_clamp)
                    tex.setWrapV(SamplerState.WM_clamp)
                    tex.setMagfilter(SamplerState.FT_linear_mipmap_linear)
                    tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
                    _PUDDLE_TEXTURES.append(tex)
    return _PUDDLE_TEXTURES


def add_solid_box(parent, x0, x1, y0, y1, z0, z1, tex, u_unit=3.5, v_unit=2.7, has_baseboard=True):
    """
    6면이 모두 닫힌 3D 완전 입체 벽체(Closed Solid Box) 생성.
    - Front(-Y), Back(+Y), Left(-X), Right(+X), Top(+Z), Bottom(-Z) 6면 완전 밀폐
    - 바닥면 침투(Z_min = -0.15m)로 바닥과 미세 틈새/들뜸/빛샘 완벽 방지
    - 벽체 하단부에 18cm 두께의 중세 던전 암석 베이스 기단(Stone Plinth Trim) 추가
    """
    dx = x1 - x0
    dy = y1 - y0
    dz = z1 - z0
    box = parent.attachNewNode('solid_box')
    box.setPos(x0, y0, z0)

    # 1. 6면 완전 밀폐 벽체 지오메트리
    # South (-Y)
    cm_s = CardMaker('s'); cm_s.setFrame(0, dx, 0, dz)
    s = box.attachNewNode(cm_s.generate())
    s.setTexture(tex)
    s.setTexScale(TextureStage.getDefault(), dx / u_unit, dz / v_unit)
    s.setTwoSided(True)

    # North (+Y)
    cm_n = CardMaker('n'); cm_n.setFrame(0, dx, 0, dz)
    n = box.attachNewNode(cm_n.generate())
    n.setPos(dx, dy, 0)
    n.setH(180)
    n.setTexture(tex)
    n.setTexScale(TextureStage.getDefault(), dx / u_unit, dz / v_unit)
    n.setTwoSided(True)

    # West (-X)
    cm_w = CardMaker('w'); cm_w.setFrame(0, dy, 0, dz)
    w = box.attachNewNode(cm_w.generate())
    w.setPos(0, dy, 0)
    w.setH(-90)
    w.setTexture(tex)
    w.setTexScale(TextureStage.getDefault(), dy / u_unit, dz / v_unit)
    w.setTwoSided(True)

    # East (+X)
    cm_e = CardMaker('e'); cm_e.setFrame(0, dy, 0, dz)
    e = box.attachNewNode(cm_e.generate())
    e.setPos(dx, 0, 0)
    e.setH(90)
    e.setTexture(tex)
    e.setTexScale(TextureStage.getDefault(), dy / u_unit, dz / v_unit)
    e.setTwoSided(True)

    # Top (+Z)
    cm_top = CardMaker('top'); cm_top.setFrame(0, dx, 0, dy)
    top = box.attachNewNode(cm_top.generate())
    top.setPos(0, 0, dz)
    top.setP(-90)
    top.setTexture(tex)
    top.setTexScale(TextureStage.getDefault(), dx / u_unit, dy / u_unit)
    top.setTwoSided(True)

    # Bottom (-Z)
    cm_bot = CardMaker('bot'); cm_bot.setFrame(0, dx, 0, dy)
    bot = box.attachNewNode(cm_bot.generate())
    bot.setPos(0, dy, 0)
    bot.setP(90)
    bot.setTexture(tex)
    bot.setTexScale(TextureStage.getDefault(), dx / u_unit, dy / u_unit)
    bot.setTwoSided(True)

    # 2. 중세 던전 석재 베이스 기단 (Stone Plinth Trim) - 암회색 풍화 화강암 톤
    if has_baseboard and z0 < 0.1:
        bb_h = 0.18 - z0
        bb_col = LColor(0.13, 0.13, 0.14, 1.0)

        cm_bs = CardMaker('bb_s'); cm_bs.setFrame(0, dx, 0, bb_h)
        bs = box.attachNewNode(cm_bs.generate())
        bs.setColor(bb_col)
        bs.setPos(0, -0.003, 0)
        bs.setTwoSided(True)

        cm_bn = CardMaker('bb_n'); cm_bn.setFrame(0, dx, 0, bb_h)
        bn = box.attachNewNode(cm_bn.generate())
        bn.setColor(bb_col)
        bn.setPos(dx, dy + 0.003, 0)
        bn.setH(180)
        bn.setTwoSided(True)

        cm_bw = CardMaker('bb_w'); cm_bw.setFrame(0, dy, 0, bb_h)
        bw = box.attachNewNode(cm_bw.generate())
        bw.setColor(bb_col)
        bw.setPos(-0.003, dy, 0)
        bw.setH(-90)
        bw.setTwoSided(True)

        cm_be = CardMaker('bb_e'); cm_be.setFrame(0, dy, 0, bb_h)
        be = box.attachNewNode(cm_be.generate())
        be.setColor(bb_col)
        be.setPos(dx + 0.003, 0, 0)
        be.setH(90)
        be.setTwoSided(True)

        # 상단 돌출 턱
        cm_br = CardMaker('bb_top'); cm_br.setFrame(0, dx, 0, dy + 0.006)
        br = box.attachNewNode(cm_br.generate())
        br.setColor(LColor(0.16, 0.16, 0.17, 1.0))
        br.setPos(0, -0.003, bb_h)
        br.setP(-90)
        br.setTwoSided(True)

    return box


def add_wall_candle_optimized(sconces_parent, flames_parent, x, y, z, nx, ny):
    """
    최적화된 3D 벽걸이 촛대 생성:
    - sconces_parent: 정적 메쉬 부품(백플레이트, 암, 받침대, 3D 십자 양초) -> flattenStrong 대상
    - flames_parent: 동적 빌보드 발광 불꽃 -> 자체 발광 및 카메라 추적
    반환값: 불꽃 중심 좌표 (Point3)
    """
    arm_len = 0.22
    iron_col = LColor(0.12, 0.12, 0.13, 1.0)
    wax_col = LColor(0.88, 0.84, 0.74, 1.0)

    # 1. 단조 철제 베이스 플레이트 (벽면 밀착)
    cm_bp = CardMaker('sconce_bp')
    cm_bp.setFrame(-0.07, 0.07, -0.12, 0.12)
    bp = sconces_parent.attachNewNode(cm_bp.generate())
    bp.setPos(x, y, z)
    bp.setColor(iron_col)
    bp.setTwoSided(True)
    if nx != 0:
        bp.setH(90 if nx < 0 else -90)
    else:
        bp.setH(0 if ny < 0 else 180)

    # 2. 단조 철제 암 (벽면에서 0.22m 돌출)
    cm_arm = CardMaker('sconce_arm')
    cm_arm.setFrame(-0.02, 0.02, 0, arm_len)
    arm = sconces_parent.attachNewNode(cm_arm.generate())
    arm.setPos(x, y, z - 0.02)
    arm.setColor(iron_col)
    arm.setP(-90)
    arm.setTwoSided(True)
    if nx != 0:
        arm.setH(90 if nx > 0 else -90)
    else:
        arm.setH(0 if ny > 0 else 180)

    # 3. 촛대 받침 접시 (Drip pan)
    cup_x = x + nx * arm_len
    cup_y = y + ny * arm_len
    cm_cup = CardMaker('drip_pan')
    cm_cup.setFrame(-0.07, 0.07, -0.07, 0.07)
    cup = sconces_parent.attachNewNode(cm_cup.generate())
    cup.setColor(LColor(0.18, 0.17, 0.16, 1.0))
    cup.setPos(cup_x, cup_y, z)
    cup.setP(-90)
    cup.setTwoSided(True)

    # 4. 정적 3D 양초 스틱 (정적 십자 쿼드)
    cm_wax1 = CardMaker('wax_1')
    cm_wax1.setFrame(-0.035, 0.035, 0, 0.16)
    w1 = sconces_parent.attachNewNode(cm_wax1.generate())
    w1.setColor(wax_col)
    w1.setPos(cup_x, cup_y, z)
    w1.setTwoSided(True)

    cm_wax2 = CardMaker('wax_2')
    cm_wax2.setFrame(-0.035, 0.035, 0, 0.16)
    w2 = sconces_parent.attachNewNode(cm_wax2.generate())
    w2.setColor(wax_col)
    w2.setPos(cup_x, cup_y, z)
    w2.setH(90)
    w2.setTwoSided(True)

    # 5. 자체 발광 촛불 불꽃 (Self-illuminating Glowing Flame Billboard)
    cm_flame = CardMaker('candle_flame')
    cm_flame.setFrame(-0.06, 0.06, 0, 0.18)
    flame = flames_parent.attachNewNode(cm_flame.generate())
    flame.setPos(cup_x, cup_y, z + 0.16)
    flame.setColor(LColor(1.0, 0.82, 0.32, 1.0))
    flame.setLightOff()
    flame.setTransparency(TransparencyAttrib.M_alpha)
    flame.setBillboardPointEye()

    return Point3(cup_x, cup_y, z + 0.20)


class Chunk:
    """중세 다크판타지 고성 던전 3D 청크 (최적화 배치, 외곽 100% 밀폐)"""
    def __init__(self, parent, cx, cy, floor_tex, wall_tex, sky_tex, floor_wet_tex=None):
        self.cx = cx
        self.cy = cy
        if parent is not None:
            self.node = parent.attachNewNode(f"chunk_{cx}_{cy}")
        else:
            self.node = NodePath(f"chunk_{cx}_{cy}")

        self.colliders = [] # [(min_x, min_y, max_x, max_y), ...]
        self.cell_colliders = collections.defaultdict(list)
        self.candle_positions = []
        self.is_hidden = False

        # 드로우 콜 최적화를 위한 지오메트리 루트 분리
        self.geom_root = self.node.attachNewNode("geom_root")
        self.sconces_root = self.node.attachNewNode("sconces_root")
        self.flames_root = self.node.attachNewNode("flames_root")
        self.puddles_root = self.node.attachNewNode("puddles_root")

        chunk_origin_x = cx * CHUNK_SIZE
        chunk_origin_y = cy * CHUNK_SIZE
        half_thick = WALL_THICKNESS / 2.0

        # 건식 석판 재질 (Roughness 0.85, 매트한 고대 던전 판석)
        dry_mat = Material('dry_cobblestone')
        dry_mat.setRoughness(0.85)
        dry_mat.setSpecular(LColor(0.08, 0.08, 0.08, 1.0))
        dry_mat.setShininess(12.0)

        # 1. 청크 바닥: 끊김 없는 일체형 대형 판석 (Seamless World-Aligned UV)
        cm_floor = CardMaker('chunk_continuous_floor')
        cm_floor.setFrame(0, CHUNK_SIZE, 0, CHUNK_SIZE)
        floor = self.geom_root.attachNewNode(cm_floor.generate())
        floor.setP(-90)
        floor.setPos(chunk_origin_x, chunk_origin_y, 0)
        floor.setTexture(floor_tex)

        # 월드 좌표 정렬 UV로 청크 간 경계선/바둑판 눈금 100% 제거
        uv_unit = 4.0
        floor.setTexScale(TextureStage.getDefault(), CHUNK_SIZE / uv_unit, CHUNK_SIZE / uv_unit)
        floor.setTexOffset(TextureStage.getDefault(), (chunk_origin_x / uv_unit) % 1.0, (chunk_origin_y / uv_unit) % 1.0)
        floor.setMaterial(dry_mat)
        floor.setColorScale(0.78, 0.76, 0.74, 1.0)

        # 2. 텍스처별 결합형 유기적 물웅덩이 데칼 (Batched Organic Puddle Decals)
        puddle_texs = get_puddle_textures()
        wet_mat = Material('wet_puddle_reflection')
        wet_mat.setRoughness(0.04)
        wet_mat.setMetallic(0.10)
        wet_mat.setSpecular(LColor(0.98, 0.95, 0.90, 1.0))
        wet_mat.setShininess(120.0)

        self.puddle_batches = []
        if puddle_texs:
            for idx, p_tex in enumerate(puddle_texs):
                batch_np = self.puddles_root.attachNewNode(f"puddle_batch_{idx}")
                batch_np.setTexture(p_tex)
                batch_np.setTransparency(TransparencyAttrib.M_alpha)
                batch_np.setMaterial(wet_mat)
                batch_np.setColorScale(0.88, 0.88, 0.94, 0.92)
                self.puddle_batches.append(batch_np)

        start_gx = cx * CHUNK_CELLS
        start_gy = cy * CHUNK_CELLS

        for i in range(CHUNK_CELLS):
            gx = start_gx + i
            cell_x = gx * CELL_SIZE
            for j in range(CHUNK_CELLS):
                gy = start_gy + j
                cell_y = gy * CELL_SIZE

                # 기둥 없는 빈 공간 중 약 38% 확률로 자연스러운 물웅덩이 배치
                if not cell_has_pillar(gx, gy) and ((gx * 73856093 ^ gy * 19349663 ^ 0x5bd1e995) % 100) < 38 and self.puddle_batches:
                    t_idx = (gx * 7 + gy * 13) % len(self.puddle_batches)
                    ox = (((gx * 37) % 100) / 100.0 - 0.5) * 1.5
                    oy = (((gy * 59) % 100) / 100.0 - 0.5) * 1.5
                    p_size = 2.6 + (((gx * 17 + gy * 31) % 100) / 100.0) * 1.6

                    cm_p = CardMaker(f'puddle_{gx}_{gy}')
                    cm_p.setFrame(-p_size * 0.5, p_size * 0.5, -p_size * 0.5, p_size * 0.5)
                    p_node = self.puddle_batches[t_idx].attachNewNode(cm_p.generate())
                    p_node.setP(-90)
                    p_node.setPos(cell_x + CELL_SIZE * 0.5 + ox, cell_y + CELL_SIZE * 0.5 + oy, 0.006)
                    p_node.setH((gx * 73 + gy * 109) % 360)

        # 3. 청크 천장: 아치형 석조 볼트 천장
        cm_ceil = CardMaker('ceiling')
        cm_ceil.setFrame(0, CHUNK_SIZE, 0, CHUNK_SIZE)
        ceil = self.geom_root.attachNewNode(cm_ceil.generate())
        ceil.setP(90)
        ceil.setPos(chunk_origin_x, chunk_origin_y + CHUNK_SIZE, WALL_HEIGHT)
        ceil.setTexture(sky_tex)
        ceil_scale = round(CHUNK_SIZE / 4.0, 2)
        ceil.setTexScale(TextureStage.getDefault(), ceil_scale, ceil_scale)
        ceil.setTexOffset(TextureStage.getDefault(), (chunk_origin_x / 4.0) % 1.0, (chunk_origin_y / 4.0) % 1.0)
        ceil.setColorScale(0.60, 0.60, 0.60, 1.0)
        ceil.setTwoSided(True)

        Z_MIN = -0.15
        Z_MAX = WALL_HEIGHT

        # 4. 청크 외곽 및 내부 벽체 지오메트리 생성
        for i in range(CHUNK_CELLS):
            gx = start_gx + i
            cell_x = gx * CELL_SIZE
            for j in range(CHUNK_CELLS):
                gy = start_gy + j
                cell_y = gy * CELL_SIZE

                ht, vt = get_edge_types(gx, gy)

                # 맵 북쪽/동쪽 최외곽 경계: 마주하는 인접 셀이 없으므로 무조건 밀폐 솔리드 벽체 강제
                if gy == (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 1:
                    ht = 1
                if gx == (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 1:
                    vt = 1

                # --- (0-A) 최남단 외곽 경계벽 완전 밀폐 (y = cell_y) ---
                if cy == MAP_MIN_CHUNK and j == 0:
                    x0 = cell_x - half_thick
                    x1 = cell_x + CELL_SIZE + half_thick
                    y0 = cell_y - half_thick
                    y1 = cell_y + half_thick
                    add_solid_box(self.geom_root, x0, x1, y0, y1, Z_MIN, Z_MAX, wall_tex, has_baseboard=True)
                    b_box_s = (x0, y0, x1, y1)
                    self.colliders.append(b_box_s)
                    self.cell_colliders[(gx, gy)].append(b_box_s)
                    self.cell_colliders[(gx, gy - 1)].append(b_box_s)

                    if gx % 2 == 0:
                        c_s = add_wall_candle_optimized(self.sconces_root, self.flames_root, cell_x + CELL_SIZE * 0.5, cell_y + half_thick, CANDLE_HEIGHT, 0, 1)
                        self.candle_positions.append(c_s)

                # --- (0-B) 최서단 외곽 경계벽 완전 밀폐 (x = cell_x) ---
                if cx == MAP_MIN_CHUNK and i == 0:
                    x0 = cell_x - half_thick
                    x1 = cell_x + half_thick
                    y0 = cell_y - half_thick
                    y1 = cell_y + CELL_SIZE + half_thick
                    add_solid_box(self.geom_root, x0, x1, y0, y1, Z_MIN, Z_MAX, wall_tex, has_baseboard=True)
                    b_box_w = (x0, y0, x1, y1)
                    self.colliders.append(b_box_w)
                    self.cell_colliders[(gx, gy)].append(b_box_w)
                    self.cell_colliders[(gx - 1, gy)].append(b_box_w)

                    if gy % 2 == 0:
                        c_w = add_wall_candle_optimized(self.sconces_root, self.flames_root, cell_x + half_thick, cell_y + CELL_SIZE * 0.5, CANDLE_HEIGHT, 1, 0)
                        self.candle_positions.append(c_w)

                # --- (1) 수평 벽체 (Horizontal Wall, y = wy) ---
                wy = cell_y + CELL_SIZE
                if ht == 1:
                    # [완전 차폐형 솔리드 벽체]
                    add_solid_box(self.geom_root, cell_x - half_thick, cell_x + CELL_SIZE + half_thick,
                                  wy - half_thick, wy + half_thick, Z_MIN, Z_MAX, wall_tex, has_baseboard=True)

                    col_box = (cell_x - half_thick, wy - half_thick, cell_x + CELL_SIZE + half_thick, wy + half_thick)
                    self.colliders.append(col_box)
                    self.cell_colliders[(gx, gy)].append(col_box)
                    self.cell_colliders[(gx, gy + 1)].append(col_box)

                    # 12m 간격 남/북 양면에 벽걸이 촛불 배치
                    if gx % 2 == 0:
                        c_s = add_wall_candle_optimized(self.sconces_root, self.flames_root, cell_x + CELL_SIZE * 0.5, wy - half_thick, CANDLE_HEIGHT, 0, -1)
                        self.candle_positions.append(c_s)
                        if gy + 1 < (MAP_MAX_CHUNK + 1) * CHUNK_CELLS:
                            c_n = add_wall_candle_optimized(self.sconces_root, self.flames_root, cell_x + CELL_SIZE * 0.5, wy + half_thick, CANDLE_HEIGHT, 0, 1)
                            self.candle_positions.append(c_n)

                elif ht == 2:
                    # [출입구 벽체]
                    add_solid_box(self.geom_root, cell_x - half_thick, cell_x + CELL_SIZE + half_thick,
                                  wy - half_thick, wy + half_thick, DOOR_HEIGHT, Z_MAX, wall_tex, has_baseboard=False)
                    add_solid_box(self.geom_root, cell_x - half_thick, cell_x,
                                  wy - half_thick, wy + half_thick, Z_MIN, DOOR_HEIGHT, wall_tex, has_baseboard=True)
                    add_solid_box(self.geom_root, cell_x + CELL_SIZE, cell_x + CELL_SIZE + half_thick,
                                  wy - half_thick, wy + half_thick, Z_MIN, DOOR_HEIGHT, wall_tex, has_baseboard=True)

                    col_l = (cell_x - half_thick, wy - half_thick, cell_x, wy + half_thick)
                    col_r = (cell_x + CELL_SIZE, wy - half_thick, cell_x + CELL_SIZE + half_thick, wy + half_thick)
                    self.colliders.extend([col_l, col_r])
                    self.cell_colliders[(gx, gy)].extend([col_l, col_r])
                    self.cell_colliders[(gx, gy + 1)].extend([col_l, col_r])

                # --- (2) 수직 벽체 (Vertical Wall, x = wx) ---
                wx = cell_x + CELL_SIZE
                if vt == 1:
                    # [완전 차폐형 솔리드 벽체]
                    add_solid_box(self.geom_root, wx - half_thick, wx + half_thick,
                                  cell_y - half_thick, cell_y + CELL_SIZE + half_thick, Z_MIN, Z_MAX, wall_tex, has_baseboard=True)

                    col_box = (wx - half_thick, cell_y - half_thick, wx + half_thick, cell_y + CELL_SIZE + half_thick)
                    self.colliders.append(col_box)
                    self.cell_colliders[(gx, gy)].append(col_box)
                    self.cell_colliders[(gx + 1, gy)].append(col_box)

                    # 12m 간격 동/서 양면에 벽걸이 촛불 배치
                    if gy % 2 == 0:
                        c_w = add_wall_candle_optimized(self.sconces_root, self.flames_root, wx - half_thick, cell_y + CELL_SIZE * 0.5, CANDLE_HEIGHT, -1, 0)
                        self.candle_positions.append(c_w)
                        if gx + 1 < (MAP_MAX_CHUNK + 1) * CHUNK_CELLS:
                            c_e = add_wall_candle_optimized(self.sconces_root, self.flames_root, wx + half_thick, cell_y + CELL_SIZE * 0.5, CANDLE_HEIGHT, 1, 0)
                            self.candle_positions.append(c_e)

                elif vt == 2:
                    # [출입구 벽체]
                    add_solid_box(self.geom_root, wx - half_thick, wx + half_thick,
                                  cell_y - half_thick, cell_y + CELL_SIZE + half_thick, DOOR_HEIGHT, Z_MAX, wall_tex, has_baseboard=False)
                    add_solid_box(self.geom_root, wx - half_thick, wx + half_thick,
                                  cell_y - half_thick, cell_y, Z_MIN, DOOR_HEIGHT, wall_tex, has_baseboard=True)
                    add_solid_box(self.geom_root, wx - half_thick, wx + half_thick,
                                  cell_y + CELL_SIZE, cell_y + CELL_SIZE + half_thick, Z_MIN, DOOR_HEIGHT, wall_tex, has_baseboard=True)

                    col_s = (wx - half_thick, cell_y - half_thick, wx + half_thick, cell_y)
                    col_n = (wx - half_thick, cell_y + CELL_SIZE, wx + half_thick, cell_y + CELL_SIZE + half_thick)
                    self.colliders.extend([col_s, col_n])
                    self.cell_colliders[(gx, gy)].extend([col_s, col_n])
                    self.cell_colliders[(gx + 1, gy)].extend([col_s, col_n])

                # --- (3) 사각 기둥 (Pillar Column) ---
                if cell_has_pillar(gx, gy):
                    px = cell_x + CELL_SIZE * 0.5
                    py = cell_y + CELL_SIZE * 0.5
                    p_thick = 1.05
                    half_p = p_thick * 0.5

                    add_solid_box(self.geom_root, px - half_p, px + half_p,
                                  py - half_p, py + half_p, Z_MIN, Z_MAX, wall_tex, has_baseboard=True)

                    col_pillar = (px - half_p, py - half_p, px + half_p, py + half_p)
                    self.colliders.append(col_pillar)
                    self.cell_colliders[(gx, gy)].append(col_pillar)

                    # 기둥 외벽면에 촛불 배치
                    if (gx + gy) % 2 == 0:
                        c_p = add_wall_candle_optimized(self.sconces_root, self.flames_root, px, py - half_p, CANDLE_HEIGHT, 0, -1)
                        self.candle_positions.append(c_p)

        # 5. 드로우 콜 결합 최적화 (flattenStrong)
        self.geom_root.flattenStrong()
        self.sconces_root.flattenStrong()
        for batch_np in self.puddle_batches:
            batch_np.flattenStrong()

    def set_visible(self, visible):
        """1인칭 시야각 청크 표시/숨김 전환"""
        if visible:
            if self.is_hidden:
                self.node.show()
                self.is_hidden = False
        else:
            if not self.is_hidden:
                self.node.hide()
                self.is_hidden = True

    def attach_to(self, parent):
        """월드 루트에 청크 연결"""
        if self.node and parent and not self.node.hasParent():
            self.node.reparentTo(parent)

    def destroy(self):
        """청크 노드 및 충돌체, 촛불 메모리 해제"""
        if self.node:
            self.node.removeNode()
            self.node = None
        self.colliders.clear()
        if hasattr(self, 'cell_colliders'):
            self.cell_colliders.clear()
        if hasattr(self, 'candle_positions'):
            self.candle_positions.clear()
        if hasattr(self, 'puddle_batches'):
            self.puddle_batches.clear()
