"""Tracer geometry, flight and fade lifecycle."""
from panda3d.core import LineSegs, LColor, TransparencyAttrib
from geometry import make_cube_to

def update_tracer_lines(world_root, tr, tail, head):
    # Allocate dynamic geometry once; subsequent frames only update vertices.
    styles = (
        ('core', 0.0, 4.5, (1.0, 1.0, .90, .98), 102),
        ('glow', .15, 9.5, (1.0, .75, .15, .75), 101),
        ('halo', .35, 18.0, (1.0, .35, .05, .35), 100),
    )
    for key, inset, thickness, color, sort in styles:
        start = tail + (head-tail)*inset
        lines = tr.get(key + '_lines')
        if lines is None:
            old = tr.get(key)
            if old is not None and not old.isEmpty():
                old.removeNode()
            lines = LineSegs('tracer_' + key)
            lines.setThickness(tr.get('th_' + key, thickness))
            lines.setColor(*tr.get('c_' + key, color))
            lines.moveTo(start)
            lines.drawTo(head)
            node = world_root.attachNewNode(lines.create(True))
            node.setLightOff()
            node.setTransparency(TransparencyAttrib.MAlpha)
            node.setDepthWrite(False)
            node.setBin('transparent', sort)
            tr[key] = node
            tr[key + '_lines'] = lines
        else:
            lines.setVertex(0, start)
            lines.setVertex(1, head)
    tr['np'] = tr['core']


def update_tracers(active_tracers, world_root, fx_dt):
    kept = 0
    for tr in active_tracers:
        tr["life"] -= fx_dt

        # 착탄 섬광 타이머 처리
        if tr.get("flash") and not tr["flash"].isEmpty():
            tr["flash_timer"] = max(0.0, tr.get("flash_timer", 0.0) - fx_dt)
            if tr["flash_timer"] <= 0.0:
                tr["flash"].removeNode()
                tr["flash"] = None
            else:
                scale = max(0.1, tr["flash_timer"] / 0.09)
                tr["flash"].setScale(scale)

        if tr.get("phase") == "fly":
            move = tr["speed"] * fx_dt
            tr["traveled"] += move
            head_pos = tr["traveled"]
            total_d = tr["total_dist"]

            if head_pos >= total_d:
                # 착탄 도달 -> 착탄 섬광 및 빠른 페이드 아웃(Dissolve, 0.08s) 전환
                tr["phase"] = "fade"
                tr["fade_timer"] = 0.08
                tr["fade_duration"] = 0.08
                tr["life"] = max(tr["life"], 0.09)

                # 탄두 제거
                if tr.get("head_node") and not tr["head_node"].isEmpty():
                    tr["head_node"].removeNode()
                    tr["head_node"] = None

                # 착탄점 발광 섬광 생성
                flash_np = world_root.attachNewNode("impact_flash")
                flash_np.setPos(tr["end"])
                f_geom = make_cube_to(flash_np, 0.28, 0.28, 0.28, LColor(1.0, 0.95, 0.40, 0.95), 0, 0, 0, rot_h=45)
                f_geom.setLightOff()
                f_geom.setTransparency(TransparencyAttrib.MAlpha)
                f_geom.setDepthWrite(False)
                f_geom.setBin("transparent", 110)
                tr["flash"] = flash_np
                tr["flash_timer"] = 0.09

                trail_head = tr["end"]
                t_len = min(14.0, max(4.0, total_d * 0.85))
                trail_tail = tr["start"] + tr["dir"] * max(0.0, total_d - t_len)
            else:
                trail_head = tr["start"] + tr["dir"] * head_pos
                t_len = min(14.0, max(3.5, head_pos * 0.85))
                tr["tracer_len"] = t_len
                trail_tail = tr["start"] + tr["dir"] * max(0.0, head_pos - t_len)

                # 3D 탄두 위치 및 방향 갱신
                if tr.get("head_node") and not tr["head_node"].isEmpty():
                    tr["head_node"].setPos(trail_head)
                    tr["head_node"].lookAt(trail_head + tr["dir"])

            # 라인 갱신 (Core, Glow, Halo)
            update_tracer_lines(world_root, tr, trail_tail, trail_head)

        elif tr.get("phase") == "fade":
            tr["fade_timer"] = max(0.0, tr.get("fade_timer", 0.0) - fx_dt)
            if tr["fade_timer"] <= 0.0:
                tr["life"] = 0.0
            else:
                fade_alpha = max(0.0, min(1.0, tr["fade_timer"] / tr["fade_duration"]))
                # 지오메트리 파괴 및 재생성 없이 노드 컬러 스케일만 즉시 감쇠 (드로우콜 및 메모리 스파이크 방지)
                for key in ("core", "glow", "halo"):
                    node = tr.get(key)
                    if node and not node.isEmpty():
                        node.setColorScale(1.0, 1.0, 1.0, fade_alpha)

        if tr["life"] <= 0.0:
            for key in ("core", "glow", "halo", "head_node", "flash", "np"):
                node = tr.get(key)
                if node and not node.isEmpty():
                    node.removeNode()
        else:
            active_tracers[kept] = tr
            kept += 1
    del active_tracers[kept:]
