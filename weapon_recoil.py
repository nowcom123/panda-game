"""Bounded, frame-rate independent recoil; mouse aim is never overwritten."""
import math


class RecoilSpring:
    def __init__(self, frequency=28.0, limit=1.8):
        self.frequency = frequency
        self.limit = limit
        self.reset()

    def reset(self):
        self.position = 0.0
        self.velocity = 0.0

    def kick(self, strength=1.0):
        # A single impulse peaks at strength after 1/frequency seconds.
        cap = self.limit * self.frequency * 2
        self.velocity = max(-cap, min(cap, self.velocity + strength * math.e * self.frequency))

    def update(self, dt):
        if dt <= 0:
            return self.position
        w = self.frequency
        decay = math.exp(-w * dt)
        c = self.velocity + w * self.position
        position = (self.position + c * dt) * decay
        self.velocity = (self.velocity - w * c * dt) * decay
        self.position = max(-self.limit, min(self.limit, position))
        if abs(position) > self.limit:
            self.velocity = 0.0
        if abs(self.position) < 1e-5 and abs(self.velocity) < 1e-4:
            self.reset()
        return self.position


# Pitch degrees, rearward travel, roll degrees, spring frequency, camera kick.
RECOIL_PROFILES = {
    'PISTOL': (9.0, .048, .6, 26.0, .80),
    'DUAL_PISTOL': (5.0, .026, 1.2, 38.0, .22),
    'AR': (4.5, .030, .45, 32.0, .45),
    'SHOTGUN': (10.0, .062, 1.0, 24.0, 1.0),
}


class WeaponRecoil:
    def __init__(self):
        self.channels = {}

    def kick(self, weapon, left=False):
        node = {'PISTOL': 'recoil_node', 'AR': 'ar_recoil_node',
                'SHOTGUN': 'sg_recoil_node',
                'DUAL_PISTOL': 'dual_left_recoil' if left else 'dual_right_recoil'}[weapon]
        if node not in self.channels:
            self.channels[node] = (RecoilSpring(RECOIL_PROFILES[weapon][3]), weapon, left)
        self.channels[node][0].kick()

    def update(self, dt, ads_alpha):
        poses = {}
        for node, (spring, weapon, left) in self.channels.items():
            amount = spring.update(dt) * (1.0 - .55 * max(0, min(1, ads_alpha)))
            pitch, travel, roll, _, _ = RECOIL_PROFILES[weapon]
            poses[node] = (-travel * amount, travel * .25 * amount,
                           pitch * amount, roll * amount * (1 if left else -1))
        return poses

    def reset(self):
        for spring, _, _ in self.channels.values():
            spring.reset()
