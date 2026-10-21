import math
import random
from panda3d.core import (NodePath, CardMaker, Geom, GeomNode, GeomTriangles,
                         GeomVertexData, GeomVertexFormat, GeomVertexWriter,
                         TransparencyAttrib)

_UNIT_CUBE = None
_ROUND_MESHES = {}


def make_muzzle_flash_to(parent, width, length, px, py, pz):
    """Prebuild four sparse, tapered flame variants along the barrel's +Y axis.

    Dimensions live in vertices, so per-shot root scaling cannot replace them
    with a metre-sized primitive. Transparent edges leave gaps between jets.
    """
    root = parent.attachNewNode('muzzle_flame')
    root.setPos(px, py, pz)
    root.setLightOff()
    root.setTwoSided(True)
    root.setTransparency(TransparencyAttrib.MAlpha)
    root.setDepthWrite(False)
    for variant in range(4):
        rng = random.Random(491 + variant)
        data = GeomVertexData('flame', GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertices = GeomVertexWriter(data, 'vertex')
        colors = GeomVertexWriter(data, 'color')
        triangles = GeomTriangles(Geom.UHStatic)
        for jet in range(5):
            angle = jet * math.tau / 5 + rng.uniform(-.4, .4)
            radius = width * rng.uniform(.27, .50)
            reach = length * rng.uniform(.55, 1.0)
            # Each flame is a narrow, asymmetric ribbon with a warm core.
            points = [(radius * .32, reach * .30), (0, 0),
                      (radius * .55, reach * .12), (radius, reach * .48),
                      (radius * .60, reach), (radius * .12, reach * .58),
                      (-radius * .12, reach * .15)]
            first = vertices.getWriteRow()
            for index, (radial, forward) in enumerate(points):
                vertices.addData3(math.cos(angle) * radial, forward,
                                  math.sin(angle) * radial)
                colors.addData4(*((1.0, .87, .44, .82) if index == 0
                                  else (1.0, .29, .035, 0.0)))
            for edge in range(1, len(points)):
                triangles.addVertices(first, first + edge,
                                      first + (edge + 1 if edge < len(points)-1 else 1))
        geom = Geom(data)
        geom.addPrimitive(triangles)
        node = GeomNode(f'flame_variant_{variant}')
        node.addGeom(geom)
        root.attachNewNode(node).hide()
    root.hide()
    return root


def _get_round_mesh(shape, axis='z'):
    """Cached, outward-facing unit meshes; dimensions match the cube helpers."""
    key = (shape, axis)
    if key in _ROUND_MESHES:
        return _ROUND_MESHES[key]
    if axis not in ('x', 'y', 'z'):
        raise ValueError('axis must be x, y or z')
    data = GeomVertexData(shape, GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
    vertices = GeomVertexWriter(data, 'vertex')
    normals = GeomVertexWriter(data, 'normal')
    uv = GeomVertexWriter(data, 'texcoord')
    triangles = GeomTriangles(Geom.UHStatic)

    def orient(x, y, z):
        return (x, z, -y) if axis == 'y' else ((z, y, -x) if axis == 'x' else (x, y, z))

    def vertex(pos, normal, tex):
        index = vertices.getWriteRow()
        vertices.addData3(*orient(*pos))
        normals.addData3(*orient(*normal))
        uv.addData2(*tex)
        return index

    sides = 16
    if shape == 'sphere':
        rings = 8
        for j in range(rings + 1):
            latitude = -math.pi / 2 + math.pi * j / rings
            for i in range(sides + 1):
                theta = 2 * math.pi * i / sides
                normal = (math.cos(latitude) * math.cos(theta),
                          math.cos(latitude) * math.sin(theta), math.sin(latitude))
                vertex(tuple(v * .5 for v in normal), normal, (i / sides, j / rings))
        for j in range(rings):
            for i in range(sides):
                a = j * (sides + 1) + i
                b = a + sides + 1
                if j > 0:
                    triangles.addVertices(a, a + 1, b)
                if j < rings - 1:
                    triangles.addVertices(a + 1, b + 1, b)
    elif shape == 'cylinder':
        for i in range(sides + 1):
            theta = 2 * math.pi * i / sides
            x, y = math.cos(theta), math.sin(theta)
            vertex((x * .5, y * .5, -.5), (x, y, 0), (i / sides, 0))
            vertex((x * .5, y * .5, .5), (x, y, 0), (i / sides, 1))
        for i in range(sides):
            a = i * 2
            triangles.addVertices(a, a + 2, a + 3)
            triangles.addVertices(a, a + 3, a + 1)
        for sign in (-1, 1):
            center = vertex((0, 0, .5 * sign), (0, 0, sign), (.5, .5))
            for i in range(sides + 1):
                theta = 2 * math.pi * i / sides
                x, y = .5 * math.cos(theta), .5 * math.sin(theta)
                vertex((x, y, .5 * sign), (0, 0, sign), (x + .5, y + .5))
            for i in range(sides):
                a, b = center + i + 1, center + i + 2
                triangles.addVertices(center, a, b) if sign > 0 else triangles.addVertices(center, b, a)
    else:
        raise ValueError('unknown round mesh')
    geom = Geom(data)
    geom.addPrimitive(triangles)
    node = GeomNode('unit_' + shape + '_' + axis)
    node.addGeom(geom)
    _ROUND_MESHES[key] = NodePath(node)
    return _ROUND_MESHES[key]


def _round_to(shape, parent, sx, sy, sz, color, px, py, pz, rot_h, rot_p, rot_r, axis='z'):
    node = _get_round_mesh(shape, axis).copyTo(parent)
    node.setScale(sx, sy, sz)
    node.setPos(px, py, pz)
    node.setHpr(rot_h, rot_p, rot_r)
    node.setColor(color)
    return node


def make_sphere_to(parent, sx, sy, sz, color, px, py, pz, rot_h=0, rot_p=0, rot_r=0):
    return _round_to('sphere', parent, sx, sy, sz, color, px, py, pz, rot_h, rot_p, rot_r)


def make_cylinder_to(parent, sx, sy, sz, color, px, py, pz, rot_h=0, rot_p=0, rot_r=0, axis='z'):
    return _round_to('cylinder', parent, sx, sy, sz, color, px, py, pz, rot_h, rot_p, rot_r, axis)


def make_sphere(name, sx, sy, sz, color):
    root = NodePath(name)
    make_sphere_to(root, sx, sy, sz, color, 0, 0, 0)
    root.flattenStrong()
    return root


def make_cylinder(name, sx, sy, sz, color, axis='z'):
    root = NodePath(name)
    make_cylinder_to(root, sx, sy, sz, color, 0, 0, 0, axis=axis)
    root.flattenStrong()
    return root

def _get_unit_cube():
    """모듈 단위 1x1x1 단위 큐브 원형(Prototype) 지연 생성 및 캐싱"""
    global _UNIT_CUBE
    if _UNIT_CUBE is None:
        _UNIT_CUBE = NodePath('unit_cube')
        cm = CardMaker('face')
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)

        # 앞 (+Y) & 뒤 (-Y)
        f1 = _UNIT_CUBE.attachNewNode(cm.generate())
        f1.setH(180)
        f1.setPos(0, 0.5, 0)
        f2 = _UNIT_CUBE.attachNewNode(cm.generate())
        f2.setPos(0, -0.5, 0)

        # 좌 (-X) & 우 (+X)
        f3 = _UNIT_CUBE.attachNewNode(cm.generate())
        f3.setH(-90)
        f3.setPos(-0.5, 0, 0)
        f4 = _UNIT_CUBE.attachNewNode(cm.generate())
        f4.setH(90)
        f4.setPos(0.5, 0, 0)

        # 상 (+Z) & 하 (-Z)
        f5 = _UNIT_CUBE.attachNewNode(cm.generate())
        f5.setP(-90)
        f5.setPos(0, 0, 0.5)
        f6 = _UNIT_CUBE.attachNewNode(cm.generate())
        f6.setP(90)
        f6.setPos(0, 0, -0.5)

        _UNIT_CUBE.flattenStrong()
    return _UNIT_CUBE


def make_cube_to(parent, sx, sy, sz, color, px, py, pz, rot_h=0, rot_p=0, rot_r=0):
    """지정된 위치와 각도(H, P, R)로 부모 노드에 3D 직육면체 복제 (원형 템플릿 기반 초고속 지오메트리 인스턴싱)"""
    sub = _get_unit_cube().copyTo(parent)
    sub.setPos(px, py, pz)
    if rot_h or rot_p or rot_r:
        sub.setHpr(rot_h, rot_p, rot_r)
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

