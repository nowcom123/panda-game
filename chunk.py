import collections
from panda3d.core import CardMaker, TextureStage, NodePath, LColor
from constants import (
    CELL_SIZE, CHUNK_CELLS, CHUNK_SIZE, TIER_HEIGHT, WALL_HEIGHT, DOOR_HEIGHT, WALL_THICKNESS,
    MAP_MIN_CHUNK, MAP_MAX_CHUNK
)
from world_gen import zone_hash, get_edge_types, cell_has_pillar




class Chunk:
    """백룸 무한 타일, 2단 두꺼운 3D 솔리드 벽체, 문틀 소핏, 촛대 및 자체 발광 촛불로 구성된 청크"""
    def __init__(self, parent, cx, cy, floor_tex, wall_tex, sky_tex):
        self.cx = cx
        self.cy = cy
        if parent is not None:
            self.node = parent.attachNewNode(f"chunk_{cx}_{cy}")
        else:
            self.node = NodePath(f"chunk_{cx}_{cy}")
        self.colliders = [] # [(min_x, min_y, max_x, max_y), ...]
        self.cell_colliders = collections.defaultdict(list) # (gx, gy) -> [collider, ...] 초고속 공간 인덱스
        self.is_hidden = False

        chunk_origin_x = cx * CHUNK_SIZE
        chunk_origin_y = cy * CHUNK_SIZE
        half_thick = WALL_THICKNESS / 2.0

        # 1. 청크 바닥 타일 (Chunk Floor)
        cm_floor = CardMaker('floor')
        cm_floor.setFrame(0, CHUNK_SIZE, 0, CHUNK_SIZE)
        floor = self.node.attachNewNode(cm_floor.generate())
        floor.setP(-90)
        floor.setPos(chunk_origin_x, chunk_origin_y, 0)
        floor.setTexture(floor_tex)
        floor.setTexScale(TextureStage.getDefault(), round(CHUNK_SIZE / 3.5, 2), round(CHUNK_SIZE / 3.5, 2))
        floor.setColorScale(0.60, 0.58, 0.52, 1.0) # 어두운 심야 카펫 톤

        # 2. 청크 천장 타일 (바닥과 동일한 텍스처 에셋 적용)
        ceil = self.node.attachNewNode(cm_floor.generate())
        ceil.setP(90)
        ceil.setPos(chunk_origin_x, chunk_origin_y + CHUNK_SIZE, WALL_HEIGHT)
        ceil.setTexture(floor_tex)
        floor_scale = round(CHUNK_SIZE / 3.5, 2)
        ceil.setTexScale(TextureStage.getDefault(), floor_scale, floor_scale)
        ceil.setColorScale(0.60, 0.58, 0.52, 1.0) # 바닥과 일체감 있는 리미널 카펫/타일 톤
        ceil.setTwoSided(True)

        # 텍스처 수직/수평 반복 비율 (높아진 벽체 및 광폭 복도에 맞춘 자연스러운 종횡비 유지)
        wall_len = CELL_SIZE + 2.0 * half_thick
        wall_u_scale = round(wall_len / 3.5, 2)
        wall_v_scale = round(TIER_HEIGHT / 2.7, 2)
        lintel_v_scale = round((TIER_HEIGHT - DOOR_HEIGHT) / 2.7, 2)

        # 3. 2단 벽체 및 두께 마감 카드메이커 설정 (벽 결합 틈새 0% 완벽 밀폐 오버랩)
        # 1단 벽 (0 ~ 4.5m)
        cm_tier1 = CardMaker('tier1_face')
        cm_tier1.setFrame(-half_thick, CELL_SIZE + half_thick, 0, TIER_HEIGHT)

        # 2단 벽 (4.5m ~ 9.0m)
        cm_tier2 = CardMaker('tier2_face')
        cm_tier2.setFrame(-half_thick, CELL_SIZE + half_thick, TIER_HEIGHT, WALL_HEIGHT)

        # 출입문 1단 인방 (2.4m ~ 4.5m)
        cm_door_lintel = CardMaker('door_lintel')
        cm_door_lintel.setFrame(-half_thick, CELL_SIZE + half_thick, DOOR_HEIGHT, TIER_HEIGHT)

        # 출입문 하단 소핏 (문틀 윗면 천장 마감: 너비 WALL_THICKNESS, 길이 CELL_SIZE)
        cm_soffit = CardMaker('soffit')
        cm_soffit.setFrame(-half_thick, CELL_SIZE + half_thick, -half_thick, half_thick)

        # 문틀 기둥 옆면 마감 (너비: WALL_THICKNESS, 높이: DOOR_HEIGHT)
        cm_jamb = CardMaker('jamb')
        cm_jamb.setFrame(-half_thick, half_thick, 0, DOOR_HEIGHT)

        # 대형 백룸 홀 전용 건축 지지 기둥 카드 (1.2m x 1.2m x 13.0m 사각 기둥)
        cm_pillar_face = CardMaker('pillar_face')
        half_p = 0.6
        cm_pillar_face.setFrame(-half_p, half_p, 0, WALL_HEIGHT)

        start_gx = cx * CHUNK_CELLS
        start_gy = cy * CHUNK_CELLS

        for i in range(CHUNK_CELLS):
            gx = start_gx + i
            cell_x = gx * CELL_SIZE

            for j in range(CHUNK_CELLS):
                gy = start_gy + j
                cell_y = gy * CELL_SIZE
                ht, vt = get_edge_types(gx, gy)

                # 맵 외곽 경계: 최북단 및 최동단은 강제 솔리드 2단 벽체로 밀폐
                if gy == (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 1:
                    ht = 1
                if gx == (MAP_MAX_CHUNK + 1) * CHUNK_CELLS - 1:
                    vt = 1

                # --- (0-A) 최남단 외곽 경계벽 밀폐 (y = cell_y) ---
                if cy == MAP_MIN_CHUNK and j == 0:
                    b_south_1 = self.node.attachNewNode(cm_tier1.generate())
                    b_south_1.setH(180)
                    b_south_1.setPos(cell_x + CELL_SIZE, cell_y + half_thick, 0)
                    b_south_1.setTexture(wall_tex)
                    b_south_1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    b_south_1.setTwoSided(True)

                    b_south_2 = self.node.attachNewNode(cm_tier2.generate())
                    b_south_2.setH(180)
                    b_south_2.setPos(cell_x + CELL_SIZE, cell_y + half_thick, 0)
                    b_south_2.setTexture(wall_tex)
                    b_south_2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    b_south_2.setTwoSided(True)

                    cap_s = self.node.attachNewNode(cm_soffit.generate())
                    cap_s.setP(90)
                    cap_s.setPos(cell_x, cell_y, WALL_HEIGHT)
                    cap_s.setTexture(wall_tex)
                    cap_s.setTwoSided(True)

                    b_box_s = (cell_x - half_thick, cell_y - half_thick, cell_x + CELL_SIZE + half_thick, cell_y + half_thick)
                    self.colliders.append(b_box_s)
                    self.cell_colliders[(gx, gy)].append(b_box_s)

                # --- (0-B) 최서단 외곽 경계벽 밀폐 (x = cell_x, 내부 지향 H=90) ---
                if cx == MAP_MIN_CHUNK and i == 0:
                    b_west_1 = self.node.attachNewNode(cm_tier1.generate())
                    b_west_1.setH(90)
                    b_west_1.setPos(cell_x + half_thick, cell_y, 0)
                    b_west_1.setTexture(wall_tex)
                    b_west_1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    b_west_1.setTwoSided(True)

                    b_west_2 = self.node.attachNewNode(cm_tier2.generate())
                    b_west_2.setH(90)
                    b_west_2.setPos(cell_x + half_thick, cell_y, 0)
                    b_west_2.setTexture(wall_tex)
                    b_west_2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    b_west_2.setTwoSided(True)

                    cap_w = self.node.attachNewNode(cm_soffit.generate())
                    cap_w.setP(90)
                    cap_w.setH(90)
                    cap_w.setPos(cell_x, cell_y, WALL_HEIGHT)
                    cap_w.setTexture(wall_tex)
                    cap_w.setTwoSided(True)

                    b_box_w = (cell_x - half_thick, cell_y - half_thick, cell_x + half_thick, cell_y + CELL_SIZE + half_thick)
                    self.colliders.append(b_box_w)
                    self.cell_colliders[(gx, gy)].append(b_box_w)

                # --- (1) 수평 벽체 (Horizontal Wall - 북쪽 경계, y = wy) ---
                wy = cell_y + CELL_SIZE
                if ht == 1:
                    # [솔리드 2단 벽체: 남쪽면 + 북쪽면]
                    # 남쪽면 (Facing -Y)
                    s1 = self.node.attachNewNode(cm_tier1.generate())
                    s1.setPos(cell_x, wy - half_thick, 0)
                    s1.setTexture(wall_tex)
                    s1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    s1.setTwoSided(True)

                    s2 = self.node.attachNewNode(cm_tier2.generate())
                    s2.setPos(cell_x, wy - half_thick, 0)
                    s2.setTexture(wall_tex)
                    s2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    s2.setTwoSided(True)

                    # 북쪽면 (Facing +Y)
                    n1 = self.node.attachNewNode(cm_tier1.generate())
                    n1.setH(180)
                    n1.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    n1.setTexture(wall_tex)
                    n1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    n1.setTwoSided(True)

                    n2 = self.node.attachNewNode(cm_tier2.generate())
                    n2.setH(180)
                    n2.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    n2.setTexture(wall_tex)
                    n2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    n2.setTwoSided(True)

                    # 벽 상단 마감
                    cap_h = self.node.attachNewNode(cm_soffit.generate())
                    cap_h.setP(90)
                    cap_h.setPos(cell_x, wy, WALL_HEIGHT)
                    cap_h.setTexture(wall_tex)
                    cap_h.setTwoSided(True)

                    # 플레이어 충돌체 등록 (0.8m 두께 반영 및 셀 공간 인덱싱)
                    col_box = (
                        cell_x - half_thick,
                        wy - half_thick,
                        cell_x + CELL_SIZE + half_thick,
                        wy + half_thick
                    )
                    self.colliders.append(col_box)
                    self.cell_colliders[(gx, gy)].append(col_box)
                    self.cell_colliders[(gx, gy + 1)].append(col_box)

                elif ht == 2:
                    # [출입문 2단 벽체: 1단은 2.4m까지 개방 통로 + 인방벽, 2단은 꽉 찬 벽]
                    # 1단 출입문 인방 (2.4m ~ 4.5m)
                    dl_s = self.node.attachNewNode(cm_door_lintel.generate())
                    dl_s.setPos(cell_x, wy - half_thick, 0)
                    dl_s.setTexture(wall_tex)
                    dl_s.setTexScale(TextureStage.getDefault(), wall_u_scale, lintel_v_scale)
                    dl_s.setTwoSided(True)

                    dl_n = self.node.attachNewNode(cm_door_lintel.generate())
                    dl_n.setH(180)
                    dl_n.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    dl_n.setTexture(wall_tex)
                    dl_n.setTexScale(TextureStage.getDefault(), wall_u_scale, lintel_v_scale)
                    dl_n.setTwoSided(True)

                    # 2단 벽체 (4.5m ~ 9.0m)
                    u_s = self.node.attachNewNode(cm_tier2.generate())
                    u_s.setPos(cell_x, wy - half_thick, 0)
                    u_s.setTexture(wall_tex)
                    u_s.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    u_s.setTwoSided(True)

                    u_n = self.node.attachNewNode(cm_tier2.generate())
                    u_n.setH(180)
                    u_n.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    u_n.setTexture(wall_tex)
                    u_n.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    u_n.setTwoSided(True)

                    # 문틀 하부 소핏 (문틀 윗면 천장 마감)
                    soffit = self.node.attachNewNode(cm_soffit.generate())
                    soffit.setP(90)
                    soffit.setPos(cell_x, wy, DOOR_HEIGHT)
                    soffit.setTexture(wall_tex)
                    soffit.setTwoSided(True)

                    # 문틀 좌우 기둥 옆면 마감
                    j_left = self.node.attachNewNode(cm_jamb.generate())
                    j_left.setH(90)
                    j_left.setPos(cell_x, wy, 0)
                    j_left.setTexture(wall_tex)
                    j_left.setTwoSided(True)

                    j_right = self.node.attachNewNode(cm_jamb.generate())
                    j_right.setH(-90)
                    j_right.setPos(cell_x + CELL_SIZE, wy, 0)
                    j_right.setTexture(wall_tex)
                    j_right.setTwoSided(True)

                # --- (2) 수직 벽체 (Vertical Wall - 동쪽 경계, x = wx) ---
                wx = cell_x + CELL_SIZE
                if vt == 1:
                    # [솔리드 2단 벽체: 서쪽면 + 동쪽면]
                    # 서쪽면 (Facing -X)
                    w1 = self.node.attachNewNode(cm_tier1.generate())
                    w1.setH(-90)
                    w1.setPos(wx - half_thick, cell_y + CELL_SIZE, 0)
                    w1.setTexture(wall_tex)
                    w1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    w1.setTwoSided(True)

                    w2 = self.node.attachNewNode(cm_tier2.generate())
                    w2.setH(-90)
                    w2.setPos(wx - half_thick, cell_y + CELL_SIZE, 0)
                    w2.setTexture(wall_tex)
                    w2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    w2.setTwoSided(True)

                    # 동쪽면 (Facing +X)
                    e1 = self.node.attachNewNode(cm_tier1.generate())
                    e1.setH(90)
                    e1.setPos(wx + half_thick, cell_y, 0)
                    e1.setTexture(wall_tex)
                    e1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    e1.setTwoSided(True)

                    e2 = self.node.attachNewNode(cm_tier2.generate())
                    e2.setH(90)
                    e2.setPos(wx + half_thick, cell_y, 0)
                    e2.setTexture(wall_tex)
                    e2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    e2.setTwoSided(True)

                    # 벽 상단 마감
                    cap_v = self.node.attachNewNode(cm_soffit.generate())
                    cap_v.setP(90)
                    cap_v.setH(90)
                    cap_v.setPos(wx, cell_y, WALL_HEIGHT)
                    cap_v.setTexture(wall_tex)
                    cap_v.setTwoSided(True)

                    # 플레이어 충돌체 등록 (셀 공간 인덱싱)
                    col_box = (
                        wx - half_thick,
                        cell_y - half_thick,
                        wx + half_thick,
                        cell_y + CELL_SIZE + half_thick
                    )
                    self.colliders.append(col_box)
                    self.cell_colliders[(gx, gy)].append(col_box)
                    self.cell_colliders[(gx + 1, gy)].append(col_box)

                elif vt == 2:
                    # [출입문 2단 벽체]
                    # 1단 출입문 인방
                    dl_w = self.node.attachNewNode(cm_door_lintel.generate())
                    dl_w.setH(-90)
                    dl_w.setPos(wx - half_thick, cell_y + CELL_SIZE, 0)
                    dl_w.setTexture(wall_tex)
                    dl_w.setTexScale(TextureStage.getDefault(), wall_u_scale, lintel_v_scale)
                    dl_w.setTwoSided(True)

                    dl_e = self.node.attachNewNode(cm_door_lintel.generate())
                    dl_e.setH(90)
                    dl_e.setPos(wx + half_thick, cell_y, 0)
                    dl_e.setTexture(wall_tex)
                    dl_e.setTexScale(TextureStage.getDefault(), wall_u_scale, lintel_v_scale)
                    dl_e.setTwoSided(True)

                    # 2단 벽체
                    u_w = self.node.attachNewNode(cm_tier2.generate())
                    u_w.setH(-90)
                    u_w.setPos(wx - half_thick, cell_y + CELL_SIZE, 0)
                    u_w.setTexture(wall_tex)
                    u_w.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    u_w.setTwoSided(True)

                    u_e = self.node.attachNewNode(cm_tier2.generate())
                    u_e.setH(90)
                    u_e.setPos(wx + half_thick, cell_y, 0)
                    u_e.setTexture(wall_tex)
                    u_e.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    u_e.setTwoSided(True)

                    # 문틀 하부 소핏
                    soffit = self.node.attachNewNode(cm_soffit.generate())
                    soffit.setP(90)
                    soffit.setH(90)
                    soffit.setPos(wx, cell_y, DOOR_HEIGHT)
                    soffit.setTexture(wall_tex)
                    soffit.setTwoSided(True)

                    # 문틀 상하 기둥 옆면 마감
                    j_s = self.node.attachNewNode(cm_jamb.generate())
                    j_s.setH(0)
                    j_s.setPos(wx, cell_y, 0)
                    j_s.setTexture(wall_tex)
                    j_s.setTwoSided(True)

                    j_n = self.node.attachNewNode(cm_jamb.generate())
                    j_n.setH(180)
                    j_n.setPos(wx, cell_y + CELL_SIZE, 0)
                    j_n.setTexture(wall_tex)
                    j_n.setTwoSided(True)

                # --- (3) 대형 백룸 룸 지지 기둥 (Pillar Column) ---
                if cell_has_pillar(gx, gy):
                    px = cell_x + CELL_SIZE * 0.5
                    py = cell_y + CELL_SIZE * 0.5

                    p_s = self.node.attachNewNode(cm_pillar_face.generate())
                    p_s.setPos(px, py - half_p, 0)
                    p_s.setTexture(wall_tex)
                    p_s.setTexScale(TextureStage.getDefault(), 1.2 / 3.5, WALL_HEIGHT / 2.7)
                    p_s.setTwoSided(True)

                    p_n = self.node.attachNewNode(cm_pillar_face.generate())
                    p_n.setH(180)
                    p_n.setPos(px, py + half_p, 0)
                    p_n.setTexture(wall_tex)
                    p_n.setTexScale(TextureStage.getDefault(), 1.2 / 3.5, WALL_HEIGHT / 2.7)
                    p_n.setTwoSided(True)

                    p_w = self.node.attachNewNode(cm_pillar_face.generate())
                    p_w.setH(90)
                    p_w.setPos(px - half_p, py, 0)
                    p_w.setTexture(wall_tex)
                    p_w.setTexScale(TextureStage.getDefault(), 1.2 / 3.5, WALL_HEIGHT / 2.7)
                    p_w.setTwoSided(True)

                    p_e = self.node.attachNewNode(cm_pillar_face.generate())
                    p_e.setH(-90)
                    p_e.setPos(px + half_p, py, 0)
                    p_e.setTexture(wall_tex)
                    p_e.setTexScale(TextureStage.getDefault(), 1.2 / 3.5, WALL_HEIGHT / 2.7)
                    p_e.setTwoSided(True)

                    col_pillar = (px - half_p, py - half_p, px + half_p, py + half_p)
                    self.colliders.append(col_pillar)
                    self.cell_colliders[(gx, gy)].append(col_pillar)

        # 4. 드로우 콜 최적화 (청크 벽체 및 바닥/천장 지오메트리 병합)
        self.node.flattenStrong()
        self.candle_positions = []

    def set_visible(self, visible):
        """1인칭 시야 렌더링 온/오프 상태 전환 (Panda3D 렌더 패스 스킵)"""
        if visible:
            if self.is_hidden:
                self.node.show()
                self.is_hidden = False
        else:
            if not self.is_hidden:
                self.node.hide()
                self.is_hidden = True

    def attach_to(self, parent):
        """백그라운드 스레드에서 생성 및 사전 병합된 청크를 메인 씬 그래프에 즉각 마운트"""
        if self.node and parent and not self.node.hasParent():
            self.node.reparentTo(parent)

    def destroy(self):
        """청크 노드 제거 및 메모리 해제"""
        if self.node:
            self.node.removeNode()
            self.node = None
        self.colliders.clear()
        if hasattr(self, 'cell_colliders'):
            self.cell_colliders.clear()
        if hasattr(self, 'candle_positions'):
            self.candle_positions.clear()
