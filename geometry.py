from panda3d.core import NodePath, CardMaker

_UNIT_CUBE = None

def _get_unit_cube():
    """모듈 단위 1x1x1 단위 큐브 원형(Prototype) 지연 생성 및 캐싱"""
    global _UNIT_CUBE
    if _UNIT_CUBE is None:
        _UNIT_CUBE = NodePath('unit_cube')
        cm = CardMaker('face')
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)

        # 앞 (+Y) & 뒤 (-Y)
        f1 = _UNIT_CUBE.attachNewNode(cm.generate())
        f1.setPos(0, 0.5, 0)
        f2 = _UNIT_CUBE.attachNewNode(cm.generate())
        f2.setH(180)
        f2.setPos(0, -0.5, 0)

        # 좌 (-X) & 우 (+X)
        f3 = _UNIT_CUBE.attachNewNode(cm.generate())
        f3.setH(90)
        f3.setPos(-0.5, 0, 0)
        f4 = _UNIT_CUBE.attachNewNode(cm.generate())
        f4.setH(-90)
        f4.setPos(0.5, 0, 0)

        # 상 (+Z) & 하 (-Z)
        f5 = _UNIT_CUBE.attachNewNode(cm.generate())
        f5.setP(90)
        f5.setPos(0, 0, 0.5)
        f6 = _UNIT_CUBE.attachNewNode(cm.generate())
        f6.setP(-90)
        f6.setPos(0, 0, -0.5)

        _UNIT_CUBE.flattenStrong()
    return _UNIT_CUBE


def make_cube_to(parent, sx, sy, sz, color, px, py, pz, rot_h=0):
    """지정된 위치와 각도로 부모 노드에 3D 직육면체 복제 (원형 템플릿 기반 초고속 지오메트리 인스턴싱)"""
    sub = _get_unit_cube().copyTo(parent)
    sub.setPos(px, py, pz)
    if rot_h:
        sub.setH(rot_h)
    sub.setScale(sx, sy, sz)
    sub.setColor(color)
    return sub


def make_cube(name, sx, sy, sz, color):
    """독립 3D 직육면체 노드 생성 (원형 템플릿 복제 및 단일 지오메트리 병합)"""
    root = NodePath(name)
    cube = _get_unit_cube().copyTo(root)
    cube.setScale(sx, sy, sz)
    cube.setColor(color)
    root.flattenStrong()
    return root

