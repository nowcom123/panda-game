"""
Render high-resolution visual previews of CableOverlordBoss (골해의 지배자)
- Front view (전신 정면)
- Side view (전신 측면)
- 360-degree arm sweep attack motion (360도 뼈팔 휩쓸기 공격 모션)
- Spider leap slam landing (거미 다리 도약 착지 모션)
- Bone spike eruption (순차 뼈 가시 분출 장면)
"""
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root_dir))

from panda3d.core import (loadPrcFileData, AmbientLight, DirectionalLight,
                          OrthographicLens, PerspectiveLens, Filename, Vec3, LColor)
loadPrcFileData('', 'window-type offscreen\nwin-size 1280 960\naudio-library-name null\nsync-video false')

from direct.showbase.ShowBase import ShowBase
from geometry import make_cube_to
from monster import CableOverlordBoss
from boss_patterns import GroundDangerIndicator, GroundBoneSpike

base = ShowBase()
base.setBackgroundColor(0.10, 0.11, 0.14)

# 1. 조명 설정 (주광 + 보조 앰비언트)
ambient = AmbientLight('preview_ambient')
ambient.setColor((0.55, 0.55, 0.60, 1.0))
base.render.setLight(base.render.attachNewNode(ambient))

dir_key = DirectionalLight('preview_key')
dir_key.setColor((0.95, 0.90, 0.85, 1.0))
dir_np = base.render.attachNewNode(dir_key)
dir_np.setHpr(-40, -35, 0)
base.render.setLight(dir_np)

dir_fill = DirectionalLight('preview_fill')
dir_fill.setColor((0.35, 0.40, 0.50, 1.0))
fill_np = base.render.attachNewNode(dir_fill)
fill_np.setHpr(140, -20, 0)
base.render.setLight(fill_np)

out_dir = Path(__file__).resolve().parent

# 바닥 타일
floor = make_cube_to(base.render, 24.0, 24.0, 0.1, LColor(0.18, 0.20, 0.24, 1.0), 0, 0, -0.05)

# 보스 생성
boss = CableOverlordBoss(base.render, 0.0, 0.0)
boss.update(0.016, is_moving=False)

# 카메라 렌즈 설정 (원근감 있는 드라마틱 뷰)
lens = PerspectiveLens()
lens.setFov(55)
base.cam.node().setLens(lens)


def capture(filename, cam_pos, look_at):
    base.camera.setPos(*cam_pos)
    base.camera.lookAt(*look_at)
    for _ in range(4):
        base.graphicsEngine.renderFrame()
    target_path = out_dir / filename
    base.win.saveScreenshot(Filename.fromOsSpecific(str(target_path)))
    print(f"Saved: {target_path}")


# ------------------------------------------------------------------------------
# 1. 전신 정면 샷 (boss_fullbody_front.png)
# ------------------------------------------------------------------------------
boss.node.setH(180)  # 카메라(+Y 방향)를 향하도록 정면 회전
boss.set_recovery_pose(False)
boss.set_sweep_telegraph_pose(False)
boss.update(0.016, is_moving=False)
capture('boss_fullbody_front.png', (0.0, -7.5, 2.6), (0.0, 0.0, 2.1))

# ------------------------------------------------------------------------------
# 2. 전신 측면 샷 (boss_fullbody_side.png)
# ------------------------------------------------------------------------------
boss.node.setH(90)  # 우측 측면이 카메라를 향하도록 회전
boss.update(0.016, is_moving=False)
capture('boss_fullbody_side.png', (0.0, -7.2, 2.4), (0.0, 0.0, 2.0))

# ------------------------------------------------------------------------------
# 3. 360도 뼈팔 휩쓸기 공격 모션 (boss_attack_arm_sweep.png)
# ------------------------------------------------------------------------------
boss.node.setH(160)
boss.set_sweep_arm_angle(75.0)  # 팔을 수평으로 뻗고 휩쓰는 중
ind_sweep = GroundDangerIndicator(base.render, 0.0, 0.0, radius=boss.pattern_controller.sweep_radius, color=LColor(1.0, 0.2, 0.15, 0.75))
ind_sweep.set_progress(0.85)
capture('boss_attack_arm_sweep.png', (-4.0, -8.0, 4.5), (0.0, 0.0, 1.8))
ind_sweep.destroy()

# ------------------------------------------------------------------------------
# 4. 거미 다리 도약 착지 / 강타 모션 (boss_attack_leap_slam.png)
# ------------------------------------------------------------------------------
boss.node.setH(180)
boss.set_recovery_pose(False)
boss.set_crouch_pose(True)  # 다리를 웅크리고 바닥을 강타하는 낮은 자세
ind_leap = GroundDangerIndicator(base.render, 0.0, 0.0, radius=3.5, color=LColor(1.0, 0.35, 0.1, 0.8))
ind_leap.set_progress(1.0)
capture('boss_attack_leap_slam.png', (3.2, -6.8, 3.2), (0.0, 0.0, 1.4))
ind_leap.destroy()
boss.set_crouch_pose(False)

# ------------------------------------------------------------------------------
# 5. 순차 뼈 가시 분출 장면 (boss_attack_spikes.png)
# ------------------------------------------------------------------------------
boss.node.setH(180)
boss.set_cast_roar_pose(True)  # 두개골을 치켜들고 포효 시전
spikes = [
    GroundBoneSpike(base.render, -1.8, -2.2, max_height=2.4),
    GroundBoneSpike(base.render, 1.2, -3.2, max_height=2.6),
    GroundBoneSpike(base.render, 0.2, -4.5, max_height=2.2),
]
for sp in spikes:
    sp.set_height_ratio(1.0)

ind_spikes = [
    GroundDangerIndicator(base.render, -1.8, -2.2, radius=1.75, color=LColor(1.0, 0.4, 0.1, 0.7)),
    GroundDangerIndicator(base.render, 1.2, -3.2, radius=1.75, color=LColor(1.0, 0.4, 0.1, 0.7)),
    GroundDangerIndicator(base.render, 0.2, -4.5, radius=1.75, color=LColor(1.0, 0.4, 0.1, 0.7)),
]
for ind in ind_spikes:
    ind.set_progress(0.9)

capture('boss_attack_spikes.png', (0.0, -9.0, 3.8), (0.0, -2.5, 1.8))

for sp in spikes:
    sp.destroy()
for ind in ind_spikes:
    ind.destroy()

boss.destroy()
base.destroy()
print("All previews rendered successfully.")
