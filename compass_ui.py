"""360도 순환 나침반. +Y는 북쪽, +X는 동쪽입니다."""

import math

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import LineSegs, TextNode


def relative_bearing(bearing, heading):
    """시선 기준 최단 회전각: 왼쪽 음수, 오른쪽 양수."""
    return (bearing - heading + 180.0) % 360.0 - 180.0


def select_objective(px, py, altars, gate):
    if gate and gate.get('opened', False):
        target = dict(gate, name='심층 탈출 관문', kind='gate')
    else:
        remaining = [a for a in altars if not a['activated']]
        if not remaining:
            return None
        target = dict(min(remaining, key=lambda a: math.hypot(
            a['pos'][0] - px, a['pos'][1] - py)), kind='altar')
    dx, dy = target['pos'][0] - px, target['pos'][1] - py
    target['distance'] = math.hypot(dx, dy)
    target['bearing'] = math.degrees(math.atan2(dx, dy)) % 360.0
    return target


class CompassHUD:
    """중앙은 시선, 좌우 끝은 ±90°. 후방 목표는 끝 화살표로 안내합니다."""

    HALF_WIDTH = 0.72
    HALF_VIEW = 90.0
    GOLD = (0.82, 0.73, 0.53, 1.0)

    def __init__(self, parent, font_kw):
        self.root = parent.attachNewNode('compass_hud')
        self.root.setZ(0.84)
        self.root.setDepthTest(False)
        self.root.setDepthWrite(False)
        self.root.setLightOff()
        self.root.setBin('fixed', 10)
        self.heading = 0.0
        self.target = None
        self.target_delta = 0.0
        for i in range(16):
            strength = 1.0 - abs((i + 0.5) / 8.0 - 1.0) * 0.65
            x0 = -self.HALF_WIDTH + 2 * self.HALF_WIDTH * i / 16
            x1 = -self.HALF_WIDTH + 2 * self.HALF_WIDTH * (i + 1) / 16
            self._line(self.root, [(x0, 0), (x1, 0)],
                       tuple(c * strength for c in self.GOLD[:3]) + (1.0,))
        for sign in (-1, 1):
            x = sign * (self.HALF_WIDTH + 0.028)
            self._line(self.root, [(x - 0.018, 0), (x, 0.008),
                                  (x + 0.018, 0), (x, -0.008), (x - 0.018, 0)])
        self._line(self.root, [(-0.010, -0.029), (0, -0.012), (0.010, -0.029)])
        self.degree_text = OnscreenText(
            parent=self.root, text='000°', pos=(0, -0.067), scale=0.028,
            fg=self.GOLD, shadow=(0, 0, 0, 0.9), align=TextNode.ACenter,
            mayChange=True, **font_kw)
        self._degree_label = '000°'
        self.ticks = []
        for bearing in range(0, 360, 15):
            node = self.root.attachNewNode(f'compass_tick_{bearing}')
            self._line(node, [(0, 0), (0, -0.015 if bearing % 45 == 0 else -0.007)])
            self.ticks.append((bearing, node))
        self.cardinals = {}
        for bearing, label in ((0, '북 N'), (90, '동 E'), (180, '남 S'), (270, '서 W')):
            self.cardinals[bearing] = OnscreenText(
                parent=self.root, text=label, pos=(0, 0.022), scale=0.038,
                fg=(0.92, 0.86, 0.70, 1), shadow=(0, 0, 0, 0.95),
                align=TextNode.ACenter, **font_kw)
        self.marker = self.root.attachNewNode('compass_objective')
        self.marker.setZ(0.068)
        self.altar_icon = self._line(self.marker, [
            (0, 0.018), (0.014, 0), (0, -0.018), (-0.014, 0), (0, 0.018)])
        self.gate_icon = self._line(self.marker, [
            (-0.016, -0.018), (-0.016, 0.008), (0, 0.022),
            (0.016, 0.008), (0.016, -0.018), (-0.016, -0.018)])
        self.left_arrow = self._line(self.marker, [(-0.025, 0.009), (-0.035, 0), (-0.025, -0.009)])
        self.right_arrow = self._line(self.marker, [(0.025, 0.009), (0.035, 0), (0.025, -0.009)])
        self.clear()
        self.root.hide()

    def _line(self, parent, points, color=None):
        lines = LineSegs()
        lines.setThickness(1.5)
        lines.setColor(*(color or self.GOLD))
        for i, (x, z) in enumerate(points):
            if i == 0:
                lines.moveTo(x, 0, z)
            else:
                lines.drawTo(x, 0, z)
        return parent.attachNewNode(lines.create())

    def clear(self):
        self.target = None
        self.target_delta = 0.0
        self.marker.hide()
        self.left_arrow.hide()
        self.right_arrow.hide()

    def update(self, camera_heading, px, py, altars, gate):
        # Panda3D의 양의 heading은 왼쪽 회전입니다.
        self.heading = (-camera_heading) % 360.0
        label = f'{int(self.heading + 0.5) % 360:03d}°'
        if label != self._degree_label:
            self.degree_text.setText(label)
            self._degree_label = label
        for bearing, node in (*self.ticks, *self.cardinals.items()):
            delta = relative_bearing(bearing, self.heading)
            if abs(delta) <= self.HALF_VIEW:
                node.setX(delta / self.HALF_VIEW * self.HALF_WIDTH)
                node.show()
            else:
                node.hide()
        self.target = select_objective(px, py, altars, gate)
        if self.target is None:
            self.clear()
            return None
        self.target_delta = relative_bearing(self.target['bearing'], self.heading)
        if self.target['distance'] < 0.5:
            self.target_delta = 0.0
        x = max(-1.0, min(1.0, self.target_delta / self.HALF_VIEW)) * self.HALF_WIDTH
        self.marker.setX(x)
        self.marker.setColorScale(*(self.target.get('color') or (0.95, 0.83, 0.49, 1)))
        self.marker.show()
        self.altar_icon.hide()
        self.gate_icon.hide()
        (self.gate_icon if self.target['kind'] == 'gate' else self.altar_icon).show()
        self.left_arrow.hide()
        self.right_arrow.hide()
        if self.target_delta < -self.HALF_VIEW:
            self.left_arrow.show()
        elif self.target_delta > self.HALF_VIEW:
            self.right_arrow.show()
        return self.target
