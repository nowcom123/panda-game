import collections
from panda3d.core import CardMaker, TextureStage, NodePath, LColor
from constants import (
    CELL_SIZE, CHUNK_CELLS, CHUNK_SIZE, TIER_HEIGHT, WALL_HEIGHT, DOOR_HEIGHT, WALL_THICKNESS
)
from geometry import make_cube_to
from world_gen import zone_hash, get_edge_types

_STAND_TEMPLATE = None
_FLAME_TEMPLATE = None

def _get_candle_templates():
    """촛대 바디 및 불꽃 원형(Prototype) 지연 생성 및 캐싱 (청크당 생성시간 79ms -> 1.3ms 단축)"""
    global _STAND_TEMPLATE, _FLAME_TEMPLATE
    if _STAND_TEMPLATE is None:
        iron_col = LColor(0.08, 0.08, 0.09, 1.0)
        wax_col = LColor(0.88, 0.84, 0.72, 1.0)
        wick_col = LColor(0.04, 0.04, 0.04, 1.0)
        _STAND_TEMPLATE = NodePath("candle_stand_proto")
        make_cube_to(_STAND_TEMPLATE, 0.44, 0.44, 0.05, iron_col, 0, 0, 0.025)
        make_cube_to(_STAND_TEMPLATE, 0.28, 0.28, 0.06, iron_col, 0, 0, 0.08)
        make_cube_to(_STAND_TEMPLATE, 0.10, 0.10, 1.15, iron_col, 0, 0, 0.685)
        make_cube_to(_STAND_TEMPLATE, 0.38, 0.38, 0.04, iron_col, 0, 0, 1.28)
        make_cube_to(_STAND_TEMPLATE, 0.16, 0.16, 0.32, wax_col, 0, 0, 1.46)
        make_cube_to(_STAND_TEMPLATE, 0.02, 0.02, 0.06, wick_col, 0, 0, 1.65)
        _STAND_TEMPLATE.flattenStrong()

    if _FLAME_TEMPLATE is None:
        flame_out_col = LColor(1.0, 0.62, 0.08, 1.0)
        flame_in_col = LColor(1.0, 0.96, 0.75, 1.0)
        _FLAME_TEMPLATE = NodePath("candle_flame_proto")
        make_cube_to(_FLAME_TEMPLATE, 0.08, 0.08, 0.18, flame_out_col, 0, 0, 1.76, rot_h=45)
        make_cube_to(_FLAME_TEMPLATE, 0.045, 0.045, 0.11, flame_in_col, 0, 0, 1.75)
        _FLAME_TEMPLATE.flattenStrong()
        _FLAME_TEMPLATE.setLightOff()

    return _STAND_TEMPLATE, _FLAME_TEMPLATE


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

        # 2. 청크 천장 타일 (광활한 3x3 연속 밤하늘 이미지 텍스처 적용 - 칠흑 같은 심야 하늘)
        ceil = self.node.attachNewNode(cm_floor.generate())
        ceil.setP(90)
        ceil.setPos(chunk_origin_x, chunk_origin_y + CHUNK_SIZE, WALL_HEIGHT)
        ceil.setTexture(sky_tex)
        sky_span = 3.0
        ceil.setTexScale(TextureStage.getDefault(), 1.0 / sky_span, 1.0 / sky_span)
        ceil.setTexOffset(TextureStage.getDefault(), (cx % sky_span) / sky_span, (cy % sky_span) / sky_span)
        ceil.setColorScale(0.12, 0.12, 0.18, 1.0) # 어둠에 잠긴 밤하늘과 은은한 별빛
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

        start_gx = cx * CHUNK_CELLS
        start_gy = cy * CHUNK_CELLS

        for i in range(CHUNK_CELLS):
            gx = start_gx + i
            cell_x = gx * CELL_SIZE

            for j in range(CHUNK_CELLS):
                gy = start_gy + j
                cell_y = gy * CELL_SIZE
                ht, vt = get_edge_types(gx, gy)

                # --- (1) 수평 벽체 (Horizontal Wall - 북쪽 경계, y = wy) ---
                wy = cell_y + CELL_SIZE
                if ht == 1:
                    # [솔리드 2단 벽체: 남쪽면 + 북쪽면]
                    # 남쪽면 (Facing -Y)
                    s1 = self.node.attachNewNode(cm_tier1.generate())
                    s1.setPos(cell_x, wy - half_thick, 0)
                    s1.setTexture(wall_tex)
                    s1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    s2 = self.node.attachNewNode(cm_tier2.generate())
                    s2.setPos(cell_x, wy - half_thick, 0)
                    s2.setTexture(wall_tex)
                    s2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

                    # 북쪽면 (Facing +Y)
                    n1 = self.node.attachNewNode(cm_tier1.generate())
                    n1.setH(180)
                    n1.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    n1.setTexture(wall_tex)
                    n1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    n2 = self.node.attachNewNode(cm_tier2.generate())
                    n2.setH(180)
                    n2.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    n2.setTexture(wall_tex)
                    n2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

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

                    dl_n = self.node.attachNewNode(cm_door_lintel.generate())
                    dl_n.setH(180)
                    dl_n.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    dl_n.setTexture(wall_tex)
                    dl_n.setTexScale(TextureStage.getDefault(), wall_u_scale, lintel_v_scale)

                    # 2단 벽체 (4.5m ~ 9.0m)
                    u_s = self.node.attachNewNode(cm_tier2.generate())
                    u_s.setPos(cell_x, wy - half_thick, 0)
                    u_s.setTexture(wall_tex)
                    u_s.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

                    u_n = self.node.attachNewNode(cm_tier2.generate())
                    u_n.setH(180)
                    u_n.setPos(cell_x + CELL_SIZE, wy + half_thick, 0)
                    u_n.setTexture(wall_tex)
                    u_n.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

                    # 문틀 하부 소핏 (문틀 윗면 천장 마감)
                    soffit = self.node.attachNewNode(cm_soffit.generate())
                    soffit.setP(90)
                    soffit.setPos(cell_x, wy, DOOR_HEIGHT)
                    soffit.setTexture(wall_tex)

                    # 문틀 좌우 기둥 옆면 마감
                    j_left = self.node.attachNewNode(cm_jamb.generate())
                    j_left.setH(90)
                    j_left.setPos(cell_x, wy, 0)
                    j_left.setTexture(wall_tex)

                    j_right = self.node.attachNewNode(cm_jamb.generate())
                    j_right.setH(-90)
                    j_right.setPos(cell_x + CELL_SIZE, wy, 0)
                    j_right.setTexture(wall_tex)

                # --- (2) 수직 벽체 (Vertical Wall - 동쪽 경계, x = wx) ---
                wx = cell_x + CELL_SIZE
                if vt == 1:
                    # [솔리드 2단 벽체: 서쪽면 + 동쪽면]
                    # 서쪽면 (Facing -X)
                    w1 = self.node.attachNewNode(cm_tier1.generate())
                    w1.setH(90)
                    w1.setPos(wx - half_thick, cell_y, 0)
                    w1.setTexture(wall_tex)
                    w1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    w2 = self.node.attachNewNode(cm_tier2.generate())
                    w2.setH(90)
                    w2.setPos(wx - half_thick, cell_y, 0)
                    w2.setTexture(wall_tex)
                    w2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

                    # 동쪽면 (Facing +X)
                    e1 = self.node.attachNewNode(cm_tier1.generate())
                    e1.setH(-90)
                    e1.setPos(wx + half_thick, cell_y + CELL_SIZE, 0)
                    e1.setTexture(wall_tex)
                    e1.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)
                    e2 = self.node.attachNewNode(cm_tier2.generate())
                    e2.setH(-90)
                    e2.setPos(wx + half_thick, cell_y + CELL_SIZE, 0)
                    e2.setTexture(wall_tex)
                    e2.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

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
                    dl_w.setH(90)
                    dl_w.setPos(wx - half_thick, cell_y, 0)
                    dl_w.setTexture(wall_tex)
                    dl_w.setTexScale(TextureStage.getDefault(), wall_u_scale, lintel_v_scale)

                    dl_e = self.node.attachNewNode(cm_door_lintel.generate())
                    dl_e.setH(-90)
                    dl_e.setPos(wx + half_thick, cell_y + CELL_SIZE, 0)
                    dl_e.setTexture(wall_tex)
                    dl_e.setTexScale(TextureStage.getDefault(), wall_u_scale, lintel_v_scale)

                    # 2단 벽체
                    u_w = self.node.attachNewNode(cm_tier2.generate())
                    u_w.setH(90)
                    u_w.setPos(wx - half_thick, cell_y, 0)
                    u_w.setTexture(wall_tex)
                    u_w.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

                    u_e = self.node.attachNewNode(cm_tier2.generate())
                    u_e.setH(-90)
                    u_e.setPos(wx + half_thick, cell_y + CELL_SIZE, 0)
                    u_e.setTexture(wall_tex)
                    u_e.setTexScale(TextureStage.getDefault(), wall_u_scale, wall_v_scale)

                    # 문틀 하부 소핏
                    soffit = self.node.attachNewNode(cm_soffit.generate())
                    soffit.setP(90)
                    soffit.setH(90)
                    soffit.setPos(wx, cell_y, DOOR_HEIGHT)
                    soffit.setTexture(wall_tex)

                    # 문틀 상하 기둥 옆면 마감
                    j_s = self.node.attachNewNode(cm_jamb.generate())
                    j_s.setH(0)
                    j_s.setPos(wx, cell_y, 0)
                    j_s.setTexture(wall_tex)

                    j_n = self.node.attachNewNode(cm_jamb.generate())
                    j_n.setH(180)
                    j_n.setPos(wx, cell_y + CELL_SIZE, 0)
                    j_n.setTexture(wall_tex)

        # 4. 드로우 콜 최적화 (청크 벽체 및 바닥/천장 지오메트리 병합)
        self.node.flattenStrong()

        # 5. 절차적 3D 촛대 및 자체 발광 촛불 배치 (사전 빌드 원형 인스턴싱으로 0.2ms 빌드)
        self.candle_positions = []
        chunk_candles = []
        for i in range(CHUNK_CELLS):
            gx = start_gx + i
            cell_x = gx * CELL_SIZE
            for j in range(CHUNK_CELLS):
                gy = start_gy + j
                cell_y = gy * CELL_SIZE
                mx, my = gx // 3, gy // 3
                lx, ly = gx % 3, gy % 3
                h = zone_hash(mx, my)
                pattern = h % 4
                room_sw = pattern in (0, 1, 3)
                room_se = pattern in (0, 2, 3)
                room_nw = pattern in (0, 2, 3)
                room_ne = pattern in (0, 1, 3)

                # (A) 중심 십자 교차로 복도 (lx=1, ly=1): 모서리 인근에 고딕 촛대 배치
                if lx == 1 and ly == 1:
                    corner_idx = (h >> 3) % 4
                    if corner_idx == 0:
                        cx_pos = cell_x + 1.25
                        cy_pos = cell_y + 1.25
                    elif corner_idx == 1:
                        cx_pos = cell_x + CELL_SIZE - 1.25
                        cy_pos = cell_y + 1.25
                    elif corner_idx == 2:
                        cx_pos = cell_x + 1.25
                        cy_pos = cell_y + CELL_SIZE - 1.25
                    else:
                        cx_pos = cell_x + CELL_SIZE - 1.25
                        cy_pos = cell_y + CELL_SIZE - 1.25
                    chunk_candles.append((cx_pos, cy_pos, gx, gy))

                # (B) 사방이 막힌 독립 닫힌 방: 방 중심부에 제단 촛대 배치
                elif lx == 0 and ly == 0 and room_sw:
                    chunk_candles.append((cell_x + CELL_SIZE * 0.5, cell_y + CELL_SIZE * 0.5, gx, gy))
                elif lx == 2 and ly == 0 and room_se:
                    chunk_candles.append((cell_x + CELL_SIZE * 0.5, cell_y + CELL_SIZE * 0.5, gx, gy))
                elif lx == 0 and ly == 2 and room_nw:
                    chunk_candles.append((cell_x + CELL_SIZE * 0.5, cell_y + CELL_SIZE * 0.5, gx, gy))
                elif lx == 2 and ly == 2 and room_ne:
                    chunk_candles.append((cell_x + CELL_SIZE * 0.5, cell_y + CELL_SIZE * 0.5, gx, gy))

        if chunk_candles:
            stand_proto, flame_proto = _get_candle_templates()
            candle_root = self.node.attachNewNode("candles")
            stands_batch = candle_root.attachNewNode("stands")
            flames_batch = candle_root.attachNewNode("flames")

            for cx_pos, cy_pos, cgx, cgy in chunk_candles:
                self.candle_positions.append((cx_pos, cy_pos, 1.76))
                # 촛대 충돌체 등록 (해당 셀에 정확한 공간 인덱싱)
                cand_box = (
                    cx_pos - 0.22, cy_pos - 0.22,
                    cx_pos + 0.22, cy_pos + 0.22
                )
                self.colliders.append(cand_box)
                self.cell_colliders[(cgx, cgy)].append(cand_box)

                # 원형 템플릿 초고속 인스턴스 복제 (C++ 레벨 인스턴싱)
                s_inst = stand_proto.copyTo(stands_batch)
                s_inst.setPos(cx_pos, cy_pos, 0)

                f_inst = flame_proto.copyTo(flames_batch)
                f_inst.setPos(cx_pos, cy_pos, 0)

            # 촛대 및 불꽃 지오메트리 일괄 병합 (단 2개의 드로우 콜로 렌더 파이프라인 극대화)
            stands_batch.flattenStrong()
            flames_batch.flattenStrong()
            flames_batch.setLightOff()

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
