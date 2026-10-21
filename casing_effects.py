import math
import random
from panda3d.core import (
    NodePath, Vec3, LColor, TransparencyAttrib
)
from geometry import make_cylinder_to


# 무기별 전용 탄피 및 셸 색상 팔레트
COLOR_BRASS_PISTOL = LColor(0.92, 0.76, 0.24, 1.0)    # .50 AE 리치 골든 브라스
COLOR_BRASS_DUAL = LColor(0.88, 0.74, 0.28, 1.0)      # 9mm 파라블럼 라이트 브라스
COLOR_BRASS_AR = LColor(0.85, 0.70, 0.25, 1.0)        # 5.56mm 밀스펙 황동
COLOR_SHOTGUN_HULL = LColor(0.80, 0.14, 0.12, 1.0)    # 12게이지 레드 플라스틱 헐
COLOR_SHOTGUN_BASE = LColor(0.88, 0.72, 0.22, 1.0)    # 12게이지 황동 베이스 림

# 지면 높이 및 물리 상수
CASING_FLOOR_Z = 0.018
GRAVITY_Z = 9.80
FADE_DURATION = 0.20


class CasingEffects:
    """고성능 3D 탄피 물리 및 렌더링 풀 시스템

    - 무기별 특화 크기 및 형상 (.50 AE, 9mm, 5.56mm, 12게이지 투톤 샷건 셸)
    - 과도한 눈부심(setLightOff) 제거 및 자연스러운 3D 월드 음영 렌더링
    - 약 0.75~0.95초 최적 수명 및 소멸 직전 부드러운 알파 페이드아웃
    - 지면 착지 후 떨림/무한 튀기 방지 (저속 시 완전 안착 처리)
    - 사전 할당 고정 크기 풀(24개) 기반 무기 공유 재사용 (런타임 노드 생성 없음)
    """

    def __init__(self, world_root, capacity=24):
        self.world_root = world_root if world_root is not None else NodePath("casing_world_root")
        self.capacity = max(1, int(capacity))
        self.cursor = 0
        self.pool = []

        self._init_pool()

    def _init_pool(self):
        """사전 할당 고정 풀 생성 - 무기별 4가지 서브메시를 각 슬롯에 미리 구성"""
        for i in range(self.capacity):
            root = self.world_root.attachNewNode(f"casing_fx_{i}")
            root.setTransparency(TransparencyAttrib.MAlpha)
            root.hide()

            meshes = {}

            # 1. PISTOL (.50 Action Express Magnum) - 굵고 묵직한 대구경 황동
            m_pistol = root.attachNewNode("mesh_pistol")
            make_cylinder_to(m_pistol, 0.013, 0.030, 0.013, COLOR_BRASS_PISTOL, 0, 0, 0, axis='y')
            m_pistol.hide()
            meshes["PISTOL"] = m_pistol

            # 2. DUAL_PISTOL (9x19mm Parabellum) - 컴팩트하고 짧은 표준 권총 탄피
            m_dual = root.attachNewNode("mesh_dual")
            make_cylinder_to(m_dual, 0.009, 0.020, 0.009, COLOR_BRASS_DUAL, 0, 0, 0, axis='y')
            m_dual.hide()
            meshes["DUAL_PISTOL"] = m_dual

            # 3. AR (5.56x45mm NATO) - 길고 날씬한 소총 라이플 탄피
            m_ar = root.attachNewNode("mesh_ar")
            make_cylinder_to(m_ar, 0.0095, 0.038, 0.0095, COLOR_BRASS_AR, 0, 0, 0, axis='y')
            m_ar.hide()
            meshes["AR"] = m_ar

            # 4. SHOTGUN (12-Gauge 2.75" Shell) - 붉은색 플라스틱 헐 본체 + 황동 바닥 림
            m_sg = root.attachNewNode("mesh_shotgun")
            # 붉은색 플라스틱 헐
            make_cylinder_to(m_sg, 0.016, 0.034, 0.016, COLOR_SHOTGUN_HULL, 0, 0.006, 0, axis='y')
            # 황동 베이스 림
            make_cylinder_to(m_sg, 0.0165, 0.012, 0.0165, COLOR_SHOTGUN_BASE, 0, -0.017, 0, axis='y')
            m_sg.hide()
            meshes["SHOTGUN"] = m_sg

            self.pool.append({
                "node": root,
                "meshes": meshes,
                "pos": Vec3(0, 0, 0),
                "vel": Vec3(0, 0, 0),
                "rot": Vec3(0, 0, 0),
                "spin": Vec3(0, 0, 0),
                "life": 0.0,
                "max_life": 0.85,
                "active": False,
                "is_settled": False,
                "current_weapon": None,
            })

    @property
    def active_count(self):
        """현재 비행/생존 중인 활성 탄피 개수"""
        return sum(1 for c in self.pool if c["active"])

    def emit(self, weapon, position, velocity, is_left=False):
        """무기 발사 시 지정된 위치/속도로 탄피 배출

        Args:
            weapon (str): 'PISTOL', 'DUAL_PISTOL', 'AR', 'SHOTGUN' (대소문자 무관)
            position (Vec3 | tuple): world_root 기준 3D 배출 위치
            velocity (Vec3 | tuple): world_root 기준 초기 사출 속도 벡터
            is_left (bool): 좌측 배출 여부 (좌측 아킴보 권총 등 역회전/좌방향 연출)
        """
        w = (weapon or "PISTOL").upper()
        if w not in ("PISTOL", "DUAL_PISTOL", "AR", "SHOTGUN"):
            if "SHOTGUN" in w or "SG" in w:
                w = "SHOTGUN"
            elif "AR" in w or "RIFLE" in w:
                w = "AR"
            elif "DUAL" in w:
                w = "DUAL_PISTOL"
            else:
                w = "PISTOL"

        c = self.pool[self.cursor]
        self.cursor = (self.cursor + 1) % self.capacity

        # 이전 사용 흔적 완전 초기화 (크기, 색상, 투명도)
        c["node"].setScale(1.0, 1.0, 1.0)
        c["node"].setColorScale(1.0, 1.0, 1.0, 1.0)

        # 무기별 전용 메시 활성화 및 타 메시 비활성화
        for m_key, m_node in c["meshes"].items():
            if m_key == w:
                m_node.show()
            else:
                m_node.hide()

        c["pos"] = Vec3(position)
        c["vel"] = Vec3(velocity)

        # 초기 3D 무작위 회전 자세
        c["rot"] = Vec3(
            random.uniform(0.0, 360.0),
            random.uniform(0.0, 360.0),
            random.uniform(0.0, 360.0)
        )

        # 텀블링 회전 스핀 각속도 (배출 방향에 따른 스핀 부호)
        side_sign = -1.0 if is_left else 1.0
        c["spin"] = Vec3(
            random.uniform(500.0, 1100.0) * side_sign,
            random.uniform(350.0, 850.0),
            random.uniform(250.0, 650.0)
        )

        # 0.75 ~ 0.95초의 시야 방해 없는 짧고 경쾌한 수명
        c["max_life"] = random.uniform(0.75, 0.95)
        c["life"] = c["max_life"]

        c["active"] = True
        c["is_settled"] = False
        c["current_weapon"] = w

        c["node"].setPos(c["pos"])
        c["node"].setHpr(c["rot"])
        c["node"].show()

    def update(self, dt):
        """탄피 물리 시뮬레이션 및 수명 갱신

        중력 가속도, 공기 저항, 지면 바운스 및 안착, 소멸 페이드아웃 처리.
        """
        if dt <= 0.0:
            return

        # 랙 스파이크/프레임 드롭 시 수치 발산 방지 클램핑
        sim_dt = min(dt, 0.10)

        for c in self.pool:
            if not c["active"]:
                continue

            c["life"] -= dt
            if c["life"] <= 0.0:
                c["active"] = False
                c["node"].hide()
                continue

            # 소멸 직전 부드러운 알파 페이드아웃 (화면에서 툭 꺼지는 현상 제거)
            if c["life"] < FADE_DURATION:
                alpha = max(0.0, min(1.0, c["life"] / FADE_DURATION))
                c["node"].setColorScale(1.0, 1.0, 1.0, alpha)

            # 지면에 완전히 안착한 경우 물리 계산 생략
            if c["is_settled"]:
                continue

            # 중력 및 가벼운 공기 저항
            c["vel"].z -= GRAVITY_Z * sim_dt
            c["vel"].x *= (1.0 - 0.40 * sim_dt)
            c["vel"].y *= (1.0 - 0.40 * sim_dt)

            c["pos"] += c["vel"] * sim_dt
            c["rot"] += c["spin"] * sim_dt

            # 지면 충돌 및 바운스 감쇄 처리
            if c["pos"].z <= CASING_FLOOR_Z:
                c["pos"].z = CASING_FLOOR_Z

                speed_sq = c["vel"].x * c["vel"].x + c["vel"].y * c["vel"].y + c["vel"].z * c["vel"].z

                # 수직 반동 속도가 작거나 전체 운동 에너지가 바닥나면 즉시 안착 (진동/무한 튀기 방지)
                if abs(c["vel"].z) < 0.45 and speed_sq < 0.60:
                    c["vel"].set(0.0, 0.0, 0.0)
                    c["spin"].set(0.0, 0.0, 0.0)
                    c["is_settled"] = True
                else:
                    # 탄성 반발 계수 및 마찰 감쇄
                    c["vel"].z = -c["vel"].z * 0.28
                    c["vel"].x *= 0.62
                    c["vel"].y *= 0.62
                    c["spin"] *= 0.55

            c["node"].setPos(c["pos"])
            c["node"].setHpr(c["rot"])

    def clear(self):
        """모든 탄피 즉시 비활성화 및 숨김 (새 게임 시작 또는 스테이지 리셋 시 호출)"""
        for c in self.pool:
            c["active"] = False
            c["is_settled"] = False
            c["life"] = 0.0
            c["node"].setColorScale(1.0, 1.0, 1.0, 1.0)
            c["node"].hide()
        self.cursor = 0

    def destroy(self):
        """모든 씬 노드 제거 및 메모리 해제"""
        for c in self.pool:
            node = c.get("node")
            if node and not node.isEmpty():
                node.removeNode()
        self.pool.clear()
        self.cursor = 0
