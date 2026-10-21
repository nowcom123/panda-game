import unittest
from panda3d.core import NodePath, Vec3
from casing_effects import CasingEffects, CASING_FLOOR_Z


class TestCasingEffects(unittest.TestCase):
    def setUp(self):
        self.root = NodePath("test_root")
        self.effects = CasingEffects(self.root, capacity=24)

    def tearDown(self):
        self.effects.destroy()
        if not self.root.isEmpty():
            self.root.removeNode()

    def test_initialization(self):
        """풀 초기화 상태 검증 (24개 고정 크기, 모두 비활성화 및 숨김)"""
        self.assertEqual(self.effects.capacity, 24)
        self.assertEqual(len(self.effects.pool), 24)
        self.assertEqual(self.effects.cursor, 0)
        self.assertEqual(self.effects.active_count, 0)

        for c in self.effects.pool:
            self.assertFalse(c["active"])
            self.assertTrue(c["node"].isHidden())
            self.assertIn("PISTOL", c["meshes"])
            self.assertIn("DUAL_PISTOL", c["meshes"])
            self.assertIn("AR", c["meshes"])
            self.assertIn("SHOTGUN", c["meshes"])

    def test_emit_weapon_submeshes(self):
        """무기별 전용 서브메시 활성화 및 상호 배타적 표시 검증"""
        weapons = ["PISTOL", "DUAL_PISTOL", "AR", "SHOTGUN"]
        for idx, w in enumerate(weapons):
            self.effects.emit(w, Vec3(0, 0, 1.0), Vec3(1, 0, 0))
            slot = self.effects.pool[idx]
            self.assertTrue(slot["active"])
            self.assertFalse(slot["node"].isHidden())
            self.assertEqual(slot["current_weapon"], w)

            # 대상 무기 메시는 표시되고, 다른 무기 메시는 숨겨져야 함
            for m_name, m_node in slot["meshes"].items():
                if m_name == w:
                    self.assertFalse(m_node.isHidden(), f"{w} mesh should be visible")
                else:
                    self.assertTrue(m_node.isHidden(), f"{m_name} mesh should be hidden when weapon is {w}")

    def test_pool_capacity_and_rollover(self):
        """풀 상한(24개) 도달 시 새 노드 생성 없이 링 버퍼 순환 재사용 검증"""
        for i in range(24):
            self.effects.emit("AR", Vec3(0, i, 1.0), Vec3(1, 0, 0))

        self.assertEqual(len(self.effects.pool), 24)
        self.assertEqual(self.effects.active_count, 24)
        self.assertEqual(self.effects.cursor, 0)

        # 25번째 배출 시 슬롯 0이 덮어써지고 커서는 1로 전진
        self.effects.emit("SHOTGUN", Vec3(99, 99, 1.0), Vec3(2, 0, 0))
        self.assertEqual(len(self.effects.pool), 24)
        self.assertEqual(self.effects.cursor, 1)
        self.assertEqual(self.effects.pool[0]["current_weapon"], "SHOTGUN")
        self.assertEqual(self.effects.pool[0]["pos"], Vec3(99, 99, 1.0))

    def test_reuse_shotgun_to_pistol_clean_reset(self):
        """샷건 셸 사용 후 권총 탄피로 재사용될 때 크기/색상/투명도 원상 복구 검증"""
        # 1) 슬롯 0에 샷건 셸 배출
        self.effects.cursor = 0
        self.effects.emit("SHOTGUN", Vec3(0, 0, 1.5), Vec3(1, 0, 0))
        slot = self.effects.pool[0]
        self.assertEqual(slot["current_weapon"], "SHOTGUN")
        self.assertFalse(slot["meshes"]["SHOTGUN"].isHidden())

        # 임의로 스케일 또는 알파 변경
        slot["node"].setScale(1.8, 1.8, 1.8)
        slot["node"].setColorScale(1.0, 0.5, 0.5, 0.3)

        # 2) 슬롯 0을 PISTOL로 재사용 배출
        self.effects.cursor = 0
        self.effects.emit("PISTOL", Vec3(1, 2, 3), Vec3(0, 1, 0))

        self.assertEqual(slot["current_weapon"], "PISTOL")
        self.assertFalse(slot["meshes"]["PISTOL"].isHidden())
        self.assertTrue(slot["meshes"]["SHOTGUN"].isHidden())
        # 스케일과 컬러 스케일이 1.0으로 리셋되었는지 확인
        self.assertEqual(slot["node"].getScale(), Vec3(1.0, 1.0, 1.0))
        self.assertEqual(slot["node"].getColorScale(), (1.0, 1.0, 1.0, 1.0))

    def test_update_gravity_and_motion(self):
        """탄피 중력 및 궤적 이동 물리 검증"""
        self.effects.emit("PISTOL", Vec3(0, 0, 2.0), Vec3(2.0, 0.0, 1.0))
        slot = self.effects.pool[0]

        initial_z_vel = slot["vel"].z
        initial_x = slot["pos"].x

        self.effects.update(0.05)

        self.assertGreater(slot["pos"].x, initial_x)
        self.assertLess(slot["vel"].z, initial_z_vel, "Gravity should decrease z velocity")
        self.assertEqual(slot["node"].getPos(), slot["pos"])

    def test_floor_bounce_and_settle(self):
        """바닥 충돌 반동 및 저속 시 떨림 없는 완전 안착(Settle) 검증"""
        # 바닥 바로 위에서 하향 낙하 배출
        self.effects.emit("AR", Vec3(0, 0, 0.05), Vec3(0.2, 0.0, -1.5))
        slot = self.effects.pool[0]

        # 물리 업데이트 진행
        for _ in range(30):
            self.effects.update(0.05)

        # 바닥 이하로 침투하지 않고 바닥 높이에 안착
        self.assertAlmostEqual(slot["pos"].z, CASING_FLOOR_Z, places=4)
        # 에너지가 소진되어 안착 상태가 됨
        self.assertTrue(slot["is_settled"])
        self.assertEqual(slot["vel"], Vec3(0, 0, 0))
        self.assertEqual(slot["spin"], Vec3(0, 0, 0))

    def test_lifetime_expiration_and_fade(self):
        """수명 만료 시 자동 비활성화 및 만료 직전 알파 페이드아웃 검증"""
        self.effects.emit("PISTOL", Vec3(0, 0, 1.0), Vec3(1, 0, 0))
        slot = self.effects.pool[0]

        # 수명을 0.15초 남김 (페이드 구간: 0.20초 미만)
        slot["life"] = 0.10
        self.effects.update(0.01)

        alpha = slot["node"].getColorScale()[3]
        self.assertLess(alpha, 1.0, "Casing should fade out when life < 0.20s")
        self.assertGreater(alpha, 0.0)

        # 수명 완전 소진
        self.effects.update(0.20)
        self.assertFalse(slot["active"])
        self.assertTrue(slot["node"].isHidden())

    def test_large_and_zero_dt_stability(self):
        """0 이하 dt 및 프레임 드롭(대형 dt) 안정성 검증"""
        self.effects.emit("PISTOL", Vec3(0, 0, 1.0), Vec3(1, 0, 0))
        slot = self.effects.pool[0]
        initial_pos = Vec3(slot["pos"])

        # dt <= 0: 상태 변화 없음
        self.effects.update(0.0)
        self.effects.update(-0.1)
        self.assertEqual(slot["pos"], initial_pos)

        # dt = 10.0 (대형 프레임 드롭): 수치 발산이나 크래시 없이 정상 수명 만료
        self.effects.update(10.0)
        self.assertFalse(slot["active"])
        self.assertTrue(slot["node"].isHidden())

    def test_clear(self):
        """clear 호출 시 잔여 탄피 즉시 비활성화 및 리셋 검증"""
        for _ in range(5):
            self.effects.emit("PISTOL", Vec3(0, 0, 1.0), Vec3(1, 0, 0))

        self.assertEqual(self.effects.active_count, 5)

        self.effects.clear()

        self.assertEqual(self.effects.active_count, 0)
        self.assertEqual(self.effects.cursor, 0)
        for c in self.effects.pool:
            self.assertFalse(c["active"])
            self.assertTrue(c["node"].isHidden())

    def test_destroy(self):
        """destroy 호출 시 노드 제거 및 풀 해제 검증"""
        self.effects.destroy()
        self.assertEqual(len(self.effects.pool), 0)
        self.assertEqual(self.effects.cursor, 0)


if __name__ == "__main__":
    unittest.main()
